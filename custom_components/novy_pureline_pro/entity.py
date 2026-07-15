"""Shared entity helpers for the Novy Pureline Pro integration."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


def build_device_info(entry_id: str) -> DeviceInfo:
    """Return the DeviceInfo shared by every Pureline Pro entity.

    All platforms expose a single logical device, so they register under the
    same identifier and metadata.
    """
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name="Novy Pureline Pro",
        manufacturer="Novy",
        model="Pureline Pro",
    )
