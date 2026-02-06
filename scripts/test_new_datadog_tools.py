#!/usr/bin/env python3
"""
Test new Datadog MCP tools in production
"""
import asyncio
import sys
import json
from datetime import datetime, timedelta, timezone

# Add src to path
sys.path.insert(0, '/home/srt/log-ai')

from src.datadog_integration import (
    init_datadog,
    list_monitors,
    search_events,
    get_service_dependencies
)
from src.config_loader import get_config

async def test_tools():
    """Test all three new Datadog tools"""
    
    print("=" * 80)
    print("Testing New Datadog Tools in Production")
    print("=" * 80)
    print()
    
    # Initialize Datadog
    print("0. Initializing Datadog...")
    print("-" * 80)
    config = get_config()
    
    if not config.dd_configured:
        print("❌ ERROR: Datadog not configured in config/.env")
        print(f"   DD_ENABLED: {config.dd_enabled}")
        print(f"   DD_API_KEY: {'set' if config.dd_api_key else 'missing'}")
        print(f"   DD_APP_KEY: {'set' if config.dd_app_key else 'missing'}")
        return
    
    init_result = init_datadog(
        api_key=config.dd_api_key,
        app_key=config.dd_app_key,
        site=config.dd_site,
        service_name=config.dd_service_name,
        env=config.dd_env,
        version=config.dd_version
    )
    
    if init_result:
        print(f"✅ Datadog initialized successfully")
    else:
        print(f"❌ Failed to initialize Datadog")
        return
    print()
    
    # Test 1: list_monitors
    print("1. Testing list_datadog_monitors (service: pason-auth-service)")
    print("-" * 80)
    result1 = list_monitors(
        service="pason-auth-service",
        status_filter=["Alert", "Warn"],
        limit=10
    )
    
    if "error" in result1:
        print(f"❌ ERROR: {result1['error']}")
        if "suggestion" in result1:
            print(f"   Suggestion: {result1['suggestion']}")
    else:
        print(f"✅ SUCCESS: Found {result1['count']} monitors")
        if result1['count'] > 0:
            for mon in result1['monitors'][:3]:
                print(f"   - [{mon['id']}] {mon['name']} ({mon['status']})")
    print()
    
    # Test 2: search_events
    print("2. Testing search_datadog_events (deployments in last 24h)")
    print("-" * 80)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=24)
    
    result2 = search_events(
        query="*",  # Simple query - search all events
        start_time=start_time,
        end_time=end_time,
        sources=["deployment"],  # Filter by deployment source
        limit=10
    )
    
    if "error" in result2:
        print(f"❌ ERROR: {result2['error']}")
        if "suggestion" in result2:
            print(f"   Suggestion: {result2['suggestion']}")
    else:
        print(f"✅ SUCCESS: Found {result2['count']} events")
        if result2['count'] > 0:
            for evt in result2['events'][:3]:
                print(f"   - [{evt['timestamp']}] {evt['title']} ({evt['source']})")
    print()
    
    # Test 3: get_service_dependencies
    print("3. Testing get_service_dependencies (service: pason-auth-service)")
    print("-" * 80)
    result3 = get_service_dependencies(service="pason-auth-service")
    
    if "error" in result3:
        print(f"❌ ERROR: {result3['error']}")
        if "suggestion" in result3:
            print(f"   Suggestion: {result3['suggestion']}")
    else:
        available = result3.get('available', True)
        if available:
            deps = result3.get('dependencies', {})
            upstream = deps.get('upstream', [])
            downstream = deps.get('downstream', [])
            print(f"✅ SUCCESS: Service found in catalog")
            print(f"   Upstream: {len(upstream)} dependencies")
            print(f"   Downstream: {len(downstream)} dependencies")
        else:
            print(f"⚠️  Service not in catalog")
            metadata = result3.get('metadata', {})
            print(f"   Note: {metadata.get('note', 'N/A')}")
    print()
    
    # Summary
    print("=" * 80)
    print("Summary:")
    print(f"  1. list_monitors: {'✅ Working' if 'error' not in result1 else '❌ Failed'}")
    print(f"  2. search_events: {'✅ Working' if 'error' not in result2 else '❌ Failed'}")
    print(f"  3. get_service_dependencies: {'✅ Working' if 'error' not in result3 else '❌ Failed'}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_tools())
