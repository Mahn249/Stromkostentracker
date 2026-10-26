"""Tests for cumulative meter validation and transactional persistence."""

# Internal helpers are exercised to verify transaction guarantees.
# ruff: noqa: SLF001

from datetime import UTC, datetime
from pathlib import Path
import sqlite3

import pytest

from homeassistant.core import State
from stromkostentracker import meter_writings


def _prepare_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    database_path = tmp_path / "meter.db"
    database_path.touch()
    monkeypatch.setattr(meter_writings, "DATABASE_PATH", database_path)
    meter_writings._ensure_meter_schema()
    return database_path


def test_validate_meter_state_requires_cumulative_energy_sensor() -> None:
    """Energy readings in kWh are accepted regardless of state class."""
    state = State(
        "sensor.energy",
        "12.5",
        {
            "device_class": "energy",
            "unit_of_measurement": "kWh",
        },
    )

    assert meter_writings.validate_meter_state(state, "sensor.energy") == 12.5
    state_with_other_state_class = State(
        "sensor.energy",
        "12.5",
        {
            "device_class": "energy",
            "unit_of_measurement": "kWh",
            "state_class": "measurement",
        },
    )
    assert (
        meter_writings.validate_meter_state(
            state_with_other_state_class, "sensor.energy"
        )
        == 12.5
    )

    invalid_states = [
        State("sensor.energy", "12.5", {"unit_of_measurement": "kWh"}),
        State(
            "sensor.energy",
            "12.5",
            {
                "device_class": "energy",
                "unit_of_measurement": "Wh",
            },
        ),
    ]
    for invalid_state in invalid_states:
        with pytest.raises(meter_writings.MeterSensorError):
            meter_writings.validate_meter_state(invalid_state, "sensor.energy")


def test_record_meter_reading_uses_unknowns_for_baseline_switch_and_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deltas are not calculated without a matching increasing checkpoint."""
    database_path = _prepare_database(tmp_path, monkeypatch)
    first_time = datetime(2026, 10, 26, 10, tzinfo=UTC)

    assert meter_writings._record_meter_reading("sensor.first", 100, first_time)
    assert meter_writings._record_meter_reading(
        "sensor.first", 101.25, datetime(2026, 10, 26, 10, 15, tzinfo=UTC)
    )
    assert meter_writings._record_meter_reading(
        "sensor.second", 5, datetime(2026, 10, 26, 10, 30, tzinfo=UTC)
    )
    assert meter_writings._record_meter_reading(
        "sensor.second", 2, datetime(2026, 10, 26, 10, 45, tzinfo=UTC)
    )
    assert meter_writings._record_meter_reading(
        "sensor.second", 2.5, datetime(2026, 10, 26, 11, tzinfo=UTC)
    )

    with sqlite3.connect(database_path) as connection:
        intervals = connection.execute(
            """SELECT source, consumption_meter_start_kwh,
                      consumption_meter_kwh, consumption_delta_kwh
               FROM meter_intervals ORDER BY id"""
        ).fetchall()
        checkpoint = connection.execute(
            "SELECT entity_id, value_kwh FROM meter_checkpoint WHERE id = 1"
        ).fetchone()

    assert intervals == [
        ("sensor.first", None, 100, None),
        ("sensor.first", 100, 101.25, 1.25),
        ("sensor.second", None, 5, None),
        ("sensor.second", 5, 2, None),
        ("sensor.second", 2, 2.5, 0.5),
    ]
    assert checkpoint == ("sensor.second", 2.5)


def test_failed_checkpoint_commit_rolls_back_interval_and_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An interval insert cannot commit if updating its checkpoint fails."""
    database_path = _prepare_database(tmp_path, monkeypatch)
    first_time = datetime(2026, 10, 26, 10, tzinfo=UTC)
    meter_writings._record_meter_reading("sensor.energy", 10, first_time)

    with sqlite3.connect(database_path) as connection:
        connection.execute("""
            CREATE TRIGGER fail_checkpoint_update
            BEFORE UPDATE ON meter_checkpoint
            BEGIN
                SELECT RAISE(ABORT, 'checkpoint update failed');
            END
        """)

    with pytest.raises(sqlite3.IntegrityError):
        meter_writings._record_meter_reading(
            "sensor.energy", 11, datetime(2026, 10, 26, 10, 15, tzinfo=UTC)
        )

    with sqlite3.connect(database_path) as connection:
        intervals = connection.execute(
            "SELECT consumption_meter_kwh FROM meter_intervals ORDER BY id"
        ).fetchall()
        checkpoint = connection.execute(
            "SELECT value_kwh FROM meter_checkpoint WHERE id = 1"
        ).fetchone()

    assert intervals == [(10,)]
    assert checkpoint == (10,)
