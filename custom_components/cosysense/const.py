"""Constants and the Brick class to Home Assistant mapping."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_BILLION,
    CONCENTRATION_PARTS_PER_MILLION,
    LIGHT_LUX,
    PERCENTAGE,
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfPressure,
    UnitOfReactivePower,
    UnitOfTemperature,
    UnitOfVolume,
)

DOMAIN = "cosysense"
MANUFACTURER = "Cosysense"

DEFAULT_BASE_URL = "https://portal.cosysense.space"
DEFAULT_REGION = "eu-west-2"

CONF_CLIENT_ID = "client_id"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_BASE_URL = "base_url"
CONF_REGION = "region"
CONF_SITE_UUID = "site_uuid"
CONF_SITE_NAME = "site_name"
CONF_SITES = "sites"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_LEVELS = "levels"
CONF_STALE_HOURS = "stale_hours"

# Most sensors report every 15 min, so polling faster mostly re-reads the same
# values. Sites with push on get changes live and poll only to reconcile.
DEFAULT_SCAN_INTERVAL = 900
MIN_SCAN_INTERVAL = 60
MAX_SCAN_INTERVAL = 3600
PUSH_RECONCILE_INTERVAL = timedelta(hours=1)
DEFAULT_STALE_HOURS = 3

INVENTORY_REFRESH = timedelta(hours=1)
# The server rewrites an unchanged value at most every 300 s.
SERVER_KEEPALIVE = timedelta(seconds=300)


@dataclass(frozen=True)
class SensorKind:
    """How one Brick point class shows up in Home Assistant."""

    label: str
    device_class: SensorDeviceClass | None = None
    diagnostic: bool = False


# Brick point class -> label and device class. Unknown classes fall back to a
# generic sensor named after the class.
SENSOR_KINDS: dict[str, SensorKind] = {
    "CO2_Sensor": SensorKind("CO2", SensorDeviceClass.CO2),
    "CO2_Level_Sensor": SensorKind("CO2", SensorDeviceClass.CO2),
    "Air_Temperature_Sensor": SensorKind("Temperature", SensorDeviceClass.TEMPERATURE),
    "Temperature_Sensor": SensorKind("Temperature", SensorDeviceClass.TEMPERATURE),
    "Air_Temperature_Setpoint": SensorKind("Temperature setpoint", SensorDeviceClass.TEMPERATURE),
    "Humidity_Sensor": SensorKind("Humidity", SensorDeviceClass.HUMIDITY),
    "Air_Humidity_Sensor": SensorKind("Humidity", SensorDeviceClass.HUMIDITY),
    "Illuminance_Sensor": SensorKind("Illuminance", SensorDeviceClass.ILLUMINANCE),
    "Motion_Sensor": SensorKind("Motion count"),
    "Electrical_Energy_Usage_Sensor": SensorKind("Energy", SensorDeviceClass.ENERGY),
    "Energy_Sensor": SensorKind("Energy", SensorDeviceClass.ENERGY),
    "Active_Power_Sensor": SensorKind("Power", SensorDeviceClass.POWER),
    "Peak_Demand_Sensor": SensorKind("Peak demand", SensorDeviceClass.POWER),
    "Apparent_Power_Sensor": SensorKind("Apparent power", SensorDeviceClass.APPARENT_POWER),
    "Reactive_Power_Sensor": SensorKind("Reactive power", SensorDeviceClass.REACTIVE_POWER),
    "Current_Sensor": SensorKind("Current", SensorDeviceClass.CURRENT),
    "Voltage_Sensor": SensorKind("Voltage", SensorDeviceClass.VOLTAGE),
    "Frequency_Sensor": SensorKind("Frequency", SensorDeviceClass.FREQUENCY),
    "Power_Factor_Sensor": SensorKind("Power factor", SensorDeviceClass.POWER_FACTOR),
    "Natural_Gas_Usage_Sensor": SensorKind("Gas", SensorDeviceClass.GAS),
    "Water_Usage_Sensor": SensorKind("Water", SensorDeviceClass.WATER),
    "Meter_Register_Sensor": SensorKind("Meter reading"),
    "Valve_Position_Sensor": SensorKind("Valve position"),
    "Pressure_Sensor": SensorKind("Pressure", SensorDeviceClass.PRESSURE),
    "PM2.5_Sensor": SensorKind("PM2.5", SensorDeviceClass.PM25),
    "TVOC_Sensor": SensorKind("TVOC", SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS_PARTS),
    "Battery_Voltage_Sensor": SensorKind("Battery voltage", SensorDeviceClass.VOLTAGE, diagnostic=True),
    "Battery_Level_Sensor": SensorKind("Battery", SensorDeviceClass.BATTERY, diagnostic=True),
    "Comfort_Feedback_Sensor": SensorKind("Comfort feedback"),
}

BINARY_KINDS: dict[str, tuple[str, BinarySensorDeviceClass | None]] = {
    "Occupancy_Sensor": ("Occupancy", BinarySensorDeviceClass.OCCUPANCY),
    "Presence_Sensor": ("Presence", BinarySensorDeviceClass.PRESENCE),
    "Leak_Sensor": ("Leak", BinarySensorDeviceClass.MOISTURE),
    "On_Off_Status": ("Power", BinarySensorDeviceClass.POWER),
    "Door_Status": ("Door", BinarySensorDeviceClass.DOOR),
    "Window_Status": ("Window", BinarySensorDeviceClass.WINDOW),
    "Open_Close_Status": ("Open", BinarySensorDeviceClass.OPENING),
}

# QUDT symbol served by the API -> (Home Assistant unit, multiplier into it).
UNITS: dict[str, tuple[str | None, float]] = {
    "DEG_C": (UnitOfTemperature.CELSIUS, 1.0),
    "DEG_F": (UnitOfTemperature.FAHRENHEIT, 1.0),
    "K": (UnitOfTemperature.KELVIN, 1.0),
    "PERCENT_RH": (PERCENTAGE, 1.0),
    "PERCENT": (PERCENTAGE, 1.0),
    "PPM": (CONCENTRATION_PARTS_PER_MILLION, 1.0),
    "PPB": (CONCENTRATION_PARTS_PER_BILLION, 1.0),
    "LUX": (LIGHT_LUX, 1.0),
    "W": (UnitOfPower.WATT, 1.0),
    "KiloW": (UnitOfPower.KILO_WATT, 1.0),
    "W-HR": (UnitOfEnergy.WATT_HOUR, 1.0),
    "KiloW-HR": (UnitOfEnergy.KILO_WATT_HOUR, 1.0),
    "V-A": (UnitOfApparentPower.VOLT_AMPERE, 1.0),
    "V-A_Reactive": (UnitOfReactivePower.VOLT_AMPERE_REACTIVE, 1.0),
    "A": (UnitOfElectricCurrent.AMPERE, 1.0),
    "V": (UnitOfElectricPotential.VOLT, 1.0),
    "HZ": (UnitOfFrequency.HERTZ, 1.0),
    "M3": (UnitOfVolume.CUBIC_METERS, 1.0),
    "L": (UnitOfVolume.LITERS, 1.0),
    "HPA": (UnitOfPressure.HPA, 1.0),
    "KiloPA": (UnitOfPressure.KPA, 1.0),
    "UNITLESS": (None, 1.0),
    "NUM": (None, 1.0),
}

# Gas in litres is shown in m3: the Energy dashboard takes gas in m3.
GAS_LITRES = ("L", (UnitOfVolume.CUBIC_METERS, 0.001))

# Device classes the Energy dashboard reads; cumulative points of these classes
# are total_increasing.
ENERGY_CLASSES = frozenset({SensorDeviceClass.ENERGY, SensorDeviceClass.GAS, SensorDeviceClass.WATER})

# A Meter_Register_Sensor carries the unit of its meter, so its device class comes
# from the equipment class (Gas_Meter, Building_Water_Meter, ...).
METER_REGISTER_CLASS = "Meter_Register_Sensor"
METER_REGISTER_DEVICE_CLASSES = (
    ("Gas", SensorDeviceClass.GAS),
    ("Water", SensorDeviceClass.WATER),
    ("Electrical", SensorDeviceClass.ENERGY),
)
