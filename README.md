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
5. Optionally, disable SSL certificate verification if you encounter certificate issues
6. Click "Submit"

### SSL Certificate Issues

If you encounter SSL certificate verification errors, you can disable SSL verification in the configuration. This is common with some ISP portals that use self-signed or incorrectly configured certificates. Note that disabling SSL verification reduces security, so only do this if necessary.

## Sensors

The integration provides the following sensors:

- **Balance**: Your current account balance in RUB
- **Customer Number**: Your customer account number
- **IP Addresses**: Comma-separated list of your assigned IP addresses
- **Bonus Balance**: Your bonus account balance in RUB

## Troubleshooting

### SSL Certificate Issues

If you encounter SSL certificate verification errors, try:
1. Disabling SSL verification in the integration configuration
2. Checking if your Marino.net portal uses a different domain

### Connection Issues

The integration automatically tries multiple possible URLs for the Marino.net customer portal:
- `https://lk.marino.net`
- `https://www.marino.net`
- `https://marino.net`
- `https://lk.marinonet.ru`
- `https://marinonet.ru`
- `https://my.marino.net`

If none of these work, you may need to inspect the actual login URL used by your ISP.

### Debug Logging

To enable detailed logging for troubleshooting:

1. Go to Settings > System > Logs
2. Set log level for `custom_components.lk_marino_net` to `debug`
3. Restart Home Assistant
4. Check the logs after attempting to configure the integration

This will show detailed information about:
- Which URLs are being tested
- SSL certificate issues
- API responses
- Authentication attempts
