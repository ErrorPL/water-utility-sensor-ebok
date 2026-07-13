"""Platform for water utility sensor integration."""
import logging

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import WaterUtilityCoordinator
from .providers import ProviderRegistry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities,
):
    """Set up water utility sensor platform."""
    _LOGGER.info("Setting up water utility sensor platform for %s", config_entry.entry_id)

    # The coordinator is created once in __init__.py's async_setup_entry and
    # shared across every platform (sensor, button) for this config entry.
    coordinator: WaterUtilityCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities = []

    for meter_number in coordinator.data.readings:
        entities.append(
            WaterMeterSensor(coordinator, meter_number, config_entry.entry_id)
        )

    if coordinator.data.balance is not None:
        entities.append(
            AccountBalanceSensor(coordinator, config_entry.entry_id)
        )

    async_add_entities(entities)
    _LOGGER.info("Created %d water utility sensor entities", len(entities))


class WaterMeterSensor(SensorEntity):
    """Sensor representing a single water meter's cumulative reading."""

    def __init__(
        self,
        coordinator: WaterUtilityCoordinator,
        meter_number: str,
        entry_id: str,
    ) -> None:
        self.coordinator = coordinator
        self.meter_number = meter_number
        self.entry_id = entry_id

        self._attr_unique_id = f"{entry_id}_meter_{meter_number}"
        self._attr_name = f"Water Meter {meter_number}"
        self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
        self._attr_device_class = SensorDeviceClass.WATER
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        # Primary measurement — not diagnostic
        self._attr_entity_category = None

    @property
    def device_info(self):
        provider_class = ProviderRegistry.get(self.coordinator.provider_id)
        manufacturer = (
            provider_class("", "").info.name if provider_class else "Water Utility"
        )
        return {
            "identifiers": {(DOMAIN, self.entry_id)},
            "name": "Water Utility",
            "manufacturer": manufacturer,
            "model": "Water Meter",
        }

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def native_value(self):
        reading = self.coordinator.data.readings.get(self.meter_number)
        return reading.current_reading if reading else None

    @property
    def extra_state_attributes(self):
        reading = self.coordinator.data.readings.get(self.meter_number)
        if not reading:
            return {}
        return {
            "meter_number":     reading.meter_number,
            "previous_reading": reading.previous_reading,
            "consumption":      reading.consumption,
            "last_reading_date": reading.timestamp.isoformat(),
        }

    async def async_update(self):
        await self.coordinator.async_request_refresh()


class AccountBalanceSensor(SensorEntity):
    """Sensor representing the water account balance."""

    def __init__(
        self,
        coordinator: WaterUtilityCoordinator,
        entry_id: str,
    ) -> None:
        self.coordinator = coordinator
        self.entry_id = entry_id

        # Scoped to entry_id so multiple entries never collide
        self._attr_unique_id = f"{entry_id}_balance"
        self._attr_name = "Water Account Balance"
        self._attr_native_unit_of_measurement = "PLN"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def device_info(self):
        provider_class = ProviderRegistry.get(self.coordinator.provider_id)
        manufacturer = (
            provider_class("", "").info.name if provider_class else "Water Utility"
        )
        return {
            "identifiers": {(DOMAIN, self.entry_id)},
            "name": "Water Utility",
            "manufacturer": manufacturer,
            "model": "Account",
        }

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def native_value(self):
        balance = self.coordinator.data.balance
        return balance.amount if balance else None

    @property
    def extra_state_attributes(self):
        balance = self.coordinator.data.balance
        if not balance:
            return {}
        return {
            "status":   balance.status,
            "currency": "PLN",
        }

    async def async_update(self):
        await self.coordinator.async_request_refresh()
