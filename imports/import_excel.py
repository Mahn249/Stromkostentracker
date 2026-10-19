"""Import validated historical meter readings into the database."""

from dataclasses import dataclass
import sqlite3

from ..database import DATABASE_PATH  # noqa: TID252
from .inspect_excel import ImportedInterval, normalize_timestamp

SOURCE = "manual_import"


@dataclass(frozen=True, slots=True)
class ImportResult:
    """Counts from an Excel import."""

    imported: int
    skipped: int


def count_existing_duplicates(rows: list[ImportedInterval]) -> int:
    """Count intervals already imported or repeated within the uploaded workbook."""
    with sqlite3.connect(DATABASE_PATH) as connection:
        existing = {
            (
                normalize_timestamp(start),
                normalize_timestamp(end),
            )
            for start, end in connection.execute(
                """
                SELECT interval_start_utc, interval_end_utc
                FROM meter_intervals
                WHERE source = ?
                """,
                (SOURCE,),
            )
        }

    seen: set[tuple[str, str]] = set()
    duplicates = 0
    for row in rows:
        key = (normalize_timestamp(row.start), normalize_timestamp(row.end))
        if key in existing or key in seen:
            duplicates += 1
        seen.add(key)
    return duplicates


def import_excel(rows: list[ImportedInterval]) -> ImportResult:
    """Insert validated intervals; existing intervals are left unchanged."""
    with sqlite3.connect(DATABASE_PATH) as connection:
        existing = {
            (
                normalize_timestamp(start),
                normalize_timestamp(end),
            )
            for start, end in connection.execute(
                """
                SELECT interval_start_utc, interval_end_utc
                FROM meter_intervals
                WHERE source = ?
                """,
                (SOURCE,),
            )
        }
        imported = 0
        skipped = 0
        for row in rows:
            key = (normalize_timestamp(row.start), normalize_timestamp(row.end))
            if key in existing:
                skipped += 1
                continue
            connection.execute(
                """
                INSERT INTO meter_intervals (
                    interval_start_utc,
                    interval_end_utc,
                    consumption_meter_kwh,
                    feed_in_meter_kwh,
                    consumption_delta_kwh,
                    note,
                    source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.start,
                    row.end,
                    row.consumption,
                    row.feed_in,
                    row.delta,
                    row.note,
                    SOURCE,
                ),
            )
            imported += 1
            existing.add(key)
    return ImportResult(imported=imported, skipped=skipped)
