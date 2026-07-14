"""Water Utility Sensor integration for Home Assistant."""
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import WaterUtilityCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "button"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Water Utility Sensor from a config entry."""
    _LOGGER.info("Setting up Water Utility Sensor for entry_id: %s", entry.entry_id)

    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    provider_id = entry.data.get("provider", "wik_krzeszowice")

    update_interval = timedelta(
        hours=entry.options.get("update_interval_hours", 24)
    )

    coordinator = WaterUtilityCoordinator(
        hass,
        username,
        password,
        provider_id,
        update_interval=update_interval,
    )

    # First refresh happens here, once, so every platform (sensor, button)
    # shares the same coordinator instance and initial data instead of each
    # platform creating (and separately logging in) its own copy.
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change (e.g. update interval)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
