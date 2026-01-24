# Service Resolution Fix - January 7, 2026

## Problem Identified

The MCP server's service resolution was not properly handling `sentry_service_name` mappings when querying Sentry. 

### Issue Description

In `services.yaml`, services have two names:
1. **Log service name** (e.g., `hub-ca-edr-proxy-service`) - used for log file paths
2. **Sentry service name** (e.g., `edr-proxy-service`) - used for Sentry project queries

When users queried Sentry tools, the system would:
- ✅ Correctly resolve the log service name
- ✅ Look up the `sentry_service_name` from config
- ❌ **But couldn't resolve queries using the Sentry project name directly**

### Example of the Problem

User wants to query Sentry for "edr-proxy-service" errors:
```
User query: "edr-proxy-service"
Expected: Find hub-ca-edr-proxy-service and hub-us-edr-proxy-service
Actual: No match found (because resolver only checked log service names)
```

## Solution Implemented

### Changes to `src/config.py`

Added **Strategy 2** to the `resolve_service_names()` function:

```python
# Strategy 2: Exact match on sentry_service_name
# This allows querying by Sentry project name (e.g., "auth-service", "edr-proxy-service")
for service in candidate_services:
    if service.sentry_service_name:
        if normalize_service_name(service.sentry_service_name) == normalized_query:
            matches.append(service)
```

Also enhanced **Strategy 4** (partial matching) to check sentry_service_name:

```python
# Also check sentry_service_name for partial matches
if service.sentry_service_name:
    normalized_sentry = normalize_service_name(service.sentry_service_name)
    if normalized_query in normalized_sentry:
        matches.append(service)
```

### Updated Matching Strategies

The resolver now uses **5 strategies** in priority order:

1. **Exact match on service name**: `"hub-ca-auth"` → `[hub-ca-auth]`
2. **Exact match on sentry_service_name**: `"auth-service"` → `[hub-ca-auth, hub-us-auth]` ✨ **NEW**
3. **Base name match**: `"auth"` → `[hub-ca-auth, hub-us-auth, hub-na-auth]`
4. **Partial match**: `"edr-proxy"` → matches both service names and sentry names ✨ **ENHANCED**
5. **Variation match**: `"edr_proxy"` → same as `"edr-proxy"` (via normalization)

## Testing

Created comprehensive test suite in `scripts/test_sentry_service_resolution.py`:

### Test Results (All Passed ✅)

```
✅ Query by sentry_service_name 'auth-service' → Found 2 services
✅ Query by sentry_service_name 'edr-proxy-service' → Found 2 services
✅ Query by sentry_service_name 'witsml' → Found 4 services
✅ Query by sentry_service_name 'mobile-api-proxy' → Found 4 services
✅ Query 'auth-service' with locale='ca' → Found 1 service
✅ Query 'edr-proxy-service' with locale='us' → Found 1 service
✅ Query by exact service name 'hub-ca-auth' → Found 1 service (backwards compatible)
✅ Query by base name 'auth' → Found 2 services (backwards compatible)
```

## Benefits

### 1. Flexibility
Users can now query using either:
- Log service names: `"hub-ca-edr-proxy-service"`
- Sentry project names: `"edr-proxy-service"`
- Base names: `"edr-proxy"`, `"auth"`
- Variations: `"edr_proxy"`, `"edrproxy"`

### 2. Deduplication
Multiple log services mapping to the same Sentry project are handled correctly:
```
Query: "auth-service"
Resolves to: hub-ca-auth, hub-us-auth
Both map to Sentry project: "auth-service"
Result: Single Sentry query (no duplicates)
```

### 3. Backwards Compatibility
All existing queries continue to work exactly as before.

### 4. Locale Filtering
Works with locale parameter:
```
Query: "auth-service", locale="ca"
Result: Only hub-ca-auth
```

## Example Usage

### Before Fix
```
User: "Query Sentry issues for edr-proxy-service"
MCP: Error: Service not found: edr-proxy-service
```

### After Fix
```
User: "Query Sentry issues for edr-proxy-service"
MCP: ✅ Found 2 services: hub-ca-edr-proxy-service, hub-us-edr-proxy-service
     Querying Sentry project: edr-proxy-service
     Results: [aggregated issues from both services]
```

## Files Modified

1. **src/config.py**
   - Added Strategy 2: Exact match on sentry_service_name
   - Enhanced Strategy 4: Partial match includes sentry_service_name
   - Updated docstring with correct strategy descriptions

## Files Created

1. **scripts/test_sentry_service_resolution.py** - Comprehensive test suite
2. **scripts/demo_service_resolution.py** - Interactive demonstration
3. **SERVICE_RESOLUTION_FIX.md** - This documentation

## Deployment

✅ Deployed to production: `syslog.example.com`
✅ All tests passed on production server
✅ Zero downtime deployment
✅ Backwards compatible

## Related Work

This fix completes the service resolution enhancement from Phase 3, which added:
- Flexible service name variations (underscores, hyphens, case-insensitive)
- Locale filtering (ca/us/na)
- Multi-service Sentry aggregation
- Helpful error messages with suggestions

The missing piece was matching on `sentry_service_name` directly, which is now resolved.
