"""Sensor platform for Novy Pureline Pro."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

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


class OffTimerSensor(_BaseSensor):
    """Seconds remaining until the hood switches off.

    Shows the software delayed-off countdown when active, falling back to
    the device's own stop-timer (``stopping`` flag in Packet400).
    """
    _attr_translation_key = "off_timer"
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:timer-off-outline"

    def __init__(self, coordinator: PurelineProCoordinator, entry: PurelineProConfigEntry) -> None:
        super().__init__(coordinator, entry, "sensor_off_timer")

    @property
    def native_value(self) -> int | None:
        # Software countdown (delayed-off button) takes precedence.
        auto_off = self.coordinator.data.get("auto_off_seconds", 0)
        if auto_off:
            return auto_off
        # Fall back to the device's own stop-timer.
        if self.coordinator.data.get("stopping"):
            return self.coordinator.data.get("timer_seconds", 0)
        return 0


class BoostTimerSensor(_BaseSensor):
    """Seconds remaining in boost mode."""

    _attr_translation_key = "boost_timer"
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator: PurelineProCoordinator, entry: PurelineProConfigEntry) -> None:
        super().__init__(coordinator, entry, "sensor_boost_timer")

    @property
    def native_value(self) -> int | None:
        boost = self.coordinator.data.get("boost", False)
        if not boost:
            return 0
        return self.coordinator.data.get("timer_seconds", 0)


class GreaseTimerSensor(_BaseSensor):
    """Minutes until the grease filter needs cleaning."""

    _attr_translation_key = "grease_filter_timer"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:filter-outline"

    def __init__(self, coordinator: PurelineProCoordinator, entry: PurelineProConfigEntry) -> None:
        super().__init__(coordinator, entry, "sensor_grease_timer")

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("grease_minutes")


class OperatingHoursFanSensor(_BaseSensor):
    """Total fan operating time in minutes."""

    _attr_translation_key = "operating_hours_fan"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:fan-clock"

    def __init__(self, coordinator: PurelineProCoordinator, entry: PurelineProConfigEntry) -> None:
        super().__init__(coordinator, entry, "sensor_operating_fan")

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("fan_operating_minutes")


class OperatingHoursLEDSensor(_BaseSensor):
    """Total LED operating time in minutes."""

    _attr_translation_key = "operating_hours_led"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:led-on"

    def __init__(self, coordinator: PurelineProCoordinator, entry: PurelineProConfigEntry) -> None:
        super().__init__(coordinator, entry, "sensor_operating_led")

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("led_operating_minutes")
