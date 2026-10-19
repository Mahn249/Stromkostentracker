"""Tests for historical Excel import validation and persistence."""

from datetime import datetime
from pathlib import Path
import sqlite3

from openpyxl import Workbook
import pytest

from stromkostentracker.imports import import_excel
from stromkostentracker.imports.inspect_excel import (
    EXPECTED_HEADERS,
    InvalidExcelFile,
    inspect_excel as inspect_workbook,
)


def _write_workbook(path: Path, rows: list[tuple[object, ...]]) -> None:
    """Create an import workbook for testing."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(EXPECTED_HEADERS)
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def test_inspect_excel_normalizes_timestamps_and_skips_blank_rows(
    tmp_path: Path,
) -> None:
    """Inspection normalizes timezone-naive Excel timestamps as UTC."""
    file_path = tmp_path / "readings.xlsx"
    _write_workbook(
        file_path,
        [
            (
                datetime(2025, 7, 25, 0, 0),
                datetime(2025, 7, 25, 0, 15),
                26087.284,
                275.367,
                0.135,
                "Abgelesen",
            ),
            (None, None, None, None, None, None),
            (
                datetime(2025, 7, 25, 0, 15),
                datetime(2025, 7, 25, 0, 30),
                26087.419,
                275.367,
                0.135,
                None,
            ),
        ],
    )

    result = inspect_workbook(file_path)

    assert not result.errors
    assert result.empty_rows == 1
    assert result.rows[0].start == "2025-07-25T00:00:00+00:00"
    assert result.rows[0].end == "2025-07-25T00:15:00+00:00"
    assert result.rows[0].note == "Abgelesen"


def test_inspect_excel_reports_invalid_value_and_accepts_missing_feed_in(
    tmp_path: Path,
) -> None:
    """Invalid numbers identify their cell value, optional feed-in may be empty."""
    file_path = tmp_path / "readings.xlsx"
    _write_workbook(
        file_path,
        [
            (
                "2025-07-25T00:00:00Z",
                "2025-07-25T00:15:00Z",
                "invalid",
                None,
                0.135,
                None,
            ),
            (
                "2025-07-25T00:15:00Z",
                "2025-07-25T00:30:00Z",
                26087.419,
                None,
                0.135,
                None,
            ),
        ],
    )

    result = inspect_workbook(file_path)

    assert result.error_count == 1
    assert result.errors == [
        "Zeile 2: Zählerstand - Verbrauch (kWh): ungültiger Zahlenwert 'invalid'"
    ]
    assert len(result.rows) == 1
    assert result.rows[0].feed_in is None


def test_inspect_excel_rejects_wrong_headers(tmp_path: Path) -> None:
    """The workbook must use the documented column headers."""
    file_path = tmp_path / "readings.xlsx"
    _write_workbook(file_path, [])
    workbook = Workbook()
    workbook.active.append(("wrong",))
    workbook.save(file_path)

    with pytest.raises(InvalidExcelFile):
        inspect_workbook(file_path)


def test_import_excel_skips_duplicate_intervals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The import is idempotent for intervals with the same source and times."""
    file_path = tmp_path / "readings.xlsx"
    _write_workbook(
        file_path,
        [
            (
                "2025-07-25T00:00:00Z",
                "2025-07-25T00:15:00Z",
                26087.284,
                275.367,
                0.135,
                None,
            ),
            (
                "2025-07-25T00:00:00Z",
                "2025-07-25T00:15:00Z",
                26087.284,
                275.367,
                0.135,
                None,
            ),
        ],
    )
    database_path = tmp_path / "meter.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE meter_intervals (
                interval_start_utc TEXT NOT NULL,
                interval_end_utc TEXT NOT NULL,
                consumption_meter_kwh REAL,
                feed_in_meter_kwh REAL,
                consumption_delta_kwh REAL,
                note TEXT,
                source TEXT NOT NULL,
                UNIQUE (interval_start_utc, interval_end_utc, source)
            )
            """
        )
    monkeypatch.setattr(import_excel, "DATABASE_PATH", database_path)
    rows = inspect_workbook(file_path).rows

    assert import_excel.count_existing_duplicates(rows) == 1
    assert import_excel.import_excel(rows) == import_excel.ImportResult(
        imported=1, skipped=1
    )
    assert import_excel.import_excel(rows) == import_excel.ImportResult(
        imported=0, skipped=2
    )
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM meter_intervals"
        ).fetchone() == (1,)


def test_import_excel_skips_legacy_timestamp_formats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An existing naive timestamp matches the equivalent UTC ISO timestamp."""
    file_path = tmp_path / "readings.xlsx"
    _write_workbook(
        file_path,
        [
            (
                "2025-07-25T00:00:00Z",
                "2025-07-25T00:15:00Z",
                26087.284,
                275.367,
                0.135,
                None,
            )
        ],
    )
    database_path = tmp_path / "meter.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE meter_intervals (
                interval_start_utc TEXT NOT NULL,
                interval_end_utc TEXT NOT NULL,
                consumption_meter_kwh REAL,
                feed_in_meter_kwh REAL,
                consumption_delta_kwh REAL,
                note TEXT,
                source TEXT NOT NULL,
                UNIQUE (interval_start_utc, interval_end_utc, source)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO meter_intervals (
                interval_start_utc, interval_end_utc, source
            ) VALUES (?, ?, ?)
            """,
            ("2025-07-25 00:00:00", "2025-07-25 00:15:00", "manual_import"),
        )
    monkeypatch.setattr(import_excel, "DATABASE_PATH", database_path)
    rows = inspect_workbook(file_path).rows

    assert import_excel.count_existing_duplicates(rows) == 1
    assert import_excel.import_excel(rows) == import_excel.ImportResult(
        imported=0, skipped=1
    )
