"""Water utility provider base classes and registry."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class WaterReading:
    """Water meter reading."""
    timestamp: datetime
    current_reading: float
    previous_reading: float
    consumption: float
    meter_number: str = ""


@dataclass
class AccountBalance:
    """Account balance information."""
    amount: float
    status: str
    meter_number: str = ""


@dataclass
class ProviderInfo:
    """Information about a water utility provider."""
    id: str
    name: str
    description: str
    default_country: str = "PL"


class WaterProvider(ABC):
    """Abstract base class for water utility providers."""

    @property
    @abstractmethod
    def info(self) -> ProviderInfo:
        """Return provider information."""
        pass

    @abstractmethod
    def login(self) -> bool:
        """Login to the provider's system."""
        pass

    @abstractmethod
    def get_current_reading(self) -> Optional[WaterReading]:
        """Get the most recent water reading."""
        pass

    @abstractmethod
    def get_account_balance(self) -> Optional[AccountBalance]:
        """Get account balance information."""
        pass


class ProviderRegistry:
    """Registry for water utility providers."""

    _providers: dict[str, type[WaterProvider]] = {}
    _loaded = False

    @classmethod
    def register(cls, provider_class: type[WaterProvider]) -> type[WaterProvider]:
        """Register a provider class."""
        instance = provider_class("", "")
        cls._providers[instance.info.id] = provider_class
        return provider_class

    @classmethod
    def get(cls, provider_id: str) -> Optional[type[WaterProvider]]:
        """Get a provider class by ID."""
        cls._ensure_loaded()
        return cls._providers.get(provider_id)

    @classmethod
    def list_providers(cls) -> list[ProviderInfo]:
        """List all registered providers."""
        cls._ensure_loaded()
        return [p("", "").info for p in cls._providers.values()]

    @classmethod
    def _ensure_loaded(cls):
        """Lazy load all providers."""
        if not cls._loaded:
            from .wodkan import WodkanKrzeszowiceProvider  # noqa: F401
            from .kpwik import KpwikProvider               # noqa: F401
            cls._loaded = True
