"""Novy Pureline Pro Home Assistant integration."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .coordinator import PurelineProConfigEntry, PurelineProCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: PurelineProConfigEntry) -> bool:
    """Set up Pureline Pro from a config entry."""
    coordinator = PurelineProCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PurelineProConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.disconnect()
    return unload_ok
