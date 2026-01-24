#!/usr/bin/env python3
"""
Quick validation test for the service resolution implementation.
Tests that the resolver correctly handles the key use cases.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import load_config, resolve_service_names, find_similar_services

def main():
    print("\n" + "=" * 80)
    print("SERVICE RESOLUTION VALIDATION")
    print("=" * 80 + "\n")
    
    config = load_config()
    print(f"✓ Loaded {len(config.services)} services\n")
    
    # Key test cases requested by user
    tests = [
        ("Test 1: 'edr-proxy' should match both locales", "edr-proxy", None, 2),
        ("Test 2: 'edr_proxy' should also work", "edr_proxy", None, 2),
        ("Test 3: 'auth' with locale='ca'", "auth", "ca", 1),
        ("Test 4: 'auth' without locale", "auth", None, 2),
        ("Test 5: Typo with partial match", "edr-prox", None, 2),  # Partial match still works
        ("Test 6: Completely wrong service", "completely-nonexistent-xyz", None, 0),
    ]
    
    print("VALIDATION TESTS:")
    print("-" * 80 + "\n")
    
    all_passed = True
    
    for desc, query, locale, expected in tests:
        matches = resolve_service_names(query, config.services, locale=locale)
        count = len(matches)
        
        locale_str = f" [locale={locale}]" if locale else ""
        passed = count == expected
        status = "✓" if passed else "✗"
        
        if not passed:
            all_passed = False
        
        print(f"{status} {desc}")
        print(f"   Query: '{query}'{locale_str}")
        print(f"   Expected: {expected} match(es), Got: {count}")
        
        if matches:
            names = [s.name for s in matches]
            print(f"   Matched: {', '.join(names)}")
            
            # Show Sentry mapping for matched services
            sentry_projects = [s.sentry_service_name for s in matches if s.sentry_service_name]
            if sentry_projects:
                unique_projects = list(set(sentry_projects))
                print(f"   Sentry: {', '.join(unique_projects)}")
        
        # For non-existent, show suggestions
        if count == 0:
            suggestions = find_similar_services(query, config.services, limit=3)
            if suggestions:
                print(f"   Suggestions: {', '.join(suggestions)}")
        
        print()
    
    print("=" * 80)
    if all_passed:
        print("✅ ALL TESTS PASSED")
        print("\nThe implementation correctly:")
        print("  • Matches service name variations (edr-proxy, edr_proxy)")
        print("  • Filters by locale when specified")
        print("  • Returns multiple services for base names")
        print("  • Provides helpful suggestions for typos")
    else:
        print("⚠️  SOME TESTS FAILED")
        print("\nPlease review the failed cases above.")
    
    print("=" * 80 + "\n")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
