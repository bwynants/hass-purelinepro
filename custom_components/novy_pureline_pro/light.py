"""Light platform for Novy Pureline Pro."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CMD_HOOD_STATUS,
    CMD_LIGHT_BRIGHTNESS,
    CMD_LIGHT_COLORTEMP,
    CMD_LIGHT_OFF,
    CMD_LIGHT_ON_AMBI,
    CMD_LIGHT_ON_WHITE,
    COLOR_TEMP_MAX_KELVIN,
    COLOR_TEMP_MIN_KELVIN,
    DOMAIN,
)

if TYPE_CHECKING:
    from .coordinator import PurelineProConfigEntry, PurelineProCoordinator

from .purelinepro_ble import mireds_to_raw_colortemp, pct_to_raw_brightness

def _kelvin_to_mireds(kelvin: int) -> int:
    return round(1_000_000 / kelvin)


def _mireds_to_kelvin(mireds: int) -> int:
    return round(1_000_000 / mireds)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PurelineProConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([ExtractorLightEntity(entry.runtime_data, entry)])


class ExtractorLightEntity(CoordinatorEntity["PurelineProCoordinator"], LightEntity):
    """Extractor hood light entity with brightness and color temperature."""

    _attr_has_entity_name = True
    _attr_translation_key = "extractor_light"
    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP}
    _attr_min_color_temp_kelvin = COLOR_TEMP_MIN_KELVIN
    _attr_max_color_temp_kelvin = COLOR_TEMP_MAX_KELVIN

    def __init__(
        self, coordinator: PurelineProCoordinator, entry: PurelineProConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_light"
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
        return self.coordinator.data.get("light_state")

    @property
    def brightness(self) -> int | None:
        ha = self.coordinator.data.get("brightness_pct")
        if ha is None:
            return None
        return round(ha * 255)

    @property
    def color_temp_kelvin(self) -> int | None:
        mireds = self.coordinator.data.get("color_temp_mireds")
        if mireds is None:
            return None
        return _mireds_to_kelvin(mireds)

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness_ha: float | None = None
        if ATTR_BRIGHTNESS in kwargs:
            brightness_ha = kwargs[ATTR_BRIGHTNESS] / 255.0

        kelvin: int | None = kwargs.get(ATTR_COLOR_TEMP_KELVIN)
        if kelvin is not None:
            mireds = _kelvin_to_mireds(kelvin)
        else:
            stored_mireds = self.coordinator.data.get("color_temp_mireds")
            mireds = stored_mireds if stored_mireds is not None else 200

        raw_colortemp = mireds_to_raw_colortemp(mireds)

        if not self.coordinator.data.get("light_state"):
            # Choose ambi vs white based on color temperature
            # C++ sends {0} as single arg for mode-switch commands: [15;0] / [16;0]
            if raw_colortemp > 127:
                await self.coordinator.send_command(CMD_LIGHT_ON_AMBI, 0)
            else:
                await self.coordinator.send_command(CMD_LIGHT_ON_WHITE, 0)

        if brightness_ha is not None:
            raw_brightness = pct_to_raw_brightness(brightness_ha)
            if raw_brightness != self.coordinator.data.get("brightness"):
                # C++ sends {1, value}: [21;1;brightness]
                await self.coordinator.send_command(CMD_LIGHT_BRIGHTNESS, 1, raw_brightness)

        # C++ sends {1, value}: [22;1;colortemp]
        if raw_colortemp != self.coordinator.data.get("colortemp"):
            await self.coordinator.send_command(CMD_LIGHT_COLORTEMP, 1, raw_colortemp)

        await self.coordinator.send_command(CMD_HOOD_STATUS, 0)

    async def async_turn_off(self, **kwargs: Any) -> None:
        # C++ sends {0}: [36;0]
        if self.coordinator.data.get("light_state"):
            await self.coordinator.send_command(CMD_LIGHT_OFF, 0)
            await self.coordinator.send_command(CMD_HOOD_STATUS, 0)

