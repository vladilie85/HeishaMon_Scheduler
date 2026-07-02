"""Constants for HeishaMon Scheduler."""

DOMAIN = "heishamon_scheduler"
VERSION = "2.2.0"  # keep in sync with manifest.json
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

# Heat pump on/off: mode blocks power the pump on if needed (and restore
# the previous power state when the block ends).
POWER_COMMAND = "SetHeatpump"
POWER_FEEDBACK = "main/Heatpump_State"

# Schedule block actions: four operating modes. Each block applies its
# mode command while active; heat/cool/dhw additionally offer an optional
# sub-setting (block value) that is sent alongside the mode.
# When a block ends the previous state is restored:
#   restore "baseline" -> value captured from the feedback topic at block
#                         start (restore_fallback if none was captured)
#   restore "fixed"    -> a fixed restore_value (e.g. heat pump back on)
ACTIONS = {
    "heat": {
        "name": "Heizen",
        "command": "SetOperationMode",
        "feedback_topic": "main/Operating_Mode_State",
        "apply_value": 0,
        "restore": "baseline",
        "state_to_command": OPMODE_STATE_TO_COMMAND,
        "power_on": True,
        "icon": "mdi:fire",
        "sub": {
            "name": "Heizkurve ± (Heat Shift)",
            "command": "SetZ1HeatRequestTemperature",
            "feedback_topic": "main/Z1_Heat_Request_Temp",
            "value_type": "number",
            "min": -5,
            "max": 5,
            "step": 1,
            "unit": "K",
            "default": 0,
            "restore": "baseline",
            "restore_fallback": 0,
        },
    },
    "cool": {
        "name": "Kühlen",
        "command": "SetOperationMode",
        "feedback_topic": "main/Operating_Mode_State",
        "apply_value": 1,
        "restore": "baseline",
        "state_to_command": OPMODE_STATE_TO_COMMAND,
        "power_on": True,
        "icon": "mdi:snowflake",
        "sub": {
            "name": "Kühl-Temperatur",
            "command": "SetZ1CoolRequestTemperature",
            "feedback_topic": "main/Z1_Cool_Request_Temp",
            "value_type": "number",
            "min": -5,
            "max": 30,
            "step": 1,
            "unit": "°C",
            "default": 18,
            "restore": "baseline",
            "restore_fallback": 0,
        },
    },
    "dhw": {
        "name": "Warmwasser",
        "command": "SetOperationMode",
        "feedback_topic": "main/Operating_Mode_State",
        "apply_value": 3,
        "restore": "baseline",
        "state_to_command": OPMODE_STATE_TO_COMMAND,
        "power_on": True,
        "icon": "mdi:water-boiler",
        "sub": {
            "name": "Soll-Temperatur",
            "command": "SetDHWTemp",
            "feedback_topic": "main/DHW_Target_Temp",
            "value_type": "number",
            "min": 40,
            "max": 75,
            "step": 1,
            "unit": "°C",
            "default": 48,
            "restore": "baseline",
        },
    },
    "off": {
        "name": "Aus",
        "command": "SetHeatpump",
        "feedback_topic": "main/Heatpump_State",
        "apply_value": 0,
        "restore": "fixed",
        "restore_value": 1,
        "icon": "mdi:power",
    },
}
