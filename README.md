# lk-marino-net
Home Assistant Integration for Marino.net

This integration allows you to monitor your Marino.net account information in Home Assistant, including:

- Account balance
- Customer number
- IP addresses
- Bonus balance

## Installation

### HACS (recommended)

1. Add this repository to HACS as a custom repository
2. Search for "LK Марьино.net" in HACS
3. Install the integration
4. Restart Home Assistant

### Manual

1. Copy the `custom_components/lk_marino_net` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to Settings > Devices & Services
2. Click "Add Integration"
3. Search for "LK Марьино.net"
4. Enter your Marino.net username and password
5. Click "Submit"

## Sensors

The integration provides the following sensors:

- **Balance**: Your current account balance in RUB
- **Customer Number**: Your customer account number
- **IP Addresses**: Comma-separated list of your assigned IP addresses
- **Bonus Balance**: Your bonus account balance in RUB

## Requirements

- Home Assistant 2023.6.0 or later
- Valid Marino.net account credentials

## Support

For issues and feature requests, please create an issue on GitHub.
