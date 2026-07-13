"""pytest configuration — stub out homeassistant before any imports."""
import sys
import types


def _mod(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


# homeassistant.config_entries
_mod("homeassistant")
_mod("homeassistant.config_entries",
     ConfigEntry=type("ConfigEntry", (), {}),
     ConfigFlow=type("ConfigFlow", (), {"async_set_unique_id": lambda *a, **k: None,
                                        "_abort_if_unique_id_configured": lambda *a: None}),
     OptionsFlow=type("OptionsFlow", (), {}))
_mod("homeassistant.core", HomeAssistant=object)
_mod("homeassistant.const",
     CONF_USERNAME="username",
     CONF_PASSWORD="password",
     UnitOfVolume=type("UnitOfVolume", (), {"CUBIC_METERS": "m³"})(),
     EntityCategory=type("EntityCategory", (), {"DIAGNOSTIC": "diagnostic"})())
_mod("homeassistant.components")
_mod("homeassistant.components.sensor",
     SensorEntity=object,
     SensorStateClass=type("SensorStateClass", (), {
         "TOTAL_INCREASING": "total_increasing", "TOTAL": "total"})(),
     SensorDeviceClass=type("SensorDeviceClass", (), {
         "WATER": "water", "MONETARY": "monetary"})())
_mod("homeassistant.helpers")
class _DataUpdateCoordinator:
    """Minimal stub — supports Generic[T] subscript syntax."""
    def __init__(self, *args, **kwargs): pass
    def __init_subclass__(cls, **kwargs): super().__init_subclass__(**kwargs)
    def __class_getitem__(cls, item): return cls

_mod("homeassistant.helpers.update_coordinator",
     DataUpdateCoordinator=_DataUpdateCoordinator,
     UpdateFailed=Exception)
_mod("homeassistant.helpers.config_validation", string=str)

vol = _mod("voluptuous")
vol.Schema = lambda s, **kw: s
vol.Required = lambda k, **kw: k
vol.In = lambda x: x
