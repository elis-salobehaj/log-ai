#!/usr/bin/env python3
"""
Simulate the exact MCP query_sentry_issues flow to debug the issue
"""

import sys
import os
import asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from config import load_config, resolve_service_names
from config_loader import Config

async def simulate_query_sentry_issues():
    """Simulate the exact flow of query_sentry_issues handler"""
    print("=" * 80)
    print("Simulating query_sentry_issues MCP Tool Call")
    print("=" * 80)
    print()
    
    # Test case: User queries "hub-ca-edr-proxy-service"
    test_queries = [
        {"service_name": "hub-ca-edr-proxy-service", "locale": None},
        {"service_name": "edr-proxy-service", "locale": None},
        {"service_name": "edr-proxy", "locale": "ca"},
    ]
    
    # Load config (simulating what server.py does)
    app_config = load_config()
    
    for i, args in enumerate(test_queries, 1):
        service_name = args["service_name"]
        locale = args["locale"]
        
        print(f"\n{'=' * 80}")
        print(f"Test {i}: query_sentry_issues(service_name='{service_name}'" +
              (f", locale='{locale}')" if locale else ")"))
        print(f"{'=' * 80}\n")
        
        # Step 1: Resolve service name(s) - EXACTLY as handler does
        print(f"Step 1: resolve_service_names('{service_name}', services, locale={locale})")
        print("-" * 80)
        matched_services = resolve_service_names(service_name, app_config.services, locale=locale)
        
        if not matched_services:
            print(f"  ❌ No services matched")
            continue
        
        print(f"  ✅ Matched {len(matched_services)} service(s):")
        for s in matched_services:
            print(f"     - {s.name}")
        print()
        
        # Step 2: Check for sentry_service_name - EXACTLY as handler does
        print("Step 2: Check each service for sentry_service_name")
        print("-" * 80)
        
        services_queried = []
        projects_without_sentry = []
        
        for service in matched_services:
            print(f"  Service: {service.name}")
            print(f"    sentry_service_name: {service.sentry_service_name}")
            
            if not service.sentry_service_name:
                print(f"    ❌ No sentry_service_name - SKIP")
                projects_without_sentry.append(service.name)
                continue
            
            sentry_project = service.sentry_service_name
            print(f"    ✅ Will query Sentry project: '{sentry_project}'")
            services_queried.append(f"{service.name} → {sentry_project}")
        
        print()
        
        # Step 3: Check final result
        print("Step 3: Final result")
        print("-" * 80)
        
        if not services_queried:
            error_msg = f"No Sentry configuration found for: {', '.join(s.name for s in matched_services)}"
            if projects_without_sentry:
                error_msg += f"\n\nServices without Sentry: {', '.join(projects_without_sentry)}"
            print(f"  ❌ ERROR: {error_msg}")
        else:
            print(f"  ✅ SUCCESS: Would query {len(services_queried)} Sentry project(s):")
            for sq in services_queried:
                print(f"     - {sq}")
        
        print()
    
    print("=" * 80)
    print("Simulation Complete")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(simulate_query_sentry_issues())
