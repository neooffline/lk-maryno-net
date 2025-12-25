"""Constants for LK Марьино.net integration."""
DOMAIN = "lk_marino_net"
PLATFORMS = ["sensor"]
SCAN_INTERVAL = 300  # 5 minutes

# API endpoints (these may need to be updated based on actual API)
# Try different possible URLs for Maryno.net customer portal
POSSIBLE_BASE_URLS = [
    "https://lk.maryno.net",
    "https://www.maryno.net",
    "https://maryno.net",
    "https://lk.marynunet.ru",  # Alternative domain
    "https://marynunet.ru",
    "https://my.maryno.net",   # Common pattern
]
BASE_URL = "https://lk.maryno.net"  # Default fallback - confirmed working
LOGIN_URL = f"{BASE_URL}/login"
ACCOUNT_URL = f"{BASE_URL}/api/user/all"  # Updated to correct endpoint

# Sensor types
SENSOR_BALANCE = "balance"
SENSOR_CUSTOMER_NUMBER = "customer_number"
SENSOR_IP_ADDRESSES = "ip_addresses"
SENSOR_BONUS_BALANCE = "bonus_balance"