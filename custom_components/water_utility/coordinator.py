"""Data coordinator for water utility sensors."""
from datetime import timedelta
import logging
from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .providers import ProviderRegistry, WaterReading, AccountBalance
from .statistics import async_import_reading

_LOGGER = logging.getLogger(__name__)


class WaterUtilityData:
    """Data container for water utility."""

    def __init__(self):
        self.readings: Dict[str, WaterReading] = {}
        self.balance: Optional[AccountBalance] = None


class WaterUtilityCoordinator(DataUpdateCoordinator[WaterUtilityData]):
    """Coordinator for water utility data.

    Supports two provider capabilities:
      - get_all_readings()  — preferred; returns all meters in one call
                              (used by providers that expose it, e.g. KpwikProvider)
      - get_current_reading() + _get_meter_ids() fallback
                              (used by providers that only implement the base ABC,
                               e.g. WodkanKrzeszowiceProvider)
    """

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        provider_id: str,
        update_interval: timedelta = timedelta(hours=24),
    ):
        self.username = username
        self.password = password
        self.provider_id = provider_id

        super().__init__(
            hass,
            _LOGGER,
            name=f"water_utility_{provider_id}",
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> WaterUtilityData:
        """Fetch data from the provider."""
        data = WaterUtilityData()

        try:
            provider_class = ProviderRegistry.get(self.provider_id)
            if not provider_class:
                raise UpdateFailed(f"Unknown provider: {self.provider_id}")

            def fetch_data():
                provider = provider_class(self.username, self.password)

                # --- Readings ---
                # Prefer get_all_readings() when the provider exposes it.
                # This avoids a separate login + meter-list call per meter.
                if hasattr(provider, "get_all_readings"):
                    readings = provider.get_all_readings()
                    for reading in readings:
                        data.readings[reading.meter_number] = reading
                else:
                    # Fallback: providers that only implement the base interface.
                    # Try to enumerate meters via _get_meter_ids if available,
                    # otherwise fall back to a single get_current_reading() call.
                    if hasattr(provider, "_get_meter_ids"):
                        meters = provider._get_meter_ids()
                        for meter_id, meter_number in meters:
                            reading = provider.get_current_reading_for_meter(meter_id)
                            if reading:
                                data.readings[reading.meter_number] = reading
                    else:
                        reading = provider.get_current_reading()
                        if reading:
                            data.readings[reading.meter_number] = reading

                # --- Balance ---
                data.balance = provider.get_account_balance()

                return data

            result = await self.hass.async_add_executor_job(fetch_data)

            # File each reading under the date the utility recorded it, not the time
            # we happened to fetch it — otherwise weeks of consumption pile up on a
            # single day in the Energy dashboard. Safe to repeat: writing the same
            # statistic_id and hour overwrites rather than accumulates.
            for reading in result.readings.values():
                async_import_reading(self.hass, self.provider_id, reading)

            return result

        except UpdateFailed:
            raise
        except Exception as exc:
            raise UpdateFailed(
                f"Failed to fetch water utility data for {self.provider_id}: {exc}"
            ) from exc
