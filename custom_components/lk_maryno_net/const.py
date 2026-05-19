"""Constants for LK Марьино.net integration."""
DOMAIN = "lk_maryno_net"
PLATFORMS = ["sensor"]
SCAN_INTERVAL = 900  # 15 minutes

BASE_URL = "https://lk.maryno.net"
AUTH_URL = f"{BASE_URL}/auth"
ACCOUNT_URL = f"{BASE_URL}/api/user/all"

SENSOR_BALANCE = "balance"
SENSOR_CUSTOMER_NUMBER = "customer_number"
SENSOR_IP_ADDRESSES = "ip_addresses"
SENSOR_BONUS_BALANCE = "bonus_balance"
SENSOR_PLAN = "plan"
SENSOR_PLAN_COST = "plan_cost"
SENSOR_PLAN_SPEED = "plan_speed"
SENSOR_STATUS = "status"
SENSOR_GONUS_COUNT = "gbonus_count"
SENSOR_GONUS_DAYS_LEFT = "gbonus_days_left"
SENSOR_GONUS_STATUS = "gbonus_status"