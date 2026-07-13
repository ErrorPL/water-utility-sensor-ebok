# Water Utility Sensor

Home Assistant custom integration for scraping water meter readings and account data from Polish water utility portals.

## Supported Providers

| Provider | Portal | Region |
|---|---|---|
| **WODKAN Krzeszowice** | ibo.wikkrzeszowice.pl | Krzeszowice |
| **KPWIK Kobierzyce** | ebok.kpwik.com | Gmina Kobierzyce |

## What it tracks

- **Water meter reading** (m³) — cumulative total, compatible with HA energy dashboard
- **Previous reading** and **consumption** since last read — exposed as sensor attributes
- **Account balance** (PLN) — where the provider portal exposes it

## Installation

### Via HACS (recommended)
1. Add this repository to HACS as a custom repository
2. Search for "Water Utility Sensor" and install
3. Restart Home Assistant

### Manual
1. Copy `custom_components/water_utility_sensor/` to your Home Assistant `custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Water Utility Sensor**
3. Select your water utility provider
4. Enter your portal login credentials (client code / username and password)

The update interval defaults to once a day (24 hours) and can be changed under the integration's options.

## Requirements

- Python 3.10+
- `httpx >= 0.25.0` (installed automatically by HA)

## Development

```bash
# Install dependencies
pip install httpx pytest pytest-asyncio homeassistant

# Run tests
pytest tests/
```

## Adding a new provider

1. Create `custom_components/water_utility_sensor/providers/your_provider.py`
2. Implement `WaterProvider` (see `providers/__init__.py` for the ABC)
3. Decorate the class with `@ProviderRegistry.register`
4. Add the import to `ProviderRegistry._ensure_loaded()` in `providers/__init__.py`

The config flow will automatically include the new provider in the selection list.

## License

MIT License — see [LICENSE](LICENSE)
