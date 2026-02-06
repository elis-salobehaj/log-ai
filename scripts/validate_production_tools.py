#!/usr/bin/env python3
"""
Production Validation Script for LogAI MCP Tools

Tests all MCP tools against production environment with hub-ca-auth service.
Reports pass/fail status, response times, and sample data.

Usage:
    python scripts/validate_production_tools.py
    python scripts/validate_production_tools.py --verbose
    python scripts/validate_production_tools.py --service hub-ca-auth
"""
import sys
import time
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config_loader import get_config
from src.sentry_integration import get_sentry_api
from src.datadog_integration import init_datadog, query_apm_traces, query_metrics, query_logs


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format"""
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    return f"{seconds:.2f}s"


def test_search_logs(service: str, verbose: bool = False) -> dict:
    """Test search_logs tool"""
    print(f"\n{'='*80}")
    print(f"TEST 1: search_logs (service={service})")
    print(f"{'='*80}")
    
    try:
        import asyncio
        from src.server import search_single_service, ProgressTracker
        from src.config import load_config, find_log_files
        
        config = load_config()
        
        # Search for ERROR logs in last hour
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=1)
        
        # Find the service config
        target_service = next((s for s in config.services if s.name == service), None)
        if not target_service:
            print(f"❌ ERROR: Service {service} not found in configuration")
            return {"status": "ERROR", "error": f"Service {service} not found"}
        
        # Find log files
        files = find_log_files(
            target_service,
            start_hour=start_time,
            end_hour=end_time
        )
        
        # Create time range dict
        time_range = {
            "start_datetime": start_time,
            "end_datetime": end_time
        }
        
        # Create progress tracker with correct params
        progress = ProgressTracker(total_files=len(files), services=[service])
        
        # Create semaphore
        semaphore = asyncio.Semaphore(5)
        
        start = time.time()
        
        # Run async search function
        matches = asyncio.run(search_single_service(
            service_name=service,
            query="ERROR",
            config=config,
            time_range=time_range,
            progress=progress,
            semaphore=semaphore
        ))
        
        duration = time.time() - start
        
        match_count = len(matches)
        print(f"✅ PASSED: Found {match_count} ERROR logs in {format_duration(duration)}")
        print(f"   Searched {len(files)} log files")
        
        if verbose and matches:
            print("\nSample matches:")
            for i, match in enumerate(matches[:3], 1):
                # Handle both dict and string formats
                if isinstance(match, dict):
                    content = str(match.get("content", match))[:100]
                else:
                    content = str(match)[:100]
                print(f"  {i}. {content}")
        
        return {"status": "PASSED", "match_count": match_count, "duration": duration}
        
    except Exception as e:
        import traceback
        print(f"❌ ERROR: {str(e)}")
        if verbose:
            traceback.print_exc()
        return {"status": "ERROR", "error": str(e)}


def test_sentry_issues(service: str, verbose: bool = False) -> dict:
    """Test query_sentry_issues tool"""
    print(f"\n{'='*80}")
    print(f"TEST 2: query_sentry_issues (service={service})")
    print(f"{'='*80}")
    
    try:
        api = get_sentry_api()
        
        start = time.time()
        result = api.query_issues(
            service_name=service.replace("hub-ca-", "").replace("hub-us-", "").replace("hub-na-", ""),
            query="is:unresolved",
            limit=5,
            statsPeriod="24h"
        )
        duration = time.time() - start
        
        if "error" in result:
            print(f"❌ FAILED: {result['error']}")
            return {"status": "FAILED", "error": result['error'], "duration": duration}
        
        issue_count = result.get("count", 0)
        print(f"✅ PASSED: Found {issue_count} unresolved issues in {format_duration(duration)}")
        
        if verbose and result.get("issues"):
            print("\nSample issues:")
            for i, issue in enumerate(result["issues"][:3], 1):
                print(f"  {i}. [{issue.get('id')}] {issue.get('title', 'N/A')[:70]}")
                print(f"     Events: {issue.get('count', 0)}, Level: {issue.get('level', 'N/A')}")
        
        return {"status": "PASSED", "issue_count": issue_count, "duration": duration}
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return {"status": "ERROR", "error": str(e)}


def test_datadog_apm(service: str, verbose: bool = False) -> dict:
    """Test query_datadog_apm tool"""
    print(f"\n{'='*80}")
    print(f"TEST 3: query_datadog_apm (service={service})")
    print(f"{'='*80}")
    
    try:
        # Initialize Datadog if not already done
        config = get_config()
        if config.dd_enabled and config.dd_api_key and config.dd_app_key:
            init_datadog(
                api_key=config.dd_api_key,
                app_key=config.dd_app_key,
                service_name="log-ai-mcp"
            )
        
        # Map service name to Datadog service name
        from src.config import load_config
        app_config = load_config()
        datadog_service = service  # Default
        target_service = next((s for s in app_config.services if s.name == service), None)
        if target_service and target_service.datadog_service_name:
            datadog_service = target_service.datadog_service_name
        
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=1)
        
        start = time.time()
        result = query_apm_traces(
            service=datadog_service,
            start_time=start_time,
            end_time=end_time,
            limit=10
        )
        duration = time.time() - start
        
        if "error" in result:
            print(f"❌ FAILED: {result['error']}")
            return {"status": "FAILED", "error": result['error'], "duration": duration}
        
        trace_count = result.get("count", 0)
        print(f"✅ PASSED: Found {trace_count} traces in {format_duration(duration)}")
        
        if verbose and result.get("traces"):
            print("\nSample traces:")
            for i, trace in enumerate(result["traces"][:3], 1):
                print(f"  {i}. Operation: {trace.get('operation', 'N/A')}")
                print(f"     Duration: {trace.get('duration_ms', 0):.1f}ms")
        
        return {"status": "PASSED", "trace_count": trace_count, "duration": duration}
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return {"status": "ERROR", "error": str(e)}


def test_datadog_logs(service: str, verbose: bool = False) -> dict:
    """Test query_datadog_logs tool"""
    print(f"\n{'='*80}")
    print(f"TEST 4: query_datadog_logs (service={service})")
    print(f"{'='*80}")
    
    try:
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=1)
        
        start = time.time()
        result = query_logs(
            query=f"service:{service}",
            start_time=start_time,
            end_time=end_time,
            limit=10
        )
        duration = time.time() - start
        
        if "error" in result:
            print(f"❌ FAILED: {result['error']}")
            return {"status": "FAILED", "error": result['error'], "duration": duration}
        
        log_count = result.get("count", 0)
        print(f"✅ PASSED: Found {log_count} log entries in {format_duration(duration)}")
        
        if verbose and result.get("logs"):
            print("\nSample logs:")
            for i, log in enumerate(result["logs"][:3], 1):
                msg = log.get("message", "N/A")[:60]
                print(f"  {i}. {msg}")
        
        return {"status": "PASSED", "log_count": log_count, "duration": duration}
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return {"status": "ERROR", "error": str(e)}


def test_datadog_metrics(service: str, verbose: bool = False) -> dict:
    """Test query_datadog_metrics tool"""
    print(f"\n{'='*80}")
    print(f"TEST 5: query_datadog_metrics (service={service})")
    print(f"{'='*80}")
    
    try:
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=1)
        
        start = time.time()
        result = query_metrics(
            metric_query="avg:system.cpu.user{*}",
            start_time=start_time,
            end_time=end_time
        )
        duration = time.time() - start
        
        if "error" in result:
            # Check if it's a permissions error
            error_msg = str(result.get("error", ""))
            if "403" in error_msg or "Forbidden" in error_msg or "permission" in error_msg.lower():
                print(f"⚠️  LIMITED: Query metrics endpoint requires additional permissions")
                print(f"   API key can list metrics but cannot query timeseries data")
                return {"status": "LIMITED", "error": "permissions", "duration": duration}
            print(f"❌ FAILED: {result['error']}")
            return {"status": "FAILED", "error": result['error'], "duration": duration}
        
        if result.get("status") == "no_data":
            print(f"⚠️  WARNING: No data available (this may be expected)")
            return {"status": "NO_DATA", "duration": duration}
        
        series_count = len(result.get("series", []))
        print(f"✅ PASSED: Retrieved {series_count} metric series in {format_duration(duration)}")
        
        if verbose and result.get("series"):
            print("\nSample metrics:")
            for i, series in enumerate(result["series"][:3], 1):
                print(f"  {i}. {series.get('metric', 'N/A')}")
                print(f"     Points: {len(series.get('points', []))}")
        
        return {"status": "PASSED", "series_count": series_count, "duration": duration}
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return {"status": "ERROR", "error": str(e)}


def main():
    """Main validation runner"""
    parser = argparse.ArgumentParser(description="Validate LogAI MCP Tools in production")
    parser.add_argument("--service", default="hub-ca-auth", help="Service to test with")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show sample data")
    args = parser.parse_args()
    
    print("="*80)
    print("LogAI MCP Tools - Production Validation")
    print("="*80)
    print(f"Service: {args.service}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Environment: Production (syslog.awstst.pason.com)")
    
    # Run all tests
    results = {
        "search_logs": test_search_logs(args.service, args.verbose),
        "query_sentry_issues": test_sentry_issues(args.service, args.verbose),
        "query_datadog_apm": test_datadog_apm(args.service, args.verbose),
        "query_datadog_logs": test_datadog_logs(args.service, args.verbose),
        "query_datadog_metrics": test_datadog_metrics(args.service, args.verbose)
    }
    
    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}\n")
    
    passed = sum(1 for r in results.values() if r.get("status") == "PASSED")
    failed = sum(1 for r in results.values() if r.get("status") == "FAILED")
    errors = sum(1 for r in results.values() if r.get("status") == "ERROR")
    warnings = sum(1 for r in results.values() if r.get("status") == "NO_DATA")
    
    total = len(results)
    
    for tool, result in results.items():
        status = result.get("status", "UNKNOWN")
        duration = result.get("duration", 0)
        
        if status == "PASSED":
            icon = "✅"
        elif status == "NO_DATA":
            icon = "⚠️ "
        elif status == "FAILED":
            icon = "❌"
        else:
            icon = "❌"
        
        print(f"{icon} {tool:30s} {status:10s} ({format_duration(duration)})")
    
    print(f"\n{'='*80}")
    print(f"Overall: {passed}/{total} tools functional")
    
    if failed > 0:
        print(f"Failed: {failed} tools")
    if errors > 0:
        print(f"Errors: {errors} tools")
    if warnings > 0:
        print(f"Warnings: {warnings} tools (no data)")
    
    print(f"{'='*80}\n")
    
    # Return exit code
    if failed > 0 or errors > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
