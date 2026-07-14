"""Long-term statistics for water meters.

The utility records a meter reading on a date and we only learn about it later —
often weeks later, since readings are entered by hand. If we let Home Assistant
derive statistics from the sensor's state, every reading's consumption would be
attributed to the moment HA happened to poll, producing one meaningless spike on
the Energy dashboard instead of usage on the day it occurred.

So we bypass the sensor and write *external* statistics keyed on the reading's own
timestamp. Re-writing the same hour is safe: the recorder overwrites a statistics
row with the same statistic_id and start, so repeated polls of an unchanged reading
are idempotent.
"""
import logging
import re

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .providers import WaterReading

_LOGGER = logging.getLogger(__name__)

# HA replaced the has_mean flag with mean_type; omitting it is deprecated and stops
# working in 2026.11. Fall back to has_mean on older cores that lack the enum.
try:
    from homeassistant.components.recorder.models import StatisticMeanType

    _MEAN_FIELDS = {"mean_type": StatisticMeanType.NONE}
except ImportError:  # pragma: no cover - depends on HA version
    _MEAN_FIELDS = {"has_mean": False}


def statistic_id_for(provider_id: str, meter_number: str) -> str:
    """Build the external statistic id for a meter.

    Must be "<domain>:<object_id>", with the object_id lowercase — the recorder
    rejects anything else.
    """
    slug = re.sub(r"[^a-z0-9_]+", "_", f"{provider_id}_{meter_number}".lower())
    return f"{DOMAIN}:{slug}"


def async_import_reading(
    hass: HomeAssistant,
    provider_id: str,
    reading: WaterReading,
) -> None:
    """Record one meter reading as an external statistic at its true date."""
    statistic_id = statistic_id_for(provider_id, reading.meter_number)

    # Statistics rows must start on an hour boundary. The utility gives us a date
    # with no time, so anchor to local midnight of that date.
    start = dt_util.start_of_local_day(reading.timestamp)

    # Named distinctly from the sensor entity ("Water Meter C23FA094856") so the two
    # are tellable apart in the Energy dashboard's source picker.
    label = "main" if reading.is_main else "sub-meter"

    metadata = StatisticMetaData(
        has_sum=True,
        name=f"KPWIK {reading.meter_number} ({label})",
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        **_MEAN_FIELDS,
    )

    # `sum` is the cumulative total; for a water meter that is simply the reading on
    # the dial. The Energy dashboard derives consumption from the difference between
    # consecutive sums, so it needs no separate consumption figure from us.
    statistics = [
        StatisticData(
            start=start,
            state=reading.current_reading,
            sum=reading.current_reading,
        )
    ]

    async_add_external_statistics(hass, metadata, statistics)
    _LOGGER.debug(
        "Imported statistic %s: %.2f m³ dated %s",
        statistic_id,
        reading.current_reading,
        start.date(),
    )
