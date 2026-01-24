#!/usr/bin/env python3
"""
End-to-end validation that Sentry queries use the correct sentry_service_name
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from config import load_config, resolve_service_names

def validate_sentry_mapping():
    """Validate the complete flow from query → service resolution → sentry mapping"""
    print("=" * 80)
    print("End-to-End Validation: Service Resolution → Sentry Mapping")
    print("=" * 80)
    print()
    
    # Load config
    app_config = load_config()
    services = app_config.services
    
    # Test cases that demonstrate the full flow
    test_cases = [
        {
            "name": "Query by Sentry project name",
            "query": "edr-proxy-service",
            "locale": None,
            "expected_log_services": ["hub-ca-edr-proxy-service", "hub-us-edr-proxy-service"],
            "expected_sentry_project": "edr-proxy-service",
            "validate": "User queries 'edr-proxy-service' → finds correct log services → maps to Sentry project"
        },
        {
            "name": "Query with locale filtering",
            "query": "auth-service",
            "locale": "ca",
            "expected_log_services": ["hub-ca-auth"],
            "expected_sentry_project": "auth-service",
            "validate": "Locale filter works with Sentry project names"
        },
        {
            "name": "Backwards compatibility - log service name",
            "query": "hub-ca-edr-proxy-service",
            "locale": None,
            "expected_log_services": ["hub-ca-edr-proxy-service"],
            "expected_sentry_project": "edr-proxy-service",
            "validate": "Traditional log service name query still works and maps correctly"
        },
        {
            "name": "Base name resolution",
            "query": "auth",
            "locale": None,
            "expected_log_services": ["hub-ca-auth", "hub-us-auth"],
            "expected_sentry_project": "auth-service",
            "validate": "Base name matches all locales and maps to single Sentry project"
        }
    ]
    
    all_passed = True
    
    for i, test in enumerate(test_cases, 1):
        print(f"Test {i}: {test['name']}")
        print("-" * 80)
        print(f"Query: '{test['query']}'" + (f" (locale={test['locale']})" if test['locale'] else ""))
        print(f"Validation: {test['validate']}")
        print()
        
        # Step 1: Resolve service names
        matched = resolve_service_names(test['query'], services, locale=test['locale'])
        matched_names = sorted([s.name for s in matched])
        expected_names = sorted(test['expected_log_services'])
        
        # Verify log services matched correctly
        if matched_names != expected_names:
            print(f"  ❌ FAIL - Log service resolution")
            print(f"     Expected: {expected_names}")
            print(f"     Got:      {matched_names}")
            all_passed = False
            print()
            continue
        
        print(f"  ✅ Step 1: Resolved to correct log services")
        print(f"     {', '.join(matched_names)}")
        print()
        
        # Step 2: Verify Sentry mapping
        sentry_projects = set()
        for service in matched:
            if service.sentry_service_name:
                sentry_projects.add(service.sentry_service_name)
        
        if len(sentry_projects) == 0:
            print(f"  ❌ FAIL - No Sentry configuration found")
            all_passed = False
            print()
            continue
        
        if len(sentry_projects) > 1:
            print(f"  ❌ FAIL - Multiple Sentry projects found (expected 1)")
            print(f"     Projects: {sorted(sentry_projects)}")
            all_passed = False
            print()
            continue
        
        actual_sentry_project = list(sentry_projects)[0]
        if actual_sentry_project != test['expected_sentry_project']:
            print(f"  ❌ FAIL - Wrong Sentry project")
            print(f"     Expected: {test['expected_sentry_project']}")
            print(f"     Got:      {actual_sentry_project}")
            all_passed = False
            print()
            continue
        
        print(f"  ✅ Step 2: Mapped to correct Sentry project")
        print(f"     Sentry project: '{actual_sentry_project}'")
        print()
        
        # Step 3: Simulate Sentry query
        print(f"  ✅ Step 3: Would query Sentry correctly")
        print(f"     sentry_api.query_issues(project='{actual_sentry_project}', ...)")
        print()
        
        print(f"  ✅✅✅ TEST PASSED")
        print()
    
    print("=" * 80)
    if all_passed:
        print("✅ ALL END-TO-END TESTS PASSED")
        print()
        print("Summary:")
        print("  • Service resolution works with sentry_service_name")
        print("  • Locale filtering applies correctly")
        print("  • Backwards compatibility maintained")
        print("  • Sentry mapping is correct for all query types")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 80)
    
    return all_passed


if __name__ == "__main__":
    success = validate_sentry_mapping()
    sys.exit(0 if success else 1)
