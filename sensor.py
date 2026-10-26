"""Sensors for the Stromkostentracker integration."""

from datetime import datetime, timedelta
import logging
import sqlite3
from typing import Any

from homeassistant import config_entries
from homeassistant.components.sensor import RestoreSensor, SensorStateClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from . import tariffs
from .const import (
    CONF_METER_ENTITY,
    DEFAULT_INTERVAL_MINUTES,
    DOMAIN,
    SIGNAL_TARIFFS_UPDATED,
)
from .meter_writings import MeterSensorError, async_setup_meter_writer

_LOGGER = logging.getLogger(__name__)
_PRICE_UNIT = "EUR/kWh"


class CurrentTariffCoordinator(DataUpdateCoordinator[dict[str, Any] | None]):
    """Fetch the tariff that is valid today from the local database."""

    def __init__(
        self, hass: HomeAssistant, config_entry: config_entries.ConfigEntry
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=config_entry)

    async def _async_update_data(self) -> dict[str, Any] | None:
        """Read the current tariff without blocking Home Assistant."""
        try:
            return await self.hass.async_add_executor_job(
                tariffs.get_current_tariff, dt_util.now().date()
            )
        except (OSError, sqlite3.Error) as err:
            raise UpdateFailed(f"Unable to read the current tariff: {err}") from err


async def async_setup_entry(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the current work-price sensor."""
    coordinator = CurrentTariffCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_TARIFFS_UPDATED, coordinator.async_request_refresh
        )
    )

    if entity_id := entry.options.get(CONF_METER_ENTITY):
        interval = timedelta(minutes=DEFAULT_INTERVAL_MINUTES)
        try:
            meter_writer = await async_setup_meter_writer(hass, entity_id, interval)
        except MeterSensorError as err:
            raise ConfigEntryNotReady(str(err)) from err
        except (OSError, sqlite3.Error) as err:
            raise ConfigEntryNotReady(
                f"Unable to prepare the consumption database: {err}"
            ) from err
        entry.async_on_unload(meter_writer.async_stop)

    async def _async_refresh(_now: datetime) -> None:
        await coordinator.async_request_refresh()

    entry.async_on_unload(
        async_track_time_change(hass, _async_refresh, hour=0, minute=0, second=0)
    )
    async_add_entities([CurrentWorkPriceSensor(coordinator, entry)])


class CurrentWorkPriceSensor(
    CoordinatorEntity[CurrentTariffCoordinator], RestoreSensor
):
    """Show the work price for the tariff period valid today."""

    _attr_has_entity_name = True
    _attr_name = "Aktueller Arbeitspreis"
    _attr_native_unit_of_measurement = _PRICE_UNIT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: CurrentTariffCoordinator,
        entry: config_entries.ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_current_work_price"
        self._attr_native_value: float | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the last valid price when no tariff is currently available."""
        await super().async_added_to_hass()
        if (tariff := self.coordinator.data) is not None:
            self._attr_native_value = float(tariff["work_price_per_kwh"])
        elif (last_sensor_data := await self.async_get_last_sensor_data()) is not None:
            if last_sensor_data.native_value is not None:
                self._attr_native_value = float(last_sensor_data.native_value)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Keep the last valid price when the database has no current tariff."""
        if (tariff := self.coordinator.data) is not None:
            self._attr_native_value = float(tariff["work_price_per_kwh"])
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> float | None:
        """Return the latest valid work price."""
        return self._attr_native_value
