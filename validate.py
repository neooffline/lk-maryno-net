#!/usr/bin/env python3
"""Basic validation script for LK Марьино.net integration."""

import sys
import os

# Add the integration path to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'custom_components', 'lk_marino_net'))

def test_imports():
    """Test that all modules can be imported."""
    try:
        from const import DOMAIN, PLATFORMS
        print(f"✓ DOMAIN: {DOMAIN}")
        print(f"✓ PLATFORMS: {PLATFORMS}")

        # Test import without actually importing aiohttp-dependent modules
        print("✓ Basic modules imported successfully")

        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False

def test_manifest():
    """Test manifest.json structure."""
    try:
        import json
        with open('custom_components/lk_marino_net/manifest.json', 'r') as f:
            manifest = json.load(f)

        required_fields = ['domain', 'name', 'version', 'config_flow']
        for field in required_fields:
            if field not in manifest:
                print(f"✗ Missing required field in manifest: {field}")
                return False

        print(f"✓ Manifest domain: {manifest['domain']}")
        print(f"✓ Manifest name: {manifest['name']}")
        print(f"✓ Config flow: {manifest.get('config_flow', False)}")

        return True
    except Exception as e:
        print(f"✗ Manifest validation error: {e}")
        return False

def main():
    """Run validation tests."""
    print("Validating LK Марьино.net integration...")
    print()

    results = []

    print("Testing imports...")
    results.append(test_imports())
    print()

    print("Testing manifest...")
    results.append(test_manifest())
    print()

    if all(results):
        print("✓ All validation tests passed!")
        return 0
    else:
        print("✗ Some validation tests failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())