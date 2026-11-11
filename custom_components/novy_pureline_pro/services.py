"""Services for the Novy Pureline Pro integration.

``novy_pureline_pro.send_command`` sends a raw command frame to the hood,
useful for protocol exploration and for commands that have no entity yet.
"""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import CMD_HOOD_STATUS, DOMAIN
from .coordinator import PurelineProConfigEntry, PurelineProCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_SEND_COMMAND = "send_command"

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_COMMAND = "command"
ATTR_ARGS = "args"
ATTR_REFRESH = "refresh"

SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_COMMAND): vol.All(vol.Coerce(int), vol.Range(min=0, max=999)),
        vol.Optional(ATTR_ARGS, default=list): vol.All(cv.ensure_list, [vol.Coerce(int)]),
        vol.Optional(ATTR_REFRESH, default=True): cv.boolean,
    }
)


def _get_coordinator(hass: HomeAssistant, call: ServiceCall) -> PurelineProCoordinator:
    """Resolve the coordinator the call targets.

    With ``config_entry_id`` the entry must belong to this integration and be
    loaded. Without it the single loaded entry is used; more than one loaded
    hood then requires an explicit id.
    """
    entry_id: str | None = call.data.get(ATTR_CONFIG_ENTRY_ID)
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_found",
                translation_placeholders={"entry_id": entry_id},
            )
        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_loaded",
                translation_placeholders={"entry_id": entry_id},
            )
        return entry.runtime_data

    loaded: list[PurelineProConfigEntry] = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    if not loaded:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="no_entry_loaded"
        )
    if len(loaded) > 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="multiple_entries"
        )
    return loaded[0].runtime_data


async def _async_send_command(call: ServiceCall) -> ServiceResponse:
    """Handle ``send_command``.

    Returns the sent frame, the hood's reply and the coordinator state after
    the (optional) status refresh, when the caller asks for a response.
    """
    hass = call.hass
    coordinator = _get_coordinator(hass, call)
    command: int = call.data[ATTR_COMMAND]
    args: list[int] = call.data[ATTR_ARGS]
    frame = f"[{command};{';'.join(str(a) for a in args)}]" if args else f"[{command}]"

    _LOGGER.debug("Service send_command: %s", frame)
    reply = await coordinator.async_send_raw_command(command, *args)

    # Ask the hood for a status report so entities reflect the new state;
    # skipped when the command itself was a status request.
    refreshed = False
    if call.data[ATTR_REFRESH] and command != CMD_HOOD_STATUS:
        await coordinator.async_send_raw_command(CMD_HOOD_STATUS, 0)
        refreshed = True

    return {
        "frame": frame,
        "reply": reply,
        "refreshed": refreshed,
        "state": dict(coordinator.data),
    }


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's services (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_SEND_COMMAND):
        return
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_COMMAND,
        _async_send_command,
        schema=SEND_COMMAND_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
