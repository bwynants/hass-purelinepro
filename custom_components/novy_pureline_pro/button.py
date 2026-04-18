"""Button platform for Novy Pureline Pro."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CMD_FAN_DEFAULT,
    CMD_FAN_RECIRCULATE,
    CMD_FAN_SPEED,
    CMD_FAN_STATE,
    CMD_LIGHT_DEFAULT,
    CMD_LIGHT_ON_AMBI,
    CMD_LIGHT_ON_WHITE,
    CMD_POWER,
    CMD_RESET_GREASE,
    DOMAIN,
)

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
            PowerToggleButton(coordinator, entry),
            DelayedOffButton(coordinator, entry),
            SetDefaultLightButton(coordinator, entry),
            SetDefaultSpeedButton(coordinator, entry),
            AmbiLightButton(coordinator, entry),
            WhiteLightButton(coordinator, entry),
            ResetGreaseButton(coordinator, entry),
        ]
    )


class _BaseButton(CoordinatorEntity["PurelineProCoordinator"], ButtonEntity):
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

    @property
    def available(self) -> bool:
        return self.coordinator.available


class PowerToggleButton(_BaseButton):
    """Toggle power (on/off) via cmd_power."""

    _attr_translation_key = "power_toggle"
    _attr_icon = "mdi:power"

    def __init__(self, coordinator: PurelineProCoordinator, entry: PurelineProConfigEntry) -> None:
        super().__init__(coordinator, entry, "btn_power")

    async def async_press(self) -> None:
        # C++ sends {0}: [10;0]
        await self.coordinator.send_command(CMD_POWER, 0)


class DelayedOffButton(_BaseButton):
    """Reduce fan to switch-off speed and start auto-off timer."""

    _attr_translation_key = "delayed_off"
    _attr_icon = "mdi:timer-off"

    def __init__(self, coordinator: PurelineProCoordinator, entry: PurelineProConfigEntry) -> None:
        super().__init__(coordinator, entry, "btn_delayed_off")

    async def async_press(self) -> None:
        data = self.coordinator.data

        # Switch light to ambi if it is currently on (mirrors C++ behaviour).
        if data.get("light_mode", 0) > 0:
            await self.coordinator.send_command(CMD_LIGHT_ON_AMBI, 0)

        # Reduce fan speed to the stored switch-off speed (only if faster).
        switch_off_speed = data.get("switch_off_fan_speed", 25)
        if data.get("fan_state") and data.get("fan_speed", 0) > switch_off_speed:
            await self.coordinator.send_command(CMD_FAN_SPEED, 1, switch_off_speed)

        # Start the software countdown (only meaningful if fan is on).
        # 30 min in recirculate mode, 5 min otherwise — same as C++.
        if data.get("fan_state"):
            duration = 30 * 60 if data.get("recirculate") else 5 * 60
            self.coordinator.start_auto_off(duration)


class SetDefaultLightButton(_BaseButton):
    """Save current light settings as default."""

    _attr_translation_key = "set_default_light"
    _attr_icon = "mdi:lightbulb-auto"

    def __init__(self, coordinator: PurelineProCoordinator, entry: PurelineProConfigEntry) -> None:
        super().__init__(coordinator, entry, "btn_default_light")

    async def async_press(self) -> None:
        mode = self.coordinator.data.get("light_mode", 1)
        # C++ sends {1, lightmode}: [42;1;mode]
        await self.coordinator.send_command(CMD_LIGHT_DEFAULT, 1, mode)


class SetDefaultSpeedButton(_BaseButton):
    """Save current fan speed as default."""

    _attr_translation_key = "set_default_speed"
    _attr_icon = "mdi:fan-auto"

    def __init__(self, coordinator: PurelineProCoordinator, entry: PurelineProConfigEntry) -> None:
        super().__init__(coordinator, entry, "btn_default_speed")

    async def async_press(self) -> None:
        # C++ sends {0}: [41;0]
        await self.coordinator.send_command(CMD_FAN_DEFAULT, 0)


class AmbiLightButton(_BaseButton):
    """Switch light to ambi (warm/indirect) preset."""

    _attr_translation_key = "ambi_light"
    _attr_icon = "mdi:lightbulb-variant"

    def __init__(self, coordinator: PurelineProCoordinator, entry: PurelineProConfigEntry) -> None:
        super().__init__(coordinator, entry, "btn_ambi_light")

    async def async_press(self) -> None:
        # C++ sends {0}: [15;0]
        await self.coordinator.send_command(CMD_LIGHT_ON_AMBI, 0)


class WhiteLightButton(_BaseButton):
    """Switch light to white (functional) preset."""

    _attr_translation_key = "white_light"
    _attr_icon = "mdi:lightbulb"

    def __init__(self, coordinator: PurelineProCoordinator, entry: PurelineProConfigEntry) -> None:
        super().__init__(coordinator, entry, "btn_white_light")

    async def async_press(self) -> None:
        # C++ sends {0}: [16;0]
        await self.coordinator.send_command(CMD_LIGHT_ON_WHITE, 0)


class ResetGreaseButton(_BaseButton):
    """Reset the grease filter cleaning reminder."""

    _attr_translation_key = "reset_grease_filter"
    _attr_icon = "mdi:filter-check"

    def __init__(self, coordinator: PurelineProCoordinator, entry: PurelineProConfigEntry) -> None:
        super().__init__(coordinator, entry, "btn_reset_grease")

    async def async_press(self) -> None:
        # No ACK expected for this command; C++ sends {0}: [23;0]
        await self.coordinator.send_command(CMD_RESET_GREASE, 0)
