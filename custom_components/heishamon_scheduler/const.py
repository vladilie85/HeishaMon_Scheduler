"""Constants for HeishaMon Scheduler."""

DOMAIN = "heishamon_scheduler"
VERSION = "2.0.1"  # keep in sync with manifest.json
DEFAULT_MQTT_BASE = "panasonic_heat_pump"
STORAGE_KEY = "heishamon_scheduler.schedules"
STORAGE_VERSION = 1
MIN_COMMAND_INTERVAL = 30  # seconds between MQTT commands

# Seconds to wait after startup before the first evaluation, so retained
# MQTT feedback/LWT messages can arrive first.
STARTUP_GRACE = 10

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# Operating_Mode_State (TOP4) reports 9 states while SetOperationMode
# (SET9) accepts 7: Auto(Heat)/Auto(Cool) both map to command "Auto".
OPMODE_STATE_TO_COMMAND = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 2, 8: 6}

# Schedule block actions. A block applies its command value while active;
# when it ends the previous state is restored:
#   restore "baseline" -> value captured from the feedback topic at block
#                         start (fallback value if none was captured)
#   restore "fixed"    -> a fixed restore_value (e.g. ForceDHW off)
ACTIONS = {
    "heat": {
        "name": "Heizen",
        "command": "SetOperationMode",
        "feedback_topic": "main/Operating_Mode_State",
        "value_type": "none",
        "apply_value": 0,
        "restore": "baseline",
        "state_to_command": OPMODE_STATE_TO_COMMAND,
        "icon": "mdi:fire",
    },
    "cool": {
        "name": "Kühlen",
        "command": "SetOperationMode",
        "feedback_topic": "main/Operating_Mode_State",
        "value_type": "none",
        "apply_value": 1,
        "restore": "baseline",
        "state_to_command": OPMODE_STATE_TO_COMMAND,
        "icon": "mdi:snowflake",
    },
    "dhw": {
        "name": "Warmwasser",
        "command": "SetForceDHW",
        "feedback_topic": "main/Force_DHW_State",
        "value_type": "none",
        "apply_value": 1,
        "restore": "fixed",
        "restore_value": 0,
        "icon": "mdi:water-boiler",
    },
    "off": {
        "name": "Aus",
        "command": "SetHeatpump",
        "feedback_topic": "main/Heatpump_State",
        "value_type": "none",
        "apply_value": 0,
        "restore": "fixed",
        "restore_value": 1,
        "icon": "mdi:power",
    },
    "z1_shift": {
        "name": "Heizkurve ±",
        "command": "SetZ1HeatRequestTemperature",
        "feedback_topic": "main/Z1_Heat_Request_Temp",
        "value_type": "number",
        "min": -5,
        "max": 5,
        "step": 1,
        "unit": "K",
        "default": -2,
        "restore": "baseline",
        "restore_fallback": 0,
        "icon": "mdi:thermometer",
    },
    "dhw_temp": {
        "name": "WW-Temperatur",
        "command": "SetDHWTemp",
        "feedback_topic": "main/DHW_Target_Temp",
        "value_type": "number",
        "min": 40,
        "max": 75,
        "step": 1,
        "unit": "°C",
        "default": 48,
        "restore": "baseline",
        "icon": "mdi:thermometer-water",
    },
    "quiet": {
        "name": "Flüstermodus",
        "command": "SetQuietMode",
        "feedback_topic": "main/Quiet_Mode_Level",
        "value_type": "enum",
        "options": {0: "Aus", 1: "Stufe 1", 2: "Stufe 2", 3: "Stufe 3"},
        "default": 1,
        "restore": "baseline",
        "restore_fallback": 0,
        "icon": "mdi:volume-off",
    },
}
