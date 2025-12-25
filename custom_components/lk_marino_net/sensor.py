"""Sensor platform for LK Марьино.net integration."""
from typing import Any, Dict, List, Optional

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
    SENSOR_IP_ADDRESSES,
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
        """Return the state of the sensor."""
        return self.coordinator.data.get("balance", 0)


class MarynoNetCustomerNumberSensor(MarynoNetSensor):
    """Customer number sensor."""

    _attr_name = "Customer Number"
    _attr_unique_id = f"{DOMAIN}_{SENSOR_CUSTOMER_NUMBER}"

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
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
        """Return the state of the sensor."""
        return self.coordinator.data.get("bonus_balance", 0)


class MarynoNetIpAddressesSensor(MarynoNetSensor):
    """IP addresses sensor."""

    _attr_name = "IP Addresses"
    _attr_unique_id = f"{DOMAIN}_{SENSOR_IP_ADDRESSES}"

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        ips = self.coordinator.data.get("ip_addresses", [])
        return ", ".join(ips) if ips else "No IP addresses"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        return {
            "ip_addresses": self.coordinator.data.get("ip_addresses", []),
        }