#!/usr/bin/env python3
"""
Test actual Sentry API integration - query real issues from auth-service
"""

import sys
import os
import asyncio
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

@pytest.mark.asyncio
async def test_sentry_api():
    """Test query_sentry_issues with real Sentry API call"""
    print("=" * 80)
    print("Sentry API Integration Test")
    print("=" * 80)
    print()
    
    # Import after path is set
    from config import load_config
    from config_loader import Config
    from sentry_integration import SentryAPI
    
    # Load environment variables from .env file
    env_config = Config()
    print("Environment loaded from .env")
    print()
    
    # Load config
    app_config = load_config()
    
    print("Configuration:")
    print("-" * 80)
    print(f"Total services: {len(app_config.services)}")
    print(f"Services with Sentry: {len([s for s in app_config.services if s.sentry_service_name])}")
    print()
    
    # Initialize Sentry API
    sentry_api = SentryAPI()
    
    print("Sentry API Status:")
    print("-" * 80)
    print(f"Available: {sentry_api.is_available()}")
    print(f"Base URL: {sentry_api.base_url}")
    print(f"Auth token: {'SET' if sentry_api.auth_token else 'NOT SET'}")
    print()
    
    if not sentry_api.is_available():
        print("❌ Sentry API not configured. Cannot test.")
        return False
    
    # Test 1: Query auth-service issues
    print("=" * 80)
    print("Test 1: Query auth-service issues (Project ID: 4)")
    print("=" * 80)
    print()
    
    print("Calling: sentry_api.query_issues(project='4', query='is:unresolved', limit=10)")
    print("-" * 80)
    
    try:
        result = sentry_api.query_issues(
            project="4",  # Project ID from DSN: /4
            query="is:unresolved",
            limit=10,
            statsPeriod="7d"
        )
        
        print(f"Success: {result.get('success')}")
        print(f"Issues returned: {len(result.get('issues', []))}")
        print()
        
        if result.get('success'):
            issues = result.get('issues', [])
            if issues:
                print("✅ TEST PASSED - Received issues from Sentry")
                print()
                print("Sample issues:")
                print("-" * 80)
                for i, issue in enumerate(issues[:3], 1):
                    print(f"\nIssue {i}:")
                    print(f"  ID: {issue.get('id')}")
                    print(f"  Title: {issue.get('title', 'No title')[:80]}")
                    print(f"  Level: {issue.get('level')}")
                    print(f"  Status: {issue.get('status')}")
                    print(f"  Count: {issue.get('count')} events")
                    print(f"  First seen: {issue.get('firstSeen')}")
                    print(f"  Last seen: {issue.get('lastSeen')}")
                
                if len(issues) > 3:
                    print(f"\n... and {len(issues) - 3} more issues")
                
                return True
            else:
                print("⚠️  SUCCESS but no issues found (project might be empty)")
                return True
        else:
            print(f"❌ TEST FAILED - API returned error")
            print(f"Error: {result.get('error')}")
            return False
            
    except Exception as e:
        print(f"❌ TEST FAILED - Exception occurred")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_sentry_api())
    
    print()
    print("=" * 80)
    if success:
        print("✅ SENTRY API TEST PASSED")
        print()
        print("The MCP tool 'query_sentry_issues' should work correctly with:")
        print('{')
        print('  "service_name": "auth-service",')
        print('  "query": "is:unresolved",')
        print('  "statsPeriod": "7d",')
        print('  "limit": 25')
        print('}')
    else:
        print("❌ SENTRY API TEST FAILED")
        print()
        print("Check:")
        print("  1. SENTRY_AUTH_TOKEN is set in config/.env")
        print("  2. SENTRY_URL is correct")
        print("  3. Network connectivity to Sentry server")
    print("=" * 80)
    
    sys.exit(0 if success else 1)
