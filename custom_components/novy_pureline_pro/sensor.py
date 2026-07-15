"""Sensor platform for Novy Pureline Pro."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfTime
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
    coordinator = entry.runtime_data
    async_add_entities(
        [
            OffTimerSensor(coordinator, entry),
            BoostTimerSensor(coordinator, entry),
            GreaseTimerSensor(coordinator, entry),
            OperatingHoursFanSensor(coordinator, entry),
            OperatingHoursLEDSensor(coordinator, entry),
        ]
    )


class _BaseSensor(CoordinatorEntity["PurelineProCoordinator"], SensorEntity):
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: PurelineProCoordinator,
        entry: PurelineProConfigEntry,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"
        self._attr_device_info = build_device_info(entry.entry_id)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self.coordinator.available


class OffTimerSensor(_BaseSensor):
    """Seconds remaining until the hood switches off.

    Shows the software delayed-off countdown when active, falling back to
    the device's own stop-timer (``stopping`` flag in Packet400).
    """
    _attr_translation_key = "off_timer"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:timer-off-outline"

    def __init__(self, coordinator: PurelineProCoordinator, entry: PurelineProConfigEntry) -> None:
        super().__init__(coordinator, entry, "sensor_off_timer")

    @property
    def native_value(self) -> int | None:
        # Software countdown (delayed-off button) takes precedence.
        auto_off = self.coordinator.data.get("auto_off_seconds", 0)
        if auto_off:
            return auto_off / 60
        # Fall back to the device's own stop-timer.
        if self.coordinator.data.get("stopping"):
            value = self.coordinator.data.get("timer_seconds", 0)
            return value / 60 if value is not None else None
        return 0


class BoostTimerSensor(_BaseSensor):
    """Seconds remaining in boost mode."""

    _attr_translation_key = "boost_timer"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator: PurelineProCoordinator, entry: PurelineProConfigEntry) -> None:
        super().__init__(coordinator, entry, "sensor_boost_timer")

    @property
    def native_value(self) -> int | None:
        boost = self.coordinator.data.get("boost", False)
        if not boost:
            return 0
        value = self.coordinator.data.get("timer_seconds", 0)
        return value / 60 if value is not None else None


class GreaseTimerSensor(_BaseSensor):
    """Minutes until the grease filter needs cleaning."""

    _attr_translation_key = "grease_filter_timer"
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:filter-outline"

    def __init__(self, coordinator: PurelineProCoordinator, entry: PurelineProConfigEntry) -> None:
        super().__init__(coordinator, entry, "sensor_grease_timer")

    @property
    def native_value(self) -> int | None:
        value = self.coordinator.data.get("grease_minutes")
        return value / 60 if value is not None else None


class OperatingHoursFanSensor(_BaseSensor):
    """Total fan operating time in minutes."""

    _attr_translation_key = "operating_hours_fan"
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:fan-clock"

    def __init__(self, coordinator: PurelineProCoordinator, entry: PurelineProConfigEntry) -> None:
        super().__init__(coordinator, entry, "sensor_operating_fan")

    @property
    def native_value(self) -> int | None:
        value = self.coordinator.data.get("fan_operating_minutes")
        return value / 60 if value is not None else None




class OperatingHoursLEDSensor(_BaseSensor):
    """Total LED operating time in minutes."""

    _attr_translation_key = "operating_hours_led"
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:led-on"

    def __init__(self, coordinator: PurelineProCoordinator, entry: PurelineProConfigEntry) -> None:
        super().__init__(coordinator, entry, "sensor_operating_led")

    @property
    def native_value(self) -> int | None:
        value = self.coordinator.data.get("led_operating_minutes")
        return value / 60 if value is not None else None

