"""Switch platform for Novy Pureline Pro."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CMD_HOOD_STATUS_402, CMD_FAN_RECIRCULATE, DOMAIN

if TYPE_CHECKING:
    from .coordinator import PurelineProConfigEntry, PurelineProCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PurelineProConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            RecirculateSwitchEntity(coordinator, entry),
        ]
    )


class _BaseSwitch(CoordinatorEntity["PurelineProCoordinator"], SwitchEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PurelineProCoordinator,
        entry: PurelineProConfigEntry,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Novy Pureline Pro",
            manufacturer="Novy",
            model="Pureline Pro",
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self.coordinator.available


class RecirculateSwitchEntity(_BaseSwitch):
    """Toggle between recirculate and exhaust mode."""

    _attr_translation_key = "recirculate"
    _attr_icon = "mdi:refresh"

    def __init__(
        self, coordinator: PurelineProCoordinator, entry: PurelineProConfigEntry
    ) -> None:
        super().__init__(coordinator, entry, "switch_recirculate")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.get("recirculate")

    async def async_turn_on(self, **kwargs: Any) -> None:
        # C++ sends {1, state}: [25;1;1]
        await self.coordinator.send_command(CMD_FAN_RECIRCULATE, 1, 1)
        await self.coordinator.send_command(CMD_HOOD_STATUS_402, 0)

    async def async_turn_off(self, **kwargs: Any) -> None:
        # C++ sends {1, state}: [25;1;0]
        await self.coordinator.send_command(CMD_FAN_RECIRCULATE, 1, 0)
        await self.coordinator.send_command(CMD_HOOD_STATUS_402, 0)
