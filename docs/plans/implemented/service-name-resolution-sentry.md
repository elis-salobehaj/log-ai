# Plan: Service Name Resolution and Sentry Query Enhancement

## Overview

Add flexible service name mapping with locale filtering and fix Sentry integration for seamless service querying across locales.

## Context

**Current Issues:**
- Service names require exact matches (e.g., "hub-ca-edr-proxy-service")
- No support for base name queries (e.g., "auth" to find all auth services)
- No locale filtering (ca/us/na parameter)
- Users must know exact service naming conventions
- Sentry queries don't support flexible service name resolution

**User Requirements:**
1. Support service name variations: edr-proxy, edr_proxy, edrproxy, hub-edr-proxy should all map to hub-ca-edr-proxy-service and hub-us-edr-proxy-service
2. Locale filtering: If user specifies locale (ca/us/na), only return services from that locale
3. Fix Sentry integration to work with flexible service queries (e.g., query "edr-proxy" and get Sentry issues from all matched services)

**Service Naming Patterns:**
- Locale prefixes: `hub-ca-`, `hub-us-`, `hub-na-`, `edr-na-`, `edrtier3-na-`
- Base names: auth, api, cfg, edr-proxy-service, kpigen, etc.
- 90 total services across locales
- Many services share Sentry projects across locales (e.g., hub-ca-auth + hub-us-auth → auth-service)

## Implementation Steps

### 1. Create Service Name Resolver in src/config.py

**Location:** Lines 30-35 (after `load_services_config()`)

**Functions to Add:**

```python
def normalize_service_name(name: str) -> str:
    """
    Normalize service name for fuzzy matching.
    
    Removes:
    - Underscores and converts to hyphens
    - Extra whitespace
    - Makes lowercase
    
    Examples:
    - "edr_proxy" → "edr-proxy"
    - "EDR-Proxy" → "edr-proxy"
    - "hub edr proxy" → "hub-edr-proxy"
    """
    return name.strip().lower().replace('_', '-').replace(' ', '-')


def get_base_service_name(service_name: str) -> str:
    """
    Extract base service name by removing locale prefix.
    
    Strips locale prefixes in order:
    1. hub-ca-
    2. hub-us-
    3. hub-na-
    4. edr-na-
    5. edrtier3-na-
    6. hub- (if not matched above)
    
    Examples:
    - "hub-ca-auth" → "auth"
    - "hub-us-edr-proxy-service" → "edr-proxy-service"
    - "edr-na-software-updater-service" → "software-updater-service"
    - "hub-portmapper" → "portmapper"
    """
    normalized = normalize_service_name(service_name)
    
    prefixes = [
        'hub-ca-',
        'hub-us-',
        'hub-na-',
        'edr-na-',
        'edrtier3-na-',
        'hub-'
    ]
    
    for prefix in prefixes:
        if normalized.startswith(prefix):
            return normalized[len(prefix):]
    
    return normalized


def resolve_service_names(
    query: str, 
    services: List[ServiceConfig],
    locale: Optional[str] = None
) -> List[ServiceConfig]:
    """
    Resolve user query to matching service(s) with fuzzy matching.
    
    Matching strategies (in order):
    1. Exact match: "hub-ca-auth" → [hub-ca-auth]
    2. Base name match: "auth" → [hub-ca-auth, hub-us-auth, hub-na-auth]
    3. Partial match: "edr-proxy" → [hub-ca-edr-proxy-service, hub-us-edr-proxy-service]
    4. Variation match: "edr_proxy" → same as "edr-proxy"
    
    Args:
        query: User's service name query (flexible format)
        services: List of all available services from config
        locale: Optional locale filter ('ca', 'us', 'na')
    
    Returns:
        List of matching ServiceConfig objects (may be empty)
    
    Examples:
        resolve_service_names("auth", services) 
            → [hub-ca-auth, hub-us-auth]
        
        resolve_service_names("edr-proxy", services, locale="ca")
            → [hub-ca-edr-proxy-service]
        
        resolve_service_names("hub-ca-auth", services)
            → [hub-ca-auth]
    """
    normalized_query = normalize_service_name(query)
    matches = []
    
    # Filter by locale if specified
    candidate_services = services
    if locale:
        locale_lower = locale.lower()
        locale_prefix = f"hub-{locale_lower}-"
        
        # Special handling for edr-na and edrtier3-na
        if locale_lower == 'na':
            candidate_services = [
                s for s in services 
                if s.name.startswith('hub-na-') 
                or s.name.startswith('edr-na-') 
                or s.name.startswith('edrtier3-na-')
            ]
        else:
            candidate_services = [
                s for s in services 
                if s.name.startswith(locale_prefix)
            ]
    
    # Strategy 1: Exact match
    for service in candidate_services:
        if normalize_service_name(service.name) == normalized_query:
            matches.append(service)
    
    if matches:
        return matches
    
    # Strategy 2: Base name match (strip locale prefix from both query and service)
    query_base = get_base_service_name(normalized_query)
    
    for service in candidate_services:
        service_base = get_base_service_name(service.name)
        if service_base == query_base:
            matches.append(service)
    
    if matches:
        return matches
    
    # Strategy 3: Partial match (query is substring of service name)
    for service in candidate_services:
        normalized_service = normalize_service_name(service.name)
        service_base = get_base_service_name(service.name)
        
        # Match if query appears in full service name or base name
        if (normalized_query in normalized_service or 
            normalized_query in service_base):
            matches.append(service)
    
    return matches


def find_similar_services(
    query: str,
    services: List[ServiceConfig],
    limit: int = 5
) -> List[str]:
    """
    Find similar service names for helpful error messages.
    
    Uses simple substring matching and returns services
    that partially match the query.
    
    Args:
        query: User's attempted service name
        services: List of all available services
        limit: Maximum number of suggestions to return
    
    Returns:
        List of similar service names (up to limit)
    """
    normalized_query = normalize_service_name(query)
    suggestions = []
    
    for service in services:
        normalized_service = normalize_service_name(service.name)
        service_base = get_base_service_name(service.name)
        
        # Check if query is similar to service name or base name
        if (normalized_query in normalized_service or
            normalized_service in normalized_query or
            normalized_query in service_base or
            service_base in normalized_query):
            suggestions.append(service.name)
    
    return suggestions[:limit]
```

### 2. Update Tool Handlers in src/server.py

**Files to Update:**
- `search_logs_handler()` - Line ~1100
- `query_sentry_issues_handler()` - Line ~1389
- `search_sentry_traces_handler()` - Line ~1533
- Cache hit tracking - Line ~799

**Pattern to Replace:**

```python
# OLD (exact match only)
target_service = next((s for s in config.services if s.name == service_name), None)
if not target_service:
    return [types.TextContent(type="text", text=f"Error: Service not found: {service_name}")]
```

**New Pattern (with locale support):**

```python
# NEW (flexible matching with locale)
locale = arguments.get("locale")  # Extract locale if provided
matched_services = resolve_service_names(service_name, config.services, locale=locale)

if not matched_services:
    # Provide helpful suggestions
    suggestions = find_similar_services(service_name, config.services)
    error_msg = f"Error: Service not found: {service_name}"
    if suggestions:
        error_msg += f"\n\nDid you mean one of these?\n  - " + "\n  - ".join(suggestions)
    return [types.TextContent(type="text", text=error_msg)]

# Handle single vs multiple matches
if len(matched_services) == 1:
    target_service = matched_services[0]
    # Continue with existing logic...
else:
    # Multiple services matched - query all and aggregate results
    # (Implementation depends on handler type)
```

### 3. Enhance Sentry Handlers for Multi-Service Support

**query_sentry_issues_handler (lines 1381-1450):**

```python
async def query_sentry_issues_handler(
    name: str, 
    arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Query Sentry issues for one or more services.
    Supports flexible service name matching and locale filtering.
    """
    service_name = arguments.get("service_name")
    locale = arguments.get("locale")
    query = arguments.get("query", "is:unresolved")
    limit = arguments.get("limit", 25)
    stats_period = arguments.get("statsPeriod", "24h")
    
    # Resolve service name(s)
    matched_services = resolve_service_names(service_name, config.services, locale=locale)
    
    if not matched_services:
        suggestions = find_similar_services(service_name, config.services)
        error_msg = f"Error: Service not found: {service_name}"
        if suggestions:
            error_msg += f"\n\nDid you mean:\n  - " + "\n  - ".join(suggestions)
        return [types.TextContent(type="text", text=error_msg)]
    
    # Aggregate results from all matched services
    all_issues = []
    services_queried = []
    
    for service in matched_services:
        if not service.sentry_service_name:
            continue  # Skip services without Sentry configuration
        
        sentry_project = service.sentry_service_name
        
        # Query Sentry API
        result = sentry_api.query_issues(
            project=sentry_project,
            query=query,
            limit=limit,
            statsPeriod=stats_period
        )
        
        if result.get("success"):
            # Tag each issue with originating service
            for issue in result.get("issues", []):
                issue["_source_service"] = service.name
                issue["_sentry_project"] = sentry_project
            
            all_issues.extend(result.get("issues", []))
            services_queried.append(f"{service.name} → {sentry_project}")
    
    if not services_queried:
        return [types.TextContent(
            type="text",
            text=f"No Sentry configuration found for: {', '.join(s.name for s in matched_services)}"
        )]
    
    # Format response
    response = f"🔍 Sentry Issues Query Results\n"
    response += f"Services: {', '.join(services_queried)}\n"
    response += f"Query: {query}\n"
    response += f"Period: {stats_period}\n"
    response += f"Found: {len(all_issues)} issues\n\n"
    
    if all_issues:
        response += "Issues:\n"
        for issue in all_issues[:limit]:
            source_service = issue.get("_source_service", "unknown")
            issue_id = issue.get("id", "N/A")
            title = issue.get("title", "No title")
            count = issue.get("count", 0)
            
            response += f"\n• [{source_service}] Issue #{issue_id}\n"
            response += f"  Title: {title}\n"
            response += f"  Events: {count}\n"
            response += f"  Link: {issue.get('permalink', 'N/A')}\n"
    else:
        response += "No issues found matching the query.\n"
    
    return [types.TextContent(type="text", text=response)]
```

**Similar updates for `search_sentry_traces_handler`**

### 4. Update Tool Schemas with Examples

**Location:** src/server.py lines 934-1068

**Add to tool descriptions:**

```python
tools=[
    types.Tool(
        name="search_logs",
        description="""Search for log entries across one or more services. 

Service name supports flexible matching:
- Exact match: "hub-ca-auth" → hub-ca-auth only
- Base name: "auth" → all auth services (hub-ca-auth, hub-us-auth, hub-na-auth)
- Partial match: "edr-proxy" → hub-ca-edr-proxy-service, hub-us-edr-proxy-service
- Variations: "edr_proxy", "edrproxy" → same as "edr-proxy"

Use the 'locale' parameter to filter by region (ca, us, or na).""",
        inputSchema={
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Service name (flexible matching - can be exact name, base name, or partial match)"
                },
                "locale": {
                    "type": "string",
                    "description": "Optional locale filter: 'ca' (Canada), 'us' (United States), or 'na' (North America)",
                    "enum": ["ca", "us", "na"]
                },
                # ... rest of parameters
            }
        }
    ),
    
    types.Tool(
        name="query_sentry_issues",
        description="""Query Sentry issues for a service.

Service name supports flexible matching:
- "auth" → queries all auth services across locales
- "edr-proxy" → queries edr-proxy-service for all locales
- "hub-ca-auth" → queries only Canada auth service

Use 'locale' parameter to filter to specific region.""",
        inputSchema={
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Service name (supports fuzzy matching and variations)"
                },
                "locale": {
                    "type": "string",
                    "description": "Optional: Filter to specific locale (ca/us/na)"
                },
                # ... rest of parameters
            },
            "required": ["service_name"]
        }
    ),
    
    # Similar updates for search_sentry_traces
]
```

### 5. Add Locale Parameter to Tool Schemas

**Update inputSchema for these tools:**
- `search_logs`
- `query_sentry_issues`
- `search_sentry_traces`

**Add property:**
```python
"locale": {
    "type": "string",
    "description": "Optional locale filter: 'ca' (Canada), 'us' (United States), or 'na' (North America)",
    "enum": ["ca", "us", "na"]
}
```

### 6. Test Sentry Integration End-to-End

**Test Cases:**

1. **Test flexible service name matching:**
   ```json
   {
     "service_name": "edr-proxy",
     "query": "is:unresolved",
     "limit": 10
   }
   ```
   Expected: Returns issues from both hub-ca-edr-proxy-service and hub-us-edr-proxy-service

2. **Test locale filtering:**
   ```json
   {
     "service_name": "auth",
     "locale": "ca",
     "query": "is:unresolved"
   }
   ```
   Expected: Returns issues only from hub-ca-auth

3. **Test service name variations:**
   ```json
   {
     "service_name": "edr_proxy",
     "query": "is:unresolved"
   }
   ```
   Expected: Same results as "edr-proxy"

4. **Test error handling:**
   ```json
   {
     "service_name": "nonexistent-service",
     "query": "is:unresolved"
   }
   ```
   Expected: Returns helpful error with suggestions

5. **Test services without Sentry config:**
   ```json
   {
     "service_name": "hub-ca-cfg",
     "query": "is:unresolved"
   }
   ```
   Expected: Returns message "No Sentry configuration found for: hub-ca-cfg"

## Questions for Refinement

### 1. Service Name Variations Handling

**Question:** Should we support unlimited variations (edr-proxy, edr_proxy, edrproxy, hub-edr-proxy) via normalization, or maintain an explicit alias mapping?

**Option A - Normalization (Recommended):**
- Pros: Works automatically for any service, no maintenance
- Cons: May match unintended services (rare)
- Implementation: `normalize_service_name()` function

**Option B - Explicit Aliases:**
- Pros: More control, explicit documentation
- Cons: Requires maintaining alias list in services.yaml
- Implementation: Add `aliases: [edr-proxy, edr_proxy, edrproxy]` to each service

**Recommendation:** Use normalization (Option A) as it's more flexible and requires no configuration changes.

### 2. Multiple Service Match Behavior

**Question:** When "auth" matches 3 services (hub-ca-auth, hub-us-auth, hub-na-auth), what should we do?

**Option A - Query All and Aggregate (Recommended):**
- Pros: Most useful for users, shows complete picture
- Cons: May be slower for large result sets
- Implementation: Loop through matched services, aggregate results

**Option B - Require Locale for Disambiguation:**
- Pros: Faster, forces users to be specific
- Cons: Less user-friendly, requires extra parameter
- Implementation: Return error if multiple matches and no locale

**Option C - Default to All with Locale Option:**
- Pros: Best of both worlds
- Cons: More complex implementation
- Implementation: Query all by default, filter if locale provided

**Recommendation:** Use Option A (query all and aggregate) with clear indication of which service each result came from.

### 3. Sentry API Caching

**Question:** Should we add caching for Sentry API responses?

**Current State:**
- No caching
- Every query hits Sentry API
- 10-second timeout per request

**Option A - Add Redis Cache (5-minute TTL):**
- Pros: Faster repeat queries, reduces Sentry API load
- Cons: Stale data possible, more complexity
- Implementation: Use existing Redis coordinator

**Option B - In-Memory Cache:**
- Pros: Simple, fast
- Cons: Lost on server restart, memory usage
- Implementation: Python dict with TTL tracking

**Option C - No Caching:**
- Pros: Always fresh data
- Cons: Slower, more API load
- Implementation: Current state

**Recommendation:** Start with Option C (no caching) and add Option A (Redis cache) if performance becomes an issue.

### 4. Error Message Verbosity

**Question:** How verbose should error messages be?

**Option A - Minimal:**
```
Error: Service not found: edr-prox
```

**Option B - With Suggestions (Recommended):**
```
Error: Service not found: edr-prox

Did you mean:
  - hub-ca-edr-proxy-service
  - hub-us-edr-proxy-service
```

**Option C - With Explanation:**
```
Error: Service not found: edr-prox

No services matched your query. Try using a base name like "edr-proxy" 
or an exact service name like "hub-ca-edr-proxy-service".

Similar services:
  - hub-ca-edr-proxy-service
  - hub-us-edr-proxy-service
```

**Recommendation:** Use Option B (with suggestions) as it's helpful but not overwhelming.

## Files to Modify

1. **src/config.py** - Add resolver functions (~150 lines)
2. **src/server.py** - Update tool handlers and schemas (~200 lines changed)
3. **config/services.yaml** - No changes needed (use existing structure)

## Estimated Implementation Time

- Step 1 (Resolver functions): 1 hour
- Step 2 (Update handlers): 2 hours
- Step 3 (Sentry multi-service): 1.5 hours
- Step 4 (Error messages): 0.5 hours
- Step 5 (Tool schemas): 0.5 hours
- Step 6 (Testing): 1 hour

**Total: ~6.5 hours**

## Success Criteria

✅ User can query "edr-proxy" and get results from all edr-proxy services  
✅ User can query "auth" with locale="ca" and get only Canadian auth results  
✅ Service name variations (edr_proxy, edrproxy) work correctly  
✅ Sentry queries return aggregated results from multiple matched services  
✅ Error messages provide helpful suggestions when service not found  
✅ All existing functionality continues to work (backward compatible)

## Risks and Mitigation

**Risk 1: Ambiguous matches**
- Mitigation: Clear indication of which services were matched in response

**Risk 2: Performance with multiple service queries**
- Mitigation: Parallel Sentry API calls, consider caching for future

**Risk 3: Breaking existing queries with exact names**
- Mitigation: Exact matches take priority in resolution strategy

**Risk 4: Locale parameter conflicts with existing parameters**
- Mitigation: Make locale optional, maintain backward compatibility
