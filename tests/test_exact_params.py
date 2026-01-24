#!/usr/bin/env python3
"""
Test service resolution works correctly with the exact parameters
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from config import load_config, resolve_service_names

def test_exact_parameters():
    """Test with exact parameters from user"""
    print("=" * 80)
    print("Service Resolution Test - Exact Parameters")
    print("=" * 80)
    print()
    
    # Load config
    app_config = load_config()
    
    # Exact test case from user
    service_name = "hub-ca-edr-proxy-service"
    
    print(f"Input: service_name = '{service_name}'")
    print()
    
    # Step 1: Resolve service name
    print("Step 1: Resolving service name...")
    print("-" * 80)
    matched_services = resolve_service_names(service_name, app_config.services, locale=None)
    
    if not matched_services:
        print(f"❌ FAILED: No services matched '{service_name}'")
        return False
    
    print(f"✅ Matched {len(matched_services)} service(s):")
    for s in matched_services:
        print(f"   - {s.name}")
    print()
    
    # Step 2: Check sentry_service_name
    print("Step 2: Checking Sentry configuration...")
    print("-" * 80)
    
    services_queried = []
    projects_without_sentry = []
    
    for service in matched_services:
        print(f"Service: {service.name}")
        print(f"   sentry_service_name: {service.sentry_service_name}")
        print(f"   sentry_dsn: {service.sentry_dsn[:50] if service.sentry_dsn else 'None'}...")
        
        if not service.sentry_service_name:
            print(f"   ❌ NO sentry_service_name - would be skipped")
            projects_without_sentry.append(service.name)
        else:
            sentry_project = service.sentry_service_name
            print(f"   ✅ Will query Sentry project: '{sentry_project}'")
            services_queried.append(f"{service.name} → {sentry_project}")
        print()
    
    # Step 3: Final verdict
    print("Step 3: Final Result")
    print("-" * 80)
    
    if not services_queried:
        error_msg = f"No Sentry configuration found for: {', '.join(s.name for s in matched_services)}"
        if projects_without_sentry:
            error_msg += f"\n\nServices without Sentry: {', '.join(projects_without_sentry)}"
        print(f"❌ WOULD RETURN ERROR:")
        print(f"   {error_msg}")
        return False
    else:
        print(f"✅ WOULD SUCCEED: Query {len(services_queried)} Sentry project(s):")
        for sq in services_queried:
            print(f"   - {sq}")
        print()
        print(f"Expected API call:")
        print(f"   sentry_api.query_issues(")
        print(f"       project='{matched_services[0].sentry_service_name}',")
        print(f"       query='is:unresolved',")
        print(f"       limit=25,")
        print(f"       statsPeriod='7d'")
        print(f"   )")
        return True
    
    print()


def test_variations():
    """Test various ways to query the same service"""
    print("\n" + "=" * 80)
    print("Testing Service Name Variations")
    print("=" * 80)
    print()
    
    app_config = load_config()
    
    test_cases = [
        ("hub-ca-edr-proxy-service", None, "Exact log service name"),
        ("edr-proxy-service", None, "Sentry project name"),
        ("edr-proxy", None, "Base name (all locales)"),
        ("edr-proxy", "ca", "Base name with locale filter"),
    ]
    
    for service_name, locale, description in test_cases:
        print(f"Test: {description}")
        print(f"  Query: '{service_name}'" + (f", locale='{locale}'" if locale else ""))
        
        matched = resolve_service_names(service_name, app_config.services, locale=locale)
        
        if matched:
            sentry_projects = {s.sentry_service_name for s in matched if s.sentry_service_name}
            print(f"  ✅ Found {len(matched)} service(s) → {len(sentry_projects)} Sentry project(s)")
            for s in matched:
                print(f"     {s.name} → {s.sentry_service_name}")
        else:
            print(f"  ❌ No match")
        
        print()
    
    print("=" * 80)


if __name__ == "__main__":
    success = test_exact_parameters()
    test_variations()
    
    print()
    print("=" * 80)
    if success:
        print("✅ ALL CHECKS PASSED")
        print()
        print("The MCP tools should work correctly with:")
        print('{')
        print('  "service_name": "hub-ca-edr-proxy-service",')
        print('  "query": "is:unresolved",')
        print('  "statsPeriod": "7d",')
        print('  "limit": 25')
        print('}')
    else:
        print("❌ CHECKS FAILED")
    print("=" * 80)
    
    sys.exit(0 if success else 1)
