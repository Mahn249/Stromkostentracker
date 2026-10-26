"""Record consumption intervals from a cumulative Home Assistant energy sensor."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import math
from pathlib import Path
import sqlite3

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import ATTR_DEVICE_CLASS, ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, State
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)
DATABASE_PATH = Path(__file__).resolve().parents[2] / "energy_cost_tracker.db"
_ENERGY_UNIT = "kWh"


class MeterSensorError(Exception):
    """Raised when the configured meter sensor is unsupported."""


def validate_meter_state(state: State | None, entity_id: str) -> float:
    """Return a valid cumulative kWh reading or raise a configuration error."""
    if state is None:
        raise MeterSensorError(f"Sensor {entity_id} is not available")
    if (
        state.attributes.get(ATTR_DEVICE_CLASS) != SensorDeviceClass.ENERGY
        or state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) != _ENERGY_UNIT
    ):
        raise MeterSensorError(
            f"Sensor {entity_id} must be an energy sensor in kWh"
        )
    try:
        value = float(state.state)
    except ValueError as err:
        raise MeterSensorError(
            f"Sensor {entity_id} has no numeric reading: {state.state}"
        ) from err
    if not math.isfinite(value) or value < 0:
        raise MeterSensorError(
            f"Sensor {entity_id} has an invalid cumulative reading: {state.state}"
        )
    return value


def _ensure_meter_schema() -> None:
    """Create the meter table if needed and add the cumulative start reading."""
    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(f"Database not found: {DATABASE_PATH}")

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS meter_intervals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                interval_start_utc TEXT NOT NULL,
                interval_end_utc TEXT NOT NULL,
                consumption_meter_kwh REAL,
                feed_in_meter_kwh REAL,
                consumption_delta_kwh REAL,
                note TEXT,
                source TEXT NOT NULL DEFAULT 'unknown',
                UNIQUE (interval_start_utc, interval_end_utc, source)
            )"""
        )
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(meter_intervals)")
        }
        if "consumption_meter_start_kwh" not in columns:
            connection.execute(
                "ALTER TABLE meter_intervals "
                "ADD COLUMN consumption_meter_start_kwh REAL"
            )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS meter_checkpoint (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                entity_id TEXT NOT NULL,
                value_kwh REAL NOT NULL,
                timestamp_utc TEXT NOT NULL
            )"""
        )


def _record_meter_reading(
    entity_id: str, value_kwh: float, timestamp: datetime
) -> bool:
    """Atomically store one reading, its interval, and the latest checkpoint."""
    if not math.isfinite(value_kwh) or value_kwh < 0:
        raise ValueError("Cumulative meter readings must be finite and non-negative")

    timestamp_utc = dt_util.as_utc(timestamp).isoformat()
    with sqlite3.connect(DATABASE_PATH, timeout=30) as connection:
        connection.execute("BEGIN IMMEDIATE")
        checkpoint = connection.execute(
            """SELECT entity_id, value_kwh, timestamp_utc
               FROM meter_checkpoint WHERE id = 1"""
        ).fetchone()

        if checkpoint is not None and checkpoint[2] >= timestamp_utc:
            return False

        if checkpoint is not None and checkpoint[0] == entity_id:
            previous_value = float(checkpoint[1])
            interval_start = str(checkpoint[2])
            start_value = previous_value
            if value_kwh < previous_value:
                _LOGGER.warning(
                    "Cumulative energy sensor %s decreased; storing the new "
                    "checkpoint with an unknown interval",
                    entity_id,
                )
                delta_kwh = None
            else:
                delta_kwh = value_kwh - previous_value
        else:
            interval_start = (
                str(checkpoint[2]) if checkpoint is not None else timestamp_utc
            )
            start_value = None
            delta_kwh = None

        connection.execute(
            """INSERT INTO meter_intervals (
                   interval_start_utc, interval_end_utc,
                   consumption_meter_kwh, consumption_meter_start_kwh,
                   consumption_delta_kwh, source
               ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                interval_start,
                timestamp_utc,
                value_kwh,
                start_value,
                delta_kwh,
                entity_id,
            ),
        )
        connection.execute(
            """INSERT INTO meter_checkpoint (id, entity_id, value_kwh, timestamp_utc)
               VALUES (1, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   entity_id = excluded.entity_id,
                   value_kwh = excluded.value_kwh,
                   timestamp_utc = excluded.timestamp_utc""",
            (entity_id, value_kwh, timestamp_utc),
        )
    return True


@dataclass(repr=False)
class MeterIntervalWriter:
    """Persist periodic readings from one cumulative energy sensor."""

    hass: HomeAssistant
    entity_id: str
    interval: timedelta
    _unsubscribe_interval: CALLBACK_TYPE = field(init=False)

    @classmethod
    async def async_create(
        cls,
        hass: HomeAssistant,
        entity_id: str,
        interval: timedelta,
    ) -> MeterIntervalWriter:
        """Validate the selected sensor and prepare the database."""
        initial_value = validate_meter_state(hass.states.get(entity_id), entity_id)
        await hass.async_add_executor_job(_ensure_meter_schema)
        await hass.async_add_executor_job(
            _record_meter_reading, entity_id, initial_value, dt_util.utcnow()
        )
        return cls(hass, entity_id, interval)

    def async_start(self) -> None:
        """Start periodic energy meter sampling."""
        self._unsubscribe_interval = async_track_time_interval(
            self.hass, self._async_finish_interval, self.interval
        )

    def async_stop(self) -> None:
        """Stop periodic energy meter sampling."""
        self._unsubscribe_interval()

    async def _async_finish_interval(self, now: datetime) -> None:
        """Validate and atomically persist the latest cumulative reading."""
        try:
            value_kwh = validate_meter_state(
                self.hass.states.get(self.entity_id), self.entity_id
            )
        except MeterSensorError as err:
            _LOGGER.warning(
                "Skipping invalid cumulative energy reading from %s: %s",
                self.entity_id,
                err,
            )
            return

        try:
            stored = await self.hass.async_add_executor_job(
                _record_meter_reading, self.entity_id, value_kwh, now
            )
        except OSError, sqlite3.Error:
            _LOGGER.exception(
                "Unable to store cumulative energy reading for %s",
                self.entity_id,
            )
            return

        if not stored:
            _LOGGER.debug(
                "Ignoring stale cumulative energy reading from %s", self.entity_id
            )


async def async_setup_meter_writer(
    hass: HomeAssistant,
    entity_id: str,
    interval: timedelta,
) -> MeterIntervalWriter:
    """Start recording consumption for the selected entity."""
    writer = await MeterIntervalWriter.async_create(hass, entity_id, interval)
    writer.async_start()
    return writer
