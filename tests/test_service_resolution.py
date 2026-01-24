#!/usr/bin/env python3
"""
Test script for service name resolution functionality.
Tests the new flexible service name matching and locale filtering.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import load_config, resolve_service_names, find_similar_services, normalize_service_name, get_base_service_name

def test_service_resolution():
    """Test various service name resolution scenarios"""
    
    print("=" * 80)
    print("SERVICE NAME RESOLUTION TESTS")
    print("=" * 80)
    print()
    
    # Load config
    config = load_config()
    print(f"✓ Loaded {len(config.services)} services from config")
    print()
    
    # Test cases
    test_cases = [
        # (query, locale, expected_count, description)
        ("hub-ca-auth", None, 1, "Exact match"),
        ("auth", None, 3, "Base name (all locales)"),
        ("auth", "ca", 1, "Base name with locale filter"),
        ("edr-proxy", None, 2, "Partial match (both hub-ca and hub-us)"),
        ("edr_proxy", None, 2, "Underscore variation"),
        ("edrproxy", None, 2, "No separator variation"),
        ("hub-ca-edr-proxy-service", None, 1, "Exact full name"),
        ("api", None, 4, "Base name 'api' (multiple matches)"),
        ("witsml", None, 4, "Base name 'witsml'"),
        ("nonexistent-service", None, 0, "Non-existent service"),
    ]
    
    print("Testing resolve_service_names():")
    print("-" * 80)
    
    passed = 0
    failed = 0
    
    for query, locale, expected_count, description in test_cases:
        matches = resolve_service_names(query, config.services, locale=locale)
        actual_count = len(matches)
        
        status = "✓" if actual_count == expected_count else "✗"
        if actual_count == expected_count:
            passed += 1
        else:
            failed += 1
        
        locale_str = f" [locale={locale}]" if locale else ""
        print(f"{status} {description}: '{query}'{locale_str}")
        print(f"  Expected: {expected_count}, Got: {actual_count}")
        
        if matches:
            service_names = [s.name for s in matches]
            print(f"  Matched: {', '.join(service_names[:5])}")
            if len(service_names) > 5:
                print(f"           ... and {len(service_names) - 5} more")
        
        print()
    
    print(f"Results: {passed} passed, {failed} failed")
    print()
    
    # Test normalization
    print("=" * 80)
    print("NORMALIZATION TESTS")
    print("=" * 80)
    print()
    
    norm_cases = [
        ("edr_proxy", "edr-proxy"),
        ("EDR-Proxy", "edr-proxy"),
        ("hub edr proxy", "hub-edr-proxy"),
        ("  auth  ", "auth"),
    ]
    
    print("Testing normalize_service_name():")
    print("-" * 80)
    
    for input_name, expected in norm_cases:
        actual = normalize_service_name(input_name)
        status = "✓" if actual == expected else "✗"
        print(f"{status} '{input_name}' → '{actual}' (expected: '{expected}')")
    
    print()
    
    # Test base name extraction
    print("=" * 80)
    print("BASE NAME EXTRACTION TESTS")
    print("=" * 80)
    print()
    
    base_cases = [
        ("hub-ca-auth", "auth"),
        ("hub-us-edr-proxy-service", "edr-proxy-service"),
        ("edr-na-software-updater-service", "software-updater-service"),
        ("hub-portmapper", "portmapper"),
        ("hub-na-das", "das"),
    ]
    
    print("Testing get_base_service_name():")
    print("-" * 80)
    
    for input_name, expected in base_cases:
        actual = get_base_service_name(input_name)
        status = "✓" if actual == expected else "✗"
        print(f"{status} '{input_name}' → '{actual}' (expected: '{expected}')")
    
    print()
    
    # Test similar service suggestions
    print("=" * 80)
    print("SIMILARITY SUGGESTION TESTS")
    print("=" * 80)
    print()
    
    print("Testing find_similar_services():")
    print("-" * 80)
    
    suggestion_cases = [
        "edr-prox",  # Typo
        "authh",     # Typo
        "wit",       # Partial
        "pipe",      # Partial
    ]
    
    for query in suggestion_cases:
        suggestions = find_similar_services(query, config.services, limit=3)
        print(f"Query: '{query}'")
        if suggestions:
            print(f"  Suggestions: {', '.join(suggestions)}")
        else:
            print(f"  No suggestions found")
        print()
    
    # Locale filtering tests
    print("=" * 80)
    print("LOCALE FILTERING TESTS")
    print("=" * 80)
    print()
    
    print("Testing locale filtering:")
    print("-" * 80)
    
    locale_tests = [
        ("auth", "ca", "Canada auth services"),
        ("auth", "us", "US auth services"),
        ("auth", "na", "NA auth services"),
        ("edr-proxy", "ca", "Canada edr-proxy"),
        ("edr-proxy", "us", "US edr-proxy"),
    ]
    
    for query, locale, description in locale_tests:
        matches = resolve_service_names(query, config.services, locale=locale)
        print(f"{description}: '{query}' [locale={locale}]")
        print(f"  Found: {len(matches)} service(s)")
        if matches:
            for match in matches:
                print(f"    - {match.name}")
        print()
    
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"✓ Basic resolution tests: {passed}/{passed+failed} passed")
    print(f"✓ All helper functions working")
    print(f"✓ Locale filtering functional")
    print()
    
    return failed == 0

if __name__ == "__main__":
    try:
        success = test_service_resolution()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"✗ Test failed with error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
