"""Constants for HeishaMon Scheduler."""

DOMAIN = "heishamon_scheduler"
DEFAULT_MQTT_BASE = "panasonic_heat_pump"
STORAGE_KEY = "heishamon_scheduler.schedules"
STORAGE_VERSION = 1
MIN_COMMAND_INTERVAL = 30  # seconds between MQTT commands

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_NAMES = {
    "mon": "Monday",
    "tue": "Tuesday",
    "wed": "Wednesday",
    "thu": "Thursday",
    "fri": "Friday",
    "sat": "Saturday",
    "sun": "Sunday",
}

CHANNELS = {
    "z1_heat_shift": {
        "name": "Z1 Heat Shift",
        "command": "SetZ1HeatRequestTemperature",
        "feedback_topic": "main/Z1_Heat_Request_Temp",
        "value_type": "number",
        "min": -5,
        "max": 5,
        "step": 1,
        "unit": "K",
        "default": 0,
        "icon": "mdi:thermometer",
    },
    "dhw_temp": {
        "name": "DHW Temperature",
        "command": "SetDHWTemp",
        "feedback_topic": "main/DHW_Target_Temp",
        "value_type": "number",
        "min": 40,
        "max": 75,
        "step": 1,
        "unit": "°C",
        "default": 48,
        "icon": "mdi:water-boiler",
    },
    "operation_mode": {
        "name": "Operating Mode",
        "command": "SetOperationMode",
        "feedback_topic": "main/Operating_Mode_State",
        "value_type": "enum",
        "options": {
            0: "Heat",
            1: "Cool",
            2: "Auto",
            3: "DHW",
            4: "Heat+DHW",
            5: "Cool+DHW",
            6: "Auto+DHW",
        },
        # Operating_Mode_State (TOP4) reports 9 states while SetOperationMode
        # (SET9) accepts 7: Auto(Heat)/Auto(Cool) both map to command "Auto".
        "state_to_command": {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 2, 8: 6},
        "default": 4,
        "icon": "mdi:heat-pump",
    },
    "z2_heat_shift": {
        "name": "Z2 Heat Shift",
        "command": "SetZ2HeatRequestTemperature",
        "feedback_topic": "main/Z2_Heat_Request_Temp",
        "value_type": "number",
        "min": -5,
        "max": 5,
        "step": 1,
        "unit": "K",
        "default": 0,
        "icon": "mdi:thermometer",
    },
    "quiet_mode": {
        "name": "Quiet Mode",
        "command": "SetQuietMode",
        "feedback_topic": "main/Quiet_Mode_Level",
        "value_type": "enum",
        "options": {
            0: "Off",
            1: "Level 1",
            2: "Level 2",
            3: "Level 3",
        },
        "default": 0,
        "icon": "mdi:volume-off",
    },
    "powerful_mode": {
        "name": "Powerful Mode",
        "command": "SetPowerfulMode",
        "feedback_topic": "main/Powerful_Mode_Time",
        "value_type": "enum",
        "options": {
            0: "Off",
            1: "30 min",
            2: "60 min",
            3: "90 min",
        },
        "default": 0,
        "icon": "mdi:rocket-launch",
    },
    "force_dhw": {
        "name": "Force DHW",
        "command": "SetForceDHW",
        "feedback_topic": "main/Force_DHW_State",
        "value_type": "enum",
        "options": {
            0: "Off",
            1: "On",
        },
        "default": 0,
        "icon": "mdi:water-boiler-alert",
    },
}

# Channels disabled by default; users opt in via config/options flow.
DEFAULT_CHANNELS = ["z1_heat_shift", "dhw_temp", "operation_mode"]

# Seconds to wait after startup before the first evaluation, so retained
# MQTT feedback/LWT messages can arrive first.
STARTUP_GRACE = 10
