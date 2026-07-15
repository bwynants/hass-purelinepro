"""Binary sensor platform for Novy Pureline Pro."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity import build_device_info

if TYPE_CHECKING:
    from .coordinator import PurelineProConfigEntry, PurelineProCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PurelineProConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([
        CleanGreaseFilterSensor(entry.runtime_data, entry),
    ])


class _BasePurelineBinarySensor(
    CoordinatorEntity["PurelineProCoordinator"], BinarySensorEntity
):
    """Shared base for Pureline Pro binary sensors."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: "PurelineProCoordinator", entry: "PurelineProConfigEntry"
    ) -> None:
        super().__init__(coordinator)
        self._attr_device_info = build_device_info(entry.entry_id)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self.coordinator.available


class CleanGreaseFilterSensor(_BasePurelineBinarySensor):
    """Binary sensor that indicates when the grease filter needs cleaning."""

    _attr_translation_key = "clean_grease_filter"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:filter-remove"

    def __init__(
        self, coordinator: "PurelineProCoordinator", entry: "PurelineProConfigEntry"
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_clean_grease"

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.get("grease_dirty")

