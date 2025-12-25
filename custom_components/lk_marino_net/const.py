"""Constants for LK Марьино.net integration."""
DOMAIN = "lk_marino_net"
PLATFORMS = ["sensor"]
SCAN_INTERVAL = 300  # 5 minutes

# API endpoints (these may need to be updated based on actual API)
# Try different possible URLs for Marino.net customer portal
POSSIBLE_BASE_URLS = [
    "https://lk.marino.net",
    "https://www.marino.net",
    "https://marino.net",
    "https://lk.marinonet.ru",  # Alternative domain
    "https://marinonet.ru",
    "https://my.marino.net",   # Common pattern
]
BASE_URL = "https://lk.marino.net"  # Default fallback
LOGIN_URL = f"{BASE_URL}/login"
ACCOUNT_URL = f"{BASE_URL}/api/account"

# Sensor types
SENSOR_BALANCE = "balance"
SENSOR_CUSTOMER_NUMBER = "customer_number"
SENSOR_IP_ADDRESSES = "ip_addresses"
SENSOR_BONUS_BALANCE = "bonus_balance"