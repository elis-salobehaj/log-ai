#!/usr/bin/env python3
"""Test Datadog APM query with mapped service name"""

from src.config_loader import get_config
from src.datadog_integration import init_datadog, query_apm_traces
from datetime import datetime, timedelta, timezone

config = get_config()
init_datadog(
    api_key=config.dd_api_key,
    app_key=config.dd_app_key,
    site=config.dd_site,
    service_name=config.dd_service_name,
    env=config.dd_env
)

end = datetime.now(timezone.utc)
start = end - timedelta(hours=24)

print("Testing APM query with pason-auth-service...")
result = query_apm_traces(
    service="pason-auth-service",
    start_time=start,
    end_time=end
)

trace_count = result.get("count", 0)
print(f"✅ Trace count: {trace_count}")

if result.get("traces"):
    trace = result["traces"][0]
    print(f"✅ Sample trace:")
    print(f"   - trace_id: {trace.get('trace_id')}")
    print(f"   - duration: {trace.get('duration_ms')}ms")
    print(f"   - operation: {trace.get('operation')}")
    print(f"   - resource: {trace.get('resource')}")
elif "error" in result:
    print(f"❌ Error: {result['error']}")
else:
    print(f"⚠️  No traces found")
