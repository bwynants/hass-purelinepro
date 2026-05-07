"""Fan platform for Novy Pureline Pro."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CMD_HOOD_STATUS, CMD_FAN_SPEED, CMD_FAN_STATE, DOMAIN

if TYPE_CHECKING:
    from .coordinator import PurelineProConfigEntry, PurelineProCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PurelineProConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([ExtractorFanEntity(entry.runtime_data, entry)])


class ExtractorFanEntity(CoordinatorEntity["PurelineProCoordinator"], FanEntity):
    """Extractor fan entity for Pureline Pro."""

    _attr_has_entity_name = True
    _attr_translation_key = "extractor_fan"
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )
    _attr_speed_count = 100

    def __init__(
        self, coordinator: PurelineProCoordinator, entry: PurelineProConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_fan"
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

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.get("fan_state")

    @property
    def percentage(self) -> int | None:
        speed = self.coordinator.data.get("fan_speed")
        return int(speed) if speed is not None else None

    async def async_turn_on(self,  percentage: int | None = None,  preset_mode: str | None = None,  **kwargs: Any) -> None:
        speed = percentage or self.coordinator.data.get("fan_speed") or 50
        # C++ sends {1, state} and {1, speed}: [29;1;1] and [28;1;speed]
        if not self.coordinator.data.get("fan_state"):
            await self.coordinator.send_command(CMD_FAN_STATE, 1, 1)
        if speed != self.coordinator.data.get("fan_speed"):
            await self.coordinator.send_command(CMD_FAN_SPEED, 1, speed)
    
        await self.coordinator.send_command(CMD_HOOD_STATUS, 0)

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self.coordinator.data.get("fan_state"):
            # C++ sends {1, 0}: [29;1;0]
            await self.coordinator.send_command(CMD_FAN_STATE, 1, 0)
            await self.coordinator.send_command(CMD_HOOD_STATUS, 0)

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage == 0:
            await self.async_turn_off()
        else:
            if not self.coordinator.data.get("fan_state"):
                await self.coordinator.send_command(CMD_FAN_STATE, 1, 1)
            if percentage != self.coordinator.data.get("fan_speed"):
                await self.coordinator.send_command(CMD_FAN_SPEED, 1, percentage)

            await self.coordinator.send_command(CMD_HOOD_STATUS, 0)
