#!/usr/bin/env python3
"""
Demonstration of improved service resolution for Sentry queries.

This script shows how the service resolution now works with sentry_service_name mapping.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from config import load_config, resolve_service_names

def demo_service_resolution():
    """Demonstrate the service resolution flow"""
    print("=" * 80)
    print("Service Resolution Demo: How Sentry Queries Work")
    print("=" * 80)
    print()
    
    # Load config
    app_config = load_config()
    services = app_config.services
    
    # Example scenarios
    scenarios = [
        {
            "title": "Scenario 1: User queries by Sentry project name",
            "query": "edr-proxy-service",
            "locale": None,
            "explanation": "User knows the Sentry project name and wants to see all errors for it"
        },
        {
            "title": "Scenario 2: User queries by partial name with locale",
            "query": "auth-service",
            "locale": "ca",
            "explanation": "User wants only Canadian auth service errors"
        },
        {
            "title": "Scenario 3: User queries by base name (finds all locales)",
            "query": "auth",
            "locale": None,
            "explanation": "User wants all auth-related errors across all regions"
        },
        {
            "title": "Scenario 4: User queries by log service name (backwards compatible)",
            "query": "hub-ca-edr-proxy-service",
            "locale": None,
            "explanation": "Traditional query by exact log service name"
        }
    ]
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n{'=' * 80}")
        print(f"{scenario['title']}")
        print(f"{'=' * 80}")
        print(f"\nUser Query: \"{scenario['query']}\"" + 
              (f" (locale={scenario['locale']})" if scenario['locale'] else ""))
        print(f"Explanation: {scenario['explanation']}")
        print()
        
        # Step 1: Resolve service names
        print("Step 1: Resolve service name(s)")
        print("-" * 80)
        matched = resolve_service_names(scenario['query'], services, locale=scenario['locale'])
        
        if not matched:
            print("  ❌ No services found")
            continue
        
        print(f"  ✅ Found {len(matched)} service(s):")
        for service in matched:
            print(f"     - {service.name}")
        print()
        
        # Step 2: Map to Sentry projects
        print("Step 2: Map to Sentry project(s)")
        print("-" * 80)
        sentry_projects = {}
        for service in matched:
            if service.sentry_service_name:
                if service.sentry_service_name not in sentry_projects:
                    sentry_projects[service.sentry_service_name] = []
                sentry_projects[service.sentry_service_name].append(service.name)
        
        if not sentry_projects:
            print("  ⚠️  No Sentry configuration found for matched services")
        else:
            print(f"  ✅ Will query {len(sentry_projects)} Sentry project(s):")
            for sentry_name, log_services in sentry_projects.items():
                print(f"     - Sentry project: '{sentry_name}'")
                print(f"       Log services: {', '.join(log_services)}")
        print()
        
        # Step 3: Query Sentry (simulated)
        print("Step 3: Query Sentry API (simulated)")
        print("-" * 80)
        if sentry_projects:
            for sentry_name in sentry_projects.keys():
                print(f"  → sentry_api.query_issues(project='{sentry_name}', query='is:unresolved')")
            print(f"  ✅ Would aggregate results from {len(sentry_projects)} Sentry project(s)")
        else:
            print("  ⚠️  No Sentry queries would be made (no configuration)")
        
        print()
    
    print("\n" + "=" * 80)
    print("Key Benefits of This Approach:")
    print("=" * 80)
    print("""
1. Flexibility: Query by log service name OR Sentry project name
2. Deduplication: Multiple log services → single Sentry project (no duplicate queries)
3. Aggregation: Results tagged with source service for clarity
4. Locale filtering: Focus on specific regions (ca/us/na)
5. Backwards compatible: All existing queries still work
    """)
    print("=" * 80)


if __name__ == "__main__":
    demo_service_resolution()
