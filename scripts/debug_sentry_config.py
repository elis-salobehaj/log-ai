#!/usr/bin/env python3
"""Debug script to check if sentry_service_name is being loaded correctly"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from config import load_config

def debug_sentry_config():
    """Check if sentry_service_name is loaded for services"""
    print("=" * 80)
    print("Debugging Sentry Configuration Loading")
    print("=" * 80)
    print()
    
    # Load config
    app_config = load_config()
    
    # Check specific services that should have Sentry config
    test_services = [
        "hub-ca-edr-proxy-service",
        "hub-us-edr-proxy-service",
        "hub-ca-auth",
        "hub-us-auth"
    ]
    
    print("Checking specific services:")
    print("-" * 80)
    for service_name in test_services:
        service = next((s for s in app_config.services if s.name == service_name), None)
        if service:
            print(f"\n✅ Found: {service.name}")
            print(f"   sentry_service_name: {service.sentry_service_name}")
            print(f"   sentry_dsn: {service.sentry_dsn[:50] if service.sentry_dsn else 'None'}...")
        else:
            print(f"\n❌ Not found: {service_name}")
    
    print()
    print("=" * 80)
    print("Summary of all services with Sentry configuration:")
    print("=" * 80)
    
    services_with_sentry = [s for s in app_config.services if s.sentry_service_name]
    services_without_sentry = [s for s in app_config.services if not s.sentry_service_name]
    
    print(f"\nServices WITH sentry_service_name: {len(services_with_sentry)}")
    for service in services_with_sentry[:10]:  # Show first 10
        print(f"  - {service.name} → {service.sentry_service_name}")
    if len(services_with_sentry) > 10:
        print(f"  ... and {len(services_with_sentry) - 10} more")
    
    print(f"\nServices WITHOUT sentry_service_name: {len(services_without_sentry)}")
    for service in services_without_sentry[:10]:  # Show first 10
        print(f"  - {service.name}")
    if len(services_without_sentry) > 10:
        print(f"  ... and {len(services_without_sentry) - 10} more")
    
    print()
    print("=" * 80)


if __name__ == "__main__":
    debug_sentry_config()
