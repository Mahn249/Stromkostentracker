"""Prepare daily consumption and cost data for the Lovelace card."""

from calendar import monthrange
from datetime import UTC, date, datetime, time, timedelta, tzinfo
import math
from pathlib import Path
import sqlite3
from typing import Any

from homeassistant.util import dt as dt_util

DATABASE_PATH = Path(__file__).resolve().parents[2] / "energy_cost_tracker.db"
MIDNIGHT_READING_TOLERANCE = timedelta(minutes=20)


def _read_month_data(
    year: int, month: int, local_timezone: tzinfo
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Read intervals, tariffs, and payment periods needed for one month."""
    month_start = datetime.combine(date(year, month, 1), time.min, local_timezone)
    next_month_start = datetime.combine(
        date(year + (month == 12), month % 12 + 1, 1), time.min, local_timezone
    )
    query_start = dt_util.as_utc(month_start - MIDNIGHT_READING_TOLERANCE).isoformat()
    query_end = dt_util.as_utc(
        next_month_start + MIDNIGHT_READING_TOLERANCE
    ).isoformat()

    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(f"Datenbank nicht gefunden: {DATABASE_PATH}")

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.row_factory = sqlite3.Row
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(meter_intervals)")
        }
        if "consumption_meter_start_kwh" in columns:
            interval_query = """SELECT interval_start_utc, interval_end_utc,
                                       consumption_meter_kwh,
                                       consumption_meter_start_kwh,
                                       consumption_delta_kwh, source
                                FROM meter_intervals
                                WHERE datetime(interval_start_utc) < datetime(?)
                                  AND datetime(interval_end_utc) > datetime(?)
                                ORDER BY interval_start_utc"""
        else:
            interval_query = """SELECT interval_start_utc, interval_end_utc,
                                       consumption_meter_kwh,
                                       NULL AS consumption_meter_start_kwh,
                                       consumption_delta_kwh, source
                                FROM meter_intervals
                                WHERE datetime(interval_start_utc) < datetime(?)
                                  AND datetime(interval_end_utc) > datetime(?)
                                ORDER BY interval_start_utc"""
        intervals = [
            dict(row)
            for row in connection.execute(
                interval_query,
                (query_end, query_start),
            ).fetchall()
        ]
        tariffs = [
            dict(row)
            for row in connection.execute(
                """SELECT valid_from, valid_until, work_price_per_kwh,
                          base_price_per_month
                   FROM tariffs
                   WHERE valid_from <= ?
                     AND (valid_until IS NULL OR valid_until >= ?)
                   ORDER BY valid_from""",
                (next_month_start.date().isoformat(), month_start.date().isoformat()),
            ).fetchall()
        ]
        payments = [
            dict(row)
            for row in connection.execute(
                """SELECT valid_from, valid_until, amount_eur
                   FROM payments
                   WHERE valid_from <= ?
                     AND (valid_until IS NULL OR valid_until >= ?)
                   ORDER BY valid_from""",
                (next_month_start.date().isoformat(), month_start.date().isoformat()),
            ).fetchall()
        ]
    return intervals, tariffs, payments


def _parse_timestamp(value: str) -> datetime:
    """Parse a timestamp stored in UTC."""
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _valid_number(value: Any) -> float | None:
    """Return a finite float value or None."""
    if value is None:
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _period_value(periods: list[dict[str, Any]], day: date) -> dict[str, Any] | None:
    """Return the period active on a given date."""
    day_string = day.isoformat()
    return next(
        (
            period
            for period in periods
            if period["valid_from"] <= day_string
            and (period["valid_until"] is None or period["valid_until"] >= day_string)
        ),
        None,
    )


def _midnight_reading(
    day: date,
    readings: list[tuple[datetime, float]],
    local_timezone: tzinfo,
) -> tuple[datetime, float] | None:
    """Choose the nearest meter reading within 20 minutes of local midnight."""
    midnight = datetime.combine(day, time.min, local_timezone)
    candidates = [
        (timestamp, value)
        for timestamp, value in readings
        if abs(timestamp - midnight) <= MIDNIGHT_READING_TOLERANCE
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda reading: (
            abs(reading[0] - midnight),
            -reading[0].timestamp(),
        ),
    )


def calculate_month_data(
    year: int,
    month: int,
    intervals: list[dict[str, Any]],
    tariffs: list[dict[str, Any]],
    payments: list[dict[str, Any]],
    *,
    now: datetime,
    local_timezone: tzinfo,
) -> dict[str, Any]:
    """Calculate per-day consumption costs and daily payment allowance."""
    days_in_month = monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, days_in_month)
    today = now.astimezone(local_timezone).date()
    through_date = min(today, month_end)
    if through_date < month_start:
        through_date = month_start - timedelta(days=1)

    midnight_readings: dict[str, list[tuple[datetime, float]]] = {}
    parsed_intervals: list[tuple[datetime, datetime, dict[str, Any]]] = []
    for interval in intervals:
        start = _parse_timestamp(interval["interval_start_utc"])
        end = _parse_timestamp(interval["interval_end_utc"])
        parsed_intervals.append((start, end, interval))
        source = interval["source"]
        start_reading = _valid_number(interval.get("consumption_meter_start_kwh"))
        end_reading = _valid_number(interval.get("consumption_meter_kwh"))
        if start_reading is not None:
            midnight_readings.setdefault(source, []).append((start, start_reading))
        if end_reading is not None:
            midnight_readings.setdefault(source, []).append((end, end_reading))

    days: list[dict[str, Any]] = []
    for day_number in range(1, days_in_month + 1):
        day = date(year, month, day_number)
        tariff = _period_value(tariffs, day)
        payment = _period_value(payments, day)
        next_day = day + timedelta(days=1)

        reading_pairs = [
            (start, end)
            for source_readings in midnight_readings.values()
            if (start := _midnight_reading(day, source_readings, local_timezone))
            is not None
            and (end := _midnight_reading(next_day, source_readings, local_timezone))
            is not None
        ]
        consumption_kwh: float | None = None
        consumption_source: str | None = None
        if reading_pairs:
            start_reading, end_reading = min(
                reading_pairs,
                key=lambda pair: (
                    abs(pair[0][0] - datetime.combine(day, time.min, local_timezone))
                    + abs(
                        pair[1][0]
                        - datetime.combine(next_day, time.min, local_timezone)
                    )
                ),
            )
            difference = end_reading[1] - start_reading[1]
            if difference >= 0:
                consumption_kwh = difference
                consumption_source = "meter_readings"

        if consumption_kwh is None:
            interval_deltas = [
                delta
                for start, _end, interval in parsed_intervals
                if start.astimezone(local_timezone).date() == day
                and (delta := _valid_number(interval.get("consumption_delta_kwh")))
                is not None
            ]
            if interval_deltas:
                consumption_kwh = sum(interval_deltas)
                consumption_source = "interval_deltas"

        daily_payment_eur = (
            float(payment["amount_eur"]) / days_in_month if payment else None
        )
        base_cost_eur = (
            float(tariff["base_price_per_month"]) / days_in_month if tariff else None
        )
        work_cost_eur = (
            consumption_kwh * float(tariff["work_price_per_kwh"])
            if consumption_kwh is not None and tariff is not None
            else None
        )
        total_cost_eur = (
            work_cost_eur + base_cost_eur
            if work_cost_eur is not None and base_cost_eur is not None
            else None
        )
        days.append(
            {
                "date": day.isoformat(),
                "consumption_kwh": consumption_kwh,
                "consumption_source": consumption_source,
                "work_cost_eur": work_cost_eur,
                "base_cost_eur": base_cost_eur,
                "total_cost_eur": total_cost_eur,
                "daily_payment_eur": daily_payment_eur,
                "balance_eur": (
                    daily_payment_eur - total_cost_eur
                    if daily_payment_eur is not None and total_cost_eur is not None
                    else None
                ),
                "over_budget": (
                    total_cost_eur > daily_payment_eur
                    if total_cost_eur is not None and daily_payment_eur is not None
                    else None
                ),
            }
        )

    elapsed_days = max(0, (through_date - month_start).days + 1)
    elapsed = days[:elapsed_days]
    payment_to_date = sum(
        day["daily_payment_eur"]
        for day in elapsed
        if day["daily_payment_eur"] is not None
    )
    known_cost_days = [
        day["total_cost_eur"] for day in elapsed if day["total_cost_eur"] is not None
    ]
    costs_to_date = sum(known_cost_days)
    return {
        "year": year,
        "month": month,
        "current_year": today.year,
        "current_month": today.month,
        "days": days,
        "payment_to_date_eur": payment_to_date,
        "costs_to_date_eur": costs_to_date,
        "balance_to_date_eur": payment_to_date - costs_to_date,
        "cost_days_count": len(known_cost_days),
    }


def get_month_data(year: int, month: int, local_timezone: tzinfo) -> dict[str, Any]:
    """Load database data and calculate chart values for one month."""
    intervals, tariffs, payments = _read_month_data(year, month, local_timezone)
    return calculate_month_data(
        year,
        month,
        intervals,
        tariffs,
        payments,
        now=dt_util.now(),
        local_timezone=local_timezone,
    )


def get_year_data(year: int, local_timezone: tzinfo) -> dict[str, Any]:
    """Load and calculate monthly consumption costs for a calendar year."""
    now = dt_util.now()
    months: list[dict[str, Any]] = []
    payment_to_date = 0.0
    costs_to_date = 0.0
    cost_days_count = 0

    for month in range(1, 13):
        intervals, tariffs, payments = _read_month_data(year, month, local_timezone)
        data = calculate_month_data(
            year,
            month,
            intervals,
            tariffs,
            payments,
            now=now,
            local_timezone=local_timezone,
        )
        month_payment = sum(
            day["daily_payment_eur"]
            for day in data["days"]
            if day["daily_payment_eur"] is not None
        )
        has_payment = any(day["daily_payment_eur"] is not None for day in data["days"])
        month_costs = data["costs_to_date_eur"] if data["cost_days_count"] > 0 else None
        months.append(
            {
                "month": month,
                "costs_eur": month_costs,
                "payment_eur": month_payment if has_payment else None,
                "payment_to_date_eur": data["payment_to_date_eur"],
                "balance_eur": (
                    data["payment_to_date_eur"] - data["costs_to_date_eur"]
                    if data["cost_days_count"] > 0
                    else None
                ),
                "cost_days_count": data["cost_days_count"],
            }
        )

        if now.astimezone(local_timezone).date() >= date(year, month, 1):
            payment_to_date += data["payment_to_date_eur"]
            costs_to_date += data["costs_to_date_eur"]
            cost_days_count += data["cost_days_count"]

    return {
        "year": year,
        "current_year": now.astimezone(local_timezone).year,
        "current_month": now.astimezone(local_timezone).month,
        "months": months,
        "payment_to_date_eur": payment_to_date,
        "costs_to_date_eur": costs_to_date,
        "balance_to_date_eur": payment_to_date - costs_to_date,
        "cost_days_count": cost_days_count,
    }
