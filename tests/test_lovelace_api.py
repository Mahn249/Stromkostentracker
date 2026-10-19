"""Tests for data exposed to the Stromkostentracker Lovelace card."""

from pathlib import Path
import sqlite3

import pytest

from stromkostentracker import lovelace_api


def test_get_available_years_returns_years_with_intervals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only years with stored meter intervals are available."""
    database_path = tmp_path / "meter.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute("""
            CREATE TABLE meter_intervals (
                interval_start_utc TEXT NOT NULL,
                interval_end_utc TEXT NOT NULL
            )
        """)
        connection.executemany(
            """
            INSERT INTO meter_intervals (interval_start_utc, interval_end_utc)
            VALUES (?, ?)
            """,
            [
                ("2024-07-25T00:00:00+00:00", "2024-07-25T00:15:00+00:00"),
                ("2025-01-01T00:00:00+00:00", "2025-01-01T00:15:00+00:00"),
                ("2024-07-25T00:15:00+00:00", "2024-07-25T00:30:00+00:00"),
            ],
        )

    monkeypatch.setattr(lovelace_api, "DATABASE_PATH", database_path)

    assert lovelace_api.get_available_years() == [2025, 2024]
