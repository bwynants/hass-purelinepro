"""Config flow for Novy Pureline Pro integration."""

from __future__ import annotations

import re
import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import UART_SERVICE_UUID

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .coordinator import PurelineProConfigEntry

# Sentinel value used in the device-picker to route to manual MAC entry
_MANUAL_MAC_KEY = "__manual__"


def _is_valid_mac(address: str) -> bool:
    return bool(re.match(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", address))


def _is_pureline_device(info: BluetoothServiceInfoBleak) -> bool:
    """Return True if the advertisement looks like a Novy Pureline Pro.

    Checks both the Nordic UART Service UUID (when forwarded by the BT adapter)
    and the device local name (the primary signal from ESPHome BT proxies which
    may not forward full service UUID lists).
    """
    if UART_SERVICE_UUID.lower() in [s.lower() for s in info.service_uuids]:
        return True
    name = (info.name or "").lower()
    _LOGGER.debug("name %s at %s", name, info.address)
    return name.startswith("pureline")


def _device_label(info: BluetoothServiceInfoBleak) -> str:
    """Human-readable label for a discovered BLE device."""
    name = info.name or "Pureline Pro"
    return f"{name} ({info.address})"


class PurelineProConfigFlow(ConfigFlow, domain="novy_pureline_pro"):
    """Handle a config flow for Novy Pureline Pro.

    Discovery path (automatic):
        HA detects the Nordic UART Service UUID → async_step_bluetooth
        → async_step_bluetooth_confirm → entry created.

    Manual path (user clicks "Add integration"):
        async_step_user scans HA's BT cache for matching devices and shows
        a picker.  If none are found the user can enter a MAC address directly
        via async_step_manual.
    """

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_address: str | None = None

    # ------------------------------------------------------------------
    # Automatic Bluetooth discovery (passive, triggered by HA)
    # ------------------------------------------------------------------

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Called by HA when a matching device is seen in BLE advertisements."""
        # Extra guard: local_name matchers in manifest.json could theoretically
        # match unrelated devices — verify it's actually a Pureline Pro.
        if not _is_pureline_device(discovery_info):
            return self.async_abort(reason="not_supported")

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured(
            updates={CONF_ADDRESS: discovery_info.address}
        )
        self._discovered_address = discovery_info.address
        self.context["title_placeholders"] = {
            "name": discovery_info.name or discovery_info.address
        }
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user to confirm the auto-discovered device."""
        if user_input is not None:
            return self.async_create_entry(
                title=f"Pureline Pro ({self._discovered_address})",
                data={CONF_ADDRESS: self._discovered_address},
            )
        return self.async_show_form(
            step_id="bluetooth_confirm",
            # Empty schema — HA renders a plain "Submit" button
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": self.context.get("title_placeholders", {}).get(
                    "name", self._discovered_address
                ),
                "address": self._discovered_address,
            },
        )

    # ------------------------------------------------------------------
    # User-initiated flow: show discovered devices or fall back to manual
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show a picker of nearby Pureline Pro devices.

        Reads HA's Bluetooth advertisement cache (no active scan started here;
        HA's BT scanner runs continuously in the background).  Devices that
        are already configured are excluded.  If no candidates are found the
        flow jumps directly to manual MAC entry.
        """
        already_configured: set[str] = {
            entry.data[CONF_ADDRESS]
            for entry in self._async_current_entries(include_ignore=False)
            if CONF_ADDRESS in entry.data
        }

        candidates: dict[str, str] = {
            info.address: _device_label(info)
            for info in async_discovered_service_info(self.hass, connectable=True)
            if _is_pureline_device(info)
            and info.address not in already_configured
        }

        if not candidates:
            # Nothing in the BT cache — go straight to manual entry
            return await self.async_step_manual()

        # Add a sentinel option that routes to manual MAC entry
        options = {**candidates, _MANUAL_MAC_KEY: "Enter MAC address manually…"}

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            if address == _MANUAL_MAC_KEY:
                return await self.async_step_manual()

            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured(updates={CONF_ADDRESS: address})
            name = candidates.get(address, address)
            return self.async_create_entry(
                title=f"Pureline Pro ({address})",
                data={CONF_ADDRESS: address},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_ADDRESS): vol.In(options)}
            ),
        )

    # ------------------------------------------------------------------
    # Manual MAC address entry (fallback / advanced)
    # ------------------------------------------------------------------

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow the user to type a Bluetooth MAC address directly."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()
            if not _is_valid_mac(address):
                errors[CONF_ADDRESS] = "invalid_mac"
            else:
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured(updates={CONF_ADDRESS: address})
                return self.async_create_entry(
                    title=f"Pureline Pro ({address})",
                    data={CONF_ADDRESS: address},
                )

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): str}),
            errors=errors,
        )
