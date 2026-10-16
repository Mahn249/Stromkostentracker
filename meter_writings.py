"""Record consumption intervals from a Home Assistant sensor."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import partial
import logging
import math
from pathlib import Path
import sqlite3

from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, UnitOfEnergy, UnitOfPower
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)
DATABASE_PATH = Path(__file__).resolve().parents[2] / "energy_cost_tracker.db"
_POWER_UNIT = UnitOfPower.WATT
_ENERGY_UNIT = UnitOfEnergy.KILO_WATT_HOUR


class MeterSensorError(Exception):
    """Raised when the configured meter sensor is unsupported."""


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


def _insert_interval(
    *,
    interval_start: datetime,
    interval_end: datetime,
    source: str,
    consumption_delta_kwh: float,
    meter_start_kwh: float | None = None,
    meter_end_kwh: float | None = None,
) -> None:
    """Store one completed consumption interval."""
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """INSERT INTO meter_intervals (
                   interval_start_utc, interval_end_utc,
                   consumption_meter_kwh,
                   consumption_meter_start_kwh,
                   consumption_delta_kwh, source
               ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                dt_util.as_utc(interval_start).isoformat(),
                dt_util.as_utc(interval_end).isoformat(),
                meter_end_kwh,
                meter_start_kwh,
                consumption_delta_kwh,
                source,
            ),
        )


@dataclass(repr=False)
class MeterIntervalWriter:
    """Collect one selected meter sensor and persist its periodic deltas."""

    hass: HomeAssistant
    entity_id: str
    interval: timedelta
    unit: str

    interval_start: datetime = field(init=False)
    last_sample_time: datetime = field(init=False)
    meter_start_kwh: float | None = field(init=False)
    last_power_w: float | None = field(init=False)
    consumption_delta_kwh: float = field(init=False)
    period_has_power_data: bool = field(init=False)
    period_has_gap: bool = field(init=False)
    _unsubscribe_interval: CALLBACK_TYPE = field(init=False)
    _unsubscribe_state: CALLBACK_TYPE | None = field(init=False)

    def __post_init__(self) -> None:
        """Initialize the interval state from the selected entity."""
        self.interval_start = dt_util.utcnow()
        self.last_sample_time = self.interval_start
        self.meter_start_kwh: float | None = None
        self.last_power_w: float | None = None
        self.consumption_delta_kwh = 0.0
        self.period_has_power_data = False
        self.period_has_gap = False
        self._set_baseline(self.hass.states.get(self.entity_id))

    @classmethod
    async def async_create(
        cls,
        hass: HomeAssistant,
        entity_id: str,
        interval: timedelta,
    ) -> MeterIntervalWriter:
        """Validate the selected sensor and prepare the database."""
        state = hass.states.get(entity_id)
        if state is None:
            raise MeterSensorError(f"Sensor {entity_id} has no state")

        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        if unit not in (_POWER_UNIT, _ENERGY_UNIT):
            raise MeterSensorError(
                f"Sensor {entity_id} must use {_POWER_UNIT} or {_ENERGY_UNIT}; "
                f"got {unit!r}"
            )

        await hass.async_add_executor_job(_ensure_meter_schema)
        return cls(hass, entity_id, interval, unit)

    def async_start(self) -> None:
        """Start sensor tracking and periodic interval writes."""
        self._unsubscribe_interval = async_track_time_interval(
            self.hass, self._async_finish_interval, self.interval
        )
        self._unsubscribe_state = (
            async_track_state_change_event(
                self.hass, self.entity_id, self._async_handle_state_change
            )
            if self.unit == _POWER_UNIT
            else None
        )

    def async_stop(self) -> None:
        """Stop interval and sensor state tracking."""
        self._unsubscribe_interval()
        if self._unsubscribe_state is not None:
            self._unsubscribe_state()

    @callback
    def _set_baseline(self, state: State | None) -> None:
        """Set the baseline from a currently available sensor state."""
        if state is None:
            self.period_has_gap = self.unit == _POWER_UNIT
            return
        value = self._numeric_value(state)
        if value is None:
            self.period_has_gap = self.unit == _POWER_UNIT
            return
        if self.unit == _POWER_UNIT:
            self.last_power_w = value
            self.period_has_power_data = True
        else:
            self.meter_start_kwh = value

    @callback
    def _numeric_value(self, state: State) -> float | None:
        """Return a finite sensor reading, logging invalid states."""
        if state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) != self.unit:
            _LOGGER.error(
                "Unit of %s changed from %s to %s; skipping its readings",
                self.entity_id,
                self.unit,
                state.attributes.get(ATTR_UNIT_OF_MEASUREMENT),
            )
            return None
        try:
            value = float(state.state)
        except ValueError:
            _LOGGER.warning(
                "Sensor %s has no numeric reading: %s", self.entity_id, state.state
            )
            return None
        if not math.isfinite(value):
            _LOGGER.warning(
                "Sensor %s has a non-finite reading: %s",
                self.entity_id,
                state.state,
            )
            return None
        return value

    @callback
    def _async_handle_state_change(self, event: Event[EventStateChangedData]) -> None:
        """Integrate the prior power reading until the next state change."""
        if event.data["entity_id"] != self.entity_id:
            return
        new_state: State | None = event.data["new_state"]
        now = dt_util.utcnow()
        self._integrate_power_until(now)
        if new_state is None:
            self.last_power_w = None
            self.period_has_gap = True
            return
        self.last_power_w = self._numeric_value(new_state)
        self.last_sample_time = now
        if self.last_power_w is not None:
            self.period_has_power_data = True
        else:
            self.period_has_gap = True

    @callback
    def _integrate_power_until(self, timestamp: datetime) -> None:
        """Apply the left Riemann sum over the elapsed time."""
        if self.last_power_w is not None:
            elapsed_seconds = (timestamp - self.last_sample_time).total_seconds()
            if elapsed_seconds > 0:
                self.consumption_delta_kwh += (
                    self.last_power_w * elapsed_seconds / 3_600_000
                )
        self.last_sample_time = timestamp

    async def _async_finish_interval(self, now: datetime) -> None:
        """Store the completed period, then establish the next baseline."""
        if self.unit == _POWER_UNIT:
            self._integrate_power_until(now)
            delta_kwh = self.consumption_delta_kwh
            if self.period_has_power_data and not self.period_has_gap:
                await self._async_write(now, delta_kwh)
            else:
                _LOGGER.warning(
                    "Skipping incomplete consumption interval for %s",
                    self.entity_id,
                )
            self.consumption_delta_kwh = 0.0
            self.period_has_power_data = False
            self.period_has_gap = False
            state = self.hass.states.get(self.entity_id)
            self.last_power_w = self._numeric_value(state) if state else None
            self.period_has_power_data = self.last_power_w is not None
            self.period_has_gap = self.last_power_w is None
            self.last_sample_time = now
        else:
            await self._async_finish_meter_interval(now)
        self.interval_start = now

    async def _async_finish_meter_interval(self, now: datetime) -> None:
        """Calculate and store the delta between cumulative meter readings."""
        state = self.hass.states.get(self.entity_id)
        meter_end_kwh = self._numeric_value(state) if state else None
        meter_start_kwh = self.meter_start_kwh
        if meter_start_kwh is not None and meter_end_kwh is not None:
            delta_kwh = meter_end_kwh - meter_start_kwh
            if delta_kwh >= 0:
                await self._async_write(
                    now,
                    delta_kwh,
                    meter_start_kwh=meter_start_kwh,
                    meter_end_kwh=meter_end_kwh,
                )
            else:
                _LOGGER.error(
                    "Meter %s decreased from %.6f to %.6f kWh; skipping interval",
                    self.entity_id,
                    meter_start_kwh,
                    meter_end_kwh,
                )
        else:
            _LOGGER.warning(
                "Skipping interval for %s because a meter reading is unavailable",
                self.entity_id,
            )
        self.meter_start_kwh = meter_end_kwh

    async def _async_write(
        self,
        now: datetime,
        delta_kwh: float,
        *,
        meter_start_kwh: float | None = None,
        meter_end_kwh: float | None = None,
    ) -> None:
        """Write one interval to SQLite without blocking the event loop."""
        try:
            await self.hass.async_add_executor_job(
                partial(
                    _insert_interval,
                    interval_start=self.interval_start,
                    interval_end=now,
                    source=self.entity_id,
                    consumption_delta_kwh=delta_kwh,
                    meter_start_kwh=meter_start_kwh,
                    meter_end_kwh=meter_end_kwh,
                )
            )
        except OSError, sqlite3.Error:
            _LOGGER.exception(
                "Unable to write consumption interval for %s", self.entity_id
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
