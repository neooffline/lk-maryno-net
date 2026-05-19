"""Sensor platform for LK Марьино.net integration."""
from typing import Any, Dict

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    SENSOR_BALANCE,
    SENSOR_BONUS_BALANCE,
    SENSOR_CUSTOMER_NUMBER,
    SENSOR_GONUS_COUNT,
    SENSOR_GONUS_DAYS_LEFT,
    SENSOR_GONUS_STATUS,
    SENSOR_IP_ADDRESSES,
    SENSOR_PLAN,
    SENSOR_PLAN_COST,
    SENSOR_PLAN_SPEED,
    SENSOR_STATUS,
)
from .coordinator import MarynoNetDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entry_id = entry.entry_id

    entities = [
        MarynoNetBalanceSensor(coordinator, entry_id),
        MarynoNetCustomerNumberSensor(coordinator, entry_id),
        MarynoNetBonusBalanceSensor(coordinator, entry_id),
        MarynoNetIpAddressesSensor(coordinator, entry_id),
        MarynoNetPlanSensor(coordinator, entry_id),
        MarynoNetPlanCostSensor(coordinator, entry_id),
        MarynoNetPlanSpeedSensor(coordinator, entry_id),
        MarynoNetStatusSensor(coordinator, entry_id),
        MarynoNetGbonusCountSensor(coordinator, entry_id),
        MarynoNetGbonusDaysLeftSensor(coordinator, entry_id),
        MarynoNetGbonusStatusSensor(coordinator, entry_id),
    ]

    async_add_entities(entities)


class MarynoNetSensor(CoordinatorEntity, SensorEntity):
    """Base sensor for Maryno.net."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MarynoNetDataUpdateCoordinator,
        entry_id: str,
        sensor_key: str,
        name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{sensor_key}"
        self._attr_name = name
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": f"LK Марьино.net ({coordinator.api_client.username})",
            "manufacturer": "Марьино.net",
            "model": "Customer Portal",
        }


class MarynoNetBalanceSensor(MarynoNetSensor):
    """Balance sensor."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "RUB"

    def __init__(self, coordinator: MarynoNetDataUpdateCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, SENSOR_BALANCE, "Balance")

    @property
    def native_value(self) -> float:
        return self.coordinator.data.get("balance", 0)


class MarynoNetCustomerNumberSensor(MarynoNetSensor):
    """Customer number sensor."""

    def __init__(self, coordinator: MarynoNetDataUpdateCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, SENSOR_CUSTOMER_NUMBER, "Customer Number")

    @property
    def native_value(self) -> str:
        return self.coordinator.data.get("customer_number", "")


class MarynoNetBonusBalanceSensor(MarynoNetSensor):
    """Bonus balance sensor."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "RUB"

    def __init__(self, coordinator: MarynoNetDataUpdateCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, SENSOR_BONUS_BALANCE, "Bonus Balance")

    @property
    def native_value(self) -> float:
        return self.coordinator.data.get("bonus_balance", 0)


class MarynoNetIpAddressesSensor(MarynoNetSensor):
    """IP addresses sensor."""

    def __init__(self, coordinator: MarynoNetDataUpdateCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, SENSOR_IP_ADDRESSES, "IP Addresses")

    @property
    def native_value(self) -> str:
        ips = self.coordinator.data.get("ip_addresses", [])
        return ", ".join(ips) if ips else "No IP addresses"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        return {
            "ip_addresses": self.coordinator.data.get("ip_addresses", []),
        }


class MarynoNetPlanSensor(MarynoNetSensor):
    """Current plan/tariff sensor."""

    def __init__(self, coordinator: MarynoNetDataUpdateCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, SENSOR_PLAN, "Plan")

    @property
    def native_value(self) -> str:
        return self.coordinator.data.get("plan", "")


class MarynoNetPlanCostSensor(MarynoNetSensor):
    """Plan cost sensor."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "RUB"

    def __init__(self, coordinator: MarynoNetDataUpdateCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, SENSOR_PLAN_COST, "Plan Cost")

    @property
    def native_value(self) -> float:
        return self.coordinator.data.get("plan_cost", 0)


class MarynoNetPlanSpeedSensor(MarynoNetSensor):
    """Plan speed sensor."""

    _attr_native_unit_of_measurement = "Kbit/s"

    def __init__(self, coordinator: MarynoNetDataUpdateCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, SENSOR_PLAN_SPEED, "Plan Speed")

    @property
    def native_value(self) -> str:
        speed = self.coordinator.data.get("plan_speed", "")
        return str(speed) if speed else ""


class MarynoNetStatusSensor(MarynoNetSensor):
    """Account status sensor."""

    def __init__(self, coordinator: MarynoNetDataUpdateCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, SENSOR_STATUS, "Status")

    @property
    def native_value(self) -> str:
        return self.coordinator.data.get("status", "")


class MarynoNetGbonusCountSensor(MarynoNetSensor):
    """G-Bonus count sensor."""

    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, coordinator: MarynoNetDataUpdateCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, SENSOR_GONUS_COUNT, "G-Bonus Count")

    @property
    def native_value(self) -> int:
        return self.coordinator.data.get("gbonus_count", 0)


class MarynoNetGbonusDaysLeftSensor(MarynoNetSensor):
    """G-Bonus days left sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "d"

    def __init__(self, coordinator: MarynoNetDataUpdateCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, SENSOR_GONUS_DAYS_LEFT, "G-Bonus Days Left")

    @property
    def native_value(self) -> int:
        return self.coordinator.data.get("gbonus_days_left", 0)


class MarynoNetGbonusStatusSensor(MarynoNetSensor):
    """G-Bonus status sensor."""

    def __init__(self, coordinator: MarynoNetDataUpdateCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, SENSOR_GONUS_STATUS, "G-Bonus Status")

    @property
    def native_value(self) -> str:
        return self.coordinator.data.get("gbonus_status", "")
