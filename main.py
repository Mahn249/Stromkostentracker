"""Utility functions for calculating daily electricity cost contributions."""

from calendar import monthrange


def calculate_daily_cost(
    consumption_kwh: float,
    price_per_kwh: float,
    base_price_month: float,
    year: int,
    month: int,
) -> float:
    """Berechnet die Kosten eines Tages inklusive Grundpreisanteil."""

    days_in_month = monthrange(year, month)[1]

    energy_cost = consumption_kwh * price_per_kwh
    daily_base_cost = base_price_month / days_in_month

    return energy_cost + daily_base_cost


if __name__ == "__main__":
    # Beispielwerte für Oktober 2026
    consumption = 8.5
    energy_price = 0.32
    base_price = 12.00

    costs = calculate_daily_cost(
        consumption_kwh=consumption,
        price_per_kwh=energy_price,
        base_price_month=base_price,
        year=2026,
        month=10,
    )
