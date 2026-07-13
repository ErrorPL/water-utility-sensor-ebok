"""Button platform for Water Utility Sensor — manual, on-demand refresh."""
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
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
    """Set up the manual-refresh button for this config entry."""
    coordinator: WaterUtilityCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([WaterUtilityRefreshButton(coordinator, config_entry.entry_id)])


class WaterUtilityRefreshButton(ButtonEntity):
    """Button that forces an immediate data refresh, bypassing the polling schedule."""

    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: WaterUtilityCoordinator, entry_id: str) -> None:
        self.coordinator = coordinator
        self.entry_id = entry_id

        self._attr_unique_id = f"{entry_id}_refresh"
        self._attr_name = "Refresh Now"

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
        }

    @property
    def available(self) -> bool:
        # The button itself should stay pressable even if the last poll
        # failed — that's exactly when someone wants to retry manually.
        return True

    async def async_press(self) -> None:
        """Handle the button press by requesting an immediate coordinator refresh."""
        _LOGGER.info("Manual refresh requested for entry %s", self.entry_id)
        await self.coordinator.async_request_refresh()
