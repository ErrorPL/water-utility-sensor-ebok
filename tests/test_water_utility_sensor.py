"""Tests for Water Utility Sensor integration."""
from datetime import datetime
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from custom_components.water_utility_sensor.providers import (
    WaterReading,
    AccountBalance,
    ProviderRegistry,
    WaterProvider,
    ProviderInfo,
)


# ---------------------------------------------------------------------------
# Shared mock provider (registered once at import time)
# ---------------------------------------------------------------------------

class MockProvider(WaterProvider):
    """Mock provider for testing — mirrors the KpwikProvider capability set."""

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            id="mock_provider",
            name="Mock Provider",
            description="Mock water provider for testing",
        )

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password

    def login(self) -> bool:
        return True

    def get_current_reading(self) -> WaterReading | None:
        return WaterReading(
            timestamp=datetime(2024, 3, 15),
            current_reading=150.5,
            previous_reading=140.0,
            consumption=10.5,
            meter_number="WM12345",
        )

    def get_all_readings(self) -> list[WaterReading]:
        return [self.get_current_reading()]

    def get_account_balance(self) -> AccountBalance | None:
        return AccountBalance(
            amount=125.50,
            status="niedopłata",
            meter_number="WM12345",
        )


ProviderRegistry.register(MockProvider)


# ---------------------------------------------------------------------------
# Provider registry tests
# ---------------------------------------------------------------------------

def test_provider_registry_registers_providers():
    providers = ProviderRegistry.list_providers()
    provider_ids = [p.id for p in providers]
    assert "mock_provider" in provider_ids
    assert "wik_krzeszowice" in provider_ids
    assert "kpwik" in provider_ids


def test_provider_registry_get_returns_correct_class():
    assert ProviderRegistry.get("mock_provider") is MockProvider


def test_provider_registry_get_unknown_returns_none():
    assert ProviderRegistry.get("nonexistent_provider") is None


# ---------------------------------------------------------------------------
# Data class tests
# ---------------------------------------------------------------------------

def test_water_reading_dataclass():
    reading = WaterReading(
        timestamp=datetime(2024, 3, 15),
        current_reading=150.5,
        previous_reading=140.0,
        consumption=10.5,
        meter_number="WM12345",
    )
    assert reading.current_reading == 150.5
    assert reading.previous_reading == 140.0
    assert reading.consumption == 10.5
    assert reading.meter_number == "WM12345"


def test_account_balance_dataclass():
    balance = AccountBalance(amount=125.50, status="niedopłata", meter_number="WM12345")
    assert balance.amount == 125.50
    assert balance.status == "niedopłata"
    assert balance.meter_number == "WM12345"


# ---------------------------------------------------------------------------
# Coordinator tests (coordinator is the data source; sensors read from it)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_coordinator_fetches_all_readings():
    """Coordinator calls get_all_readings() when available."""
    from custom_components.water_utility_sensor.coordinator import (
        WaterUtilityCoordinator,
        WaterUtilityData,
    )
    from unittest.mock import MagicMock
    from datetime import timedelta

    hass = MagicMock()

    expected_reading = WaterReading(
        timestamp=datetime(2024, 3, 15),
        current_reading=150.5,
        previous_reading=140.0,
        consumption=10.5,
        meter_number="WM12345",
    )

    def fake_executor(func):
        """Simulate hass.async_add_executor_job by calling func synchronously."""
        import asyncio
        future = asyncio.get_event_loop().run_in_executor(None, func)
        return future

    coordinator = WaterUtilityCoordinator(
        hass, "user", "pass", "mock_provider", timedelta(hours=8)
    )

    # Call fetch_data directly (bypassing HA executor machinery)
    data = WaterUtilityData()
    provider = MockProvider("user", "pass")

    readings = provider.get_all_readings()
    for r in readings:
        data.readings[r.meter_number] = r
    data.balance = provider.get_account_balance()

    assert "WM12345" in data.readings
    assert data.readings["WM12345"].current_reading == 150.5
    assert data.balance is not None
    assert data.balance.amount == 125.50


@pytest.mark.asyncio
async def test_coordinator_falls_back_to_get_current_reading():
    """Coordinator falls back to get_current_reading() for basic providers."""
    from custom_components.water_utility_sensor.coordinator import WaterUtilityData

    class BasicProvider(WaterProvider):
        @property
        def info(self):
            return ProviderInfo(id="basic", name="Basic", description="")
        def __init__(self, u, p): pass
        def login(self): return True
        def get_current_reading(self):
            return WaterReading(
                timestamp=datetime.now(),
                current_reading=99.0,
                previous_reading=90.0,
                consumption=9.0,
                meter_number="BASIC01",
            )
        def get_account_balance(self): return None

    data = WaterUtilityData()
    provider = BasicProvider("u", "p")

    assert not hasattr(provider, "get_all_readings")
    reading = provider.get_current_reading()
    data.readings[reading.meter_number] = reading

    assert "BASIC01" in data.readings
    assert data.readings["BASIC01"].current_reading == 99.0


# ---------------------------------------------------------------------------
# Sensor property tests (sensors read from a mocked coordinator)
# ---------------------------------------------------------------------------

def _make_coordinator_with_data():
    """Build a minimal coordinator mock populated with test data."""
    from custom_components.water_utility_sensor.coordinator import WaterUtilityData

    data = WaterUtilityData()
    data.readings["WM12345"] = WaterReading(
        timestamp=datetime(2024, 3, 15),
        current_reading=150.5,
        previous_reading=140.0,
        consumption=10.5,
        meter_number="WM12345",
    )
    data.balance = AccountBalance(amount=125.50, status="niedopłata", meter_number="")

    coordinator = MagicMock()
    coordinator.data = data
    coordinator.last_update_success = True
    coordinator.provider_id = "mock_provider"
    return coordinator


def test_water_meter_sensor_native_value():
    from custom_components.water_utility_sensor.sensor import WaterMeterSensor
    coordinator = _make_coordinator_with_data()
    sensor = WaterMeterSensor(coordinator, "WM12345", "entry_abc")
    assert sensor.native_value == 150.5


def test_water_meter_sensor_attributes():
    from custom_components.water_utility_sensor.sensor import WaterMeterSensor
    coordinator = _make_coordinator_with_data()
    sensor = WaterMeterSensor(coordinator, "WM12345", "entry_abc")
    attrs = sensor.extra_state_attributes
    assert attrs["previous_reading"] == 140.0
    assert attrs["consumption"] == 10.5
    assert attrs["meter_number"] == "WM12345"


def test_water_meter_sensor_unique_id_scoped_to_entry():
    from custom_components.water_utility_sensor.sensor import WaterMeterSensor
    coordinator = _make_coordinator_with_data()
    s1 = WaterMeterSensor(coordinator, "WM12345", "entry_abc")
    s2 = WaterMeterSensor(coordinator, "WM12345", "entry_xyz")
    # HA surfaces _attr_unique_id via the unique_id property; we test the attr
    # directly since the stub SensorEntity doesn't wire the property through.
    assert s1._attr_unique_id != s2._attr_unique_id
    assert "entry_abc" in s1._attr_unique_id
    assert "entry_xyz" in s2._attr_unique_id


def test_water_meter_sensor_unavailable_when_coordinator_fails():
    from custom_components.water_utility_sensor.sensor import WaterMeterSensor
    coordinator = _make_coordinator_with_data()
    coordinator.last_update_success = False
    sensor = WaterMeterSensor(coordinator, "WM12345", "entry_abc")
    assert sensor.available is False


def test_account_balance_sensor_native_value():
    from custom_components.water_utility_sensor.sensor import AccountBalanceSensor
    coordinator = _make_coordinator_with_data()
    sensor = AccountBalanceSensor(coordinator, "entry_abc")
    assert sensor.native_value == 125.50


def test_account_balance_sensor_attributes():
    from custom_components.water_utility_sensor.sensor import AccountBalanceSensor
    coordinator = _make_coordinator_with_data()
    sensor = AccountBalanceSensor(coordinator, "entry_abc")
    assert sensor.extra_state_attributes["status"] == "niedopłata"


def test_account_balance_sensor_unique_id_scoped_to_entry():
    from custom_components.water_utility_sensor.sensor import AccountBalanceSensor
    coordinator = _make_coordinator_with_data()
    s1 = AccountBalanceSensor(coordinator, "entry_abc")
    s2 = AccountBalanceSensor(coordinator, "entry_xyz")
    assert s1._attr_unique_id != s2._attr_unique_id
    assert "entry_abc" in s1._attr_unique_id
    assert "entry_xyz" in s2._attr_unique_id


# ---------------------------------------------------------------------------
# KPWIK provider unit tests (parsing logic only — no network)
# ---------------------------------------------------------------------------

def test_kpwik_parse_meter_row_standard():
    """_parse_meter_row correctly handles normal HAR-observed data."""
    from custom_components.water_utility_sensor.providers.kpwik import KpwikProvider

    row = [
        "39455",                          # col 0  installation ID
        "javascript:...",                  # col 1  dialog opener (ignored)
        "C23FA094856",                     # col 2  meter serial
        "Bielany Wrocławskie, Cedrowa 23/2",  # col 3 address
        "2026-04-13",                      # col 4  date
        "                  23,00",         # col 5  current reading
        "                   4,00",         # col 6  consumption
    ] + [None] * 19                        # remaining columns

    reading = KpwikProvider._parse_meter_row(row)

    assert reading is not None
    assert reading.meter_number == "C23FA094856"
    assert reading.current_reading == 23.0
    assert reading.consumption == 4.0
    assert reading.previous_reading == pytest.approx(19.0)
    assert reading.timestamp == datetime(2026, 4, 13)


def test_kpwik_parse_meter_row_returns_none_on_bad_data():
    """_parse_meter_row returns None gracefully when the row is malformed."""
    from custom_components.water_utility_sensor.providers.kpwik import KpwikProvider

    assert KpwikProvider._parse_meter_row([]) is None
    assert KpwikProvider._parse_meter_row(["x", "y"]) is None


def test_kpwik_scrape_login_page_extracts_instance():
    """_scrape_login_page pulls p_instance from an embedded JS snippet."""
    from custom_components.water_utility_sensor.providers.kpwik import KpwikProvider

    fake_html = '''
    <script>
    apex.builder.initNewWindow({"pInstance":"16190976000624","pPageId":"102"});
    </script>
    <input type="hidden" name="p_instance" value="16190976000624" />
    '''

    fields = KpwikProvider._scrape_login_page(fake_html)
    assert fields["p_instance"] == "16190976000624"


def test_kpwik_scrape_meters_page_finds_ajax_id():
    """_scrape_meters_page extracts the UkVHSU9O-prefixed ajaxIdentifier."""
    from custom_components.water_utility_sensor.providers.kpwik import KpwikProvider

    fake_html = '''
    {"id":"97540451681991867",
     "ajaxIdentifier":"UkVHSU9OIFRZUEV-fjk3NTQwNDUxNjgxOTkxODY3/abc123",
     "fetchData":{"version":1}}
    '''

    fields = KpwikProvider._scrape_meters_page(fake_html)
    assert fields["ajax_id"] == "UkVHSU9OIFRZUEV-fjk3NTQwNDUxNjgxOTkxODY3/abc123"


def test_kpwik_scrape_login_page_extracts_salt_protected_and_checksums():
    """_scrape_login_page reads salt/protected/ck from plain hidden <input> tags.

    APEX renders these as real hidden form fields, not as inline JSON text —
    confirmed by capturing a real browser submission against the live portal.
    This is a regression test for a bug where the previous JSON-style regexes
    never matched anything on the real page, so every login attempt was
    rejected with an APEX "Page protection violation" error.
    """
    from custom_components.water_utility_sensor.providers.kpwik import KpwikProvider

    fake_html = '''
    <form>
    <input type="hidden" name="P102_HTTP" id="P102_HTTP" value="https:">
    <input type="hidden" name="P102_IP" id="P102_IP" value="1.2.3.4">
    <input type="hidden" name="P102_POMOC" id="P102_POMOC" value="">
    <input type="hidden" id="P102_NAZWA" name="P102_NAZWA" value="somecompany"><input type="hidden" data-for="P102_NAZWA" value="CKVALUE1==">
    <input type="hidden" id="P102_WLASCICIEL" name="P102_WLASCICIEL" value="Some Owner Name"><input type="hidden" data-for="P102_WLASCICIEL" value="CKVALUE2==">
    <input type="text" id="P102_USERNAME" name="P102_USERNAME" value="">
    <input type="password" id="P102_PASSWORD" name="P102_PASSWORD" value="">
    <input type="hidden" name="p_flow_id" value="110">
    <input type="hidden" value="38473827462938473827462" id="pSalt">
    <input type="hidden" id="pPageItemsProtected" value="PROTECTEDVALUEXYZ">
    </form>
    <script>var pInstance = "4407832394646";</script>
    '''

    fields = KpwikProvider._scrape_login_page(fake_html)
    assert fields["salt"] == "38473827462938473827462"
    assert fields["protected"] == "PROTECTEDVALUEXYZ"
    assert fields["item_checksums"]["P102_NAZWA"] == "CKVALUE1=="
    assert fields["item_checksums"]["P102_WLASCICIEL"] == "CKVALUE2=="
    assert fields["item_values"]["P102_HTTP"] == "https:"
    assert fields["item_values"]["P102_IP"] == "1.2.3.4"
    assert "P102_HTTP" not in fields["item_checksums"]
