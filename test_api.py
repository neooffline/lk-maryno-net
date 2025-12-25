#!/usr/bin/env python3
"""Test script for Maryno.net API client."""

import asyncio
import logging
import sys
import os

# Add the custom_components directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'custom_components'))

from lk_marino_net.api import MarynoNetApiClient

# Set up logging
logging.basicConfig(level=logging.DEBUG)

async def test_api():
    """Test the API client."""
    # Replace with your actual credentials
    username = "your_contract_number"
    password = "your_password"

    print(f"Testing Maryno.net API with username: {username}")

    client = MarynoNetApiClient(username, password)

    try:
        # Test authentication
        print("Authenticating...")
        await client.authenticate()
        print("✓ Authentication successful")

        # Test getting account info
        print("Getting account info...")
        data = await client.get_account_info()
        print("✓ Account info retrieved successfully")
        print(f"Balance: {data['balance']}")
        print(f"Customer number: {data['customer_number']}")
        print(f"IP addresses: {data['ip_addresses']}")
        print(f"Bonus balance: {data['bonus_balance']}")

    except Exception as e:
        print(f"✗ Test failed: {e}")
        return False

    finally:
        await client.close()

    return True

if __name__ == "__main__":
    success = asyncio.run(test_api())
    if success:
        print("\n✓ All tests passed!")
    else:
        print("\n✗ Tests failed!")
        sys.exit(1)