"""Sensor platform for LK Марьино.net integration."""
from typing import Any, Dict

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
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

    entities = [
        MarynoNetBalanceSensor(coordinator),
        MarynoNetCustomerNumberSensor(coordinator),
        MarynoNetBonusBalanceSensor(coordinator),
        MarynoNetIpAddressesSensor(coordinator),
        MarynoNetPlanSensor(coordinator),
        MarynoNetPlanCostSensor(coordinator),
        MarynoNetPlanSpeedSensor(coordinator),
        MarynoNetStatusSensor(coordinator),
        MarynoNetGbonusCountSensor(coordinator),
        MarynoNetGbonusDaysLeftSensor(coordinator),
        MarynoNetGbonusStatusSensor(coordinator),
    ]

    async_add_entities(entities)


class MarynoNetSensor(CoordinatorEntity, SensorEntity):
    """Base sensor for Maryno.net."""

    def __init__(self, coordinator: MarynoNetDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.config_entry.entry_id)},
            "name": "LK Марьино.net",
            "manufacturer": "Марьино.net",
            "model": "Customer Portal",
        }


class MarynoNetBalanceSensor(MarynoNetSensor):
    """Balance sensor."""

    _attr_name = "Balance"
    _attr_unique_id = f"{DOMAIN}_{SENSOR_BALANCE}"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "RUB"

    @property
    def native_value(self) -> float:
        return self.coordinator.data.get("balance", 0)


class MarynoNetCustomerNumberSensor(MarynoNetSensor):
    """Customer number sensor."""

    _attr_name = "Customer Number"
    _attr_unique_id = f"{DOMAIN}_{SENSOR_CUSTOMER_NUMBER}"

    @property
    def native_value(self) -> str:
        return self.coordinator.data.get("customer_number", "")


class MarynoNetBonusBalanceSensor(MarynoNetSensor):
    """Bonus balance sensor."""

    _attr_name = "Bonus Balance"
    _attr_unique_id = f"{DOMAIN}_{SENSOR_BONUS_BALANCE}"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "RUB"

    @property
    def native_value(self) -> float:
        return self.coordinator.data.get("bonus_balance", 0)


class MarynoNetIpAddressesSensor(MarynoNetSensor):
    """IP addresses sensor."""

    _attr_name = "IP Addresses"
    _attr_unique_id = f"{DOMAIN}_{SENSOR_IP_ADDRESSES}"

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

    _attr_name = "Plan"
    _attr_unique_id = f"{DOMAIN}_{SENSOR_PLAN}"

    @property
    def native_value(self) -> str:
        return self.coordinator.data.get("plan", "")


class MarynoNetPlanCostSensor(MarynoNetSensor):
    """Plan cost sensor."""

    _attr_name = "Plan Cost"
    _attr_unique_id = f"{DOMAIN}_{SENSOR_PLAN_COST}"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "RUB"

    @property
    def native_value(self) -> float:
        return self.coordinator.data.get("plan_cost", 0)


class MarynoNetPlanSpeedSensor(MarynoNetSensor):
    """Plan speed sensor."""

    _attr_name = "Plan Speed"
    _attr_unique_id = f"{DOMAIN}_{SENSOR_PLAN_SPEED}"
    _attr_native_unit_of_measurement = "Kbit/s"

    @property
    def native_value(self) -> str:
        speed = self.coordinator.data.get("plan_speed", "")
        if speed:
            return str(speed)
        return ""


class MarynoNetStatusSensor(MarynoNetSensor):
    """Account status sensor."""

    _attr_name = "Status"
    _attr_unique_id = f"{DOMAIN}_{SENSOR_STATUS}"

    @property
    def native_value(self) -> str:
        return self.coordinator.data.get("status", "")


class MarynoNetGbonusCountSensor(MarynoNetSensor):
    """G-Bonus count sensor."""

    _attr_name = "G-Bonus Count"
    _attr_unique_id = f"{DOMAIN}_{SENSOR_GONUS_COUNT}"
    _attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> int:
        return self.coordinator.data.get("gbonus_count", 0)


class MarynoNetGbonusDaysLeftSensor(MarynoNetSensor):
    """G-Bonus days left sensor."""

    _attr_name = "G-Bonus Days Left"
    _attr_unique_id = f"{DOMAIN}_{SENSOR_GONUS_DAYS_LEFT}"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "d"

    @property
    def native_value(self) -> int:
        return self.coordinator.data.get("gbonus_days_left", 0)


class MarynoNetGbonusStatusSensor(MarynoNetSensor):
    """G-Bonus status sensor."""

    _attr_name = "G-Bonus Status"
    _attr_unique_id = f"{DOMAIN}_{SENSOR_GONUS_STATUS}"

    @property
    def native_value(self) -> str:
        return self.coordinator.data.get("gbonus_status", "")
