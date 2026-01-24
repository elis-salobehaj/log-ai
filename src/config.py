import yaml
import glob
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel
import os

class ServiceConfig(BaseModel):
    name: str
    type: str
    description: str
    path_pattern: str
    path_date_formats: Optional[List[str]] = None
    sentry_service_name: Optional[str] = None  # Maps to existing Sentry project
    sentry_dsn: Optional[str] = None  # Per-service Sentry DSN
    
    def get_sentry_project_id(self) -> Optional[str]:
        """Extract Sentry project ID from DSN"""
        if not self.sentry_dsn:
            return None
        
        # DSN format: https://key@host/PROJECT_ID
        try:
            parts = self.sentry_dsn.split('/')
            if parts and parts[-1].isdigit():
                return parts[-1]
        except:
            pass
        
        return None

class AppConfig(BaseModel):
    services: List[ServiceConfig]

def load_config(config_path: str = None) -> AppConfig:
    if config_path is None:
        # Default to ../config/services.yaml relative to this file
        base_dir = Path(__file__).parent.parent
        config_path = base_dir / "config" / "services.yaml"
    
    with open(config_path, "r") as f:
        data = yaml.safe_load(f)
    
    return AppConfig(**data)

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
    1. Exact match on service name: "hub-ca-auth" → [hub-ca-auth]
    2. Exact match on sentry_service_name: "auth-service" → [hub-ca-auth, hub-us-auth]
    3. Base name match: "auth" → [hub-ca-auth, hub-us-auth, hub-na-auth]
    4. Partial match: "edr-proxy" → [hub-ca-edr-proxy-service, hub-us-edr-proxy-service]
    5. Variation match: "edr_proxy" → same as "edr-proxy" (handled by normalization)
    
    Args:
        query: User's service name query (flexible format)
        services: List of all available services from config
        locale: Optional locale filter ('ca', 'us', 'na')
    
    Returns:
        List of matching ServiceConfig objects (may be empty)
    
    Examples:
        resolve_service_names("auth", services) 
            → [hub-ca-auth, hub-us-auth]
        
        resolve_service_names("auth-service", services)
            → [hub-ca-auth, hub-us-auth] (matches sentry_service_name)
        
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
        
        # Special handling for 'na' locale (includes hub-na-, edr-na-, edrtier3-na-)
        if locale_lower == 'na':
            candidate_services = [
                s for s in services 
                if s.name.startswith('hub-na-') 
                or s.name.startswith('edr-na-') 
                or s.name.startswith('edrtier3-na-')
            ]
        else:
            locale_prefix = f"hub-{locale_lower}-"
            candidate_services = [
                s for s in services 
                if s.name.startswith(locale_prefix)
            ]
    
    # Strategy 1: Exact match on service name
    for service in candidate_services:
        if normalize_service_name(service.name) == normalized_query:
            matches.append(service)
    
    if matches:
        return matches
    
    # Strategy 2: Exact match on sentry_service_name
    # This allows querying by Sentry project name (e.g., "auth-service", "edr-proxy-service")
    for service in candidate_services:
        if service.sentry_service_name:
            if normalize_service_name(service.sentry_service_name) == normalized_query:
                matches.append(service)
    
    if matches:
        return matches
    
    # Strategy 3: Base name match (strip locale prefix from both query and service)
    query_base = get_base_service_name(normalized_query)
    
    for service in candidate_services:
        service_base = get_base_service_name(service.name)
        if service_base == query_base:
            matches.append(service)
    
    if matches:
        return matches
    
    # Strategy 4: Partial match (query is substring of service name or sentry_service_name)
    for service in candidate_services:
        normalized_service = normalize_service_name(service.name)
        service_base = get_base_service_name(service.name)
        
        # Match if query appears in full service name or base name
        if (normalized_query in normalized_service or 
            normalized_query in service_base):
            matches.append(service)
            continue
        
        # Also check sentry_service_name for partial matches
        if service.sentry_service_name:
            normalized_sentry = normalize_service_name(service.sentry_service_name)
            if normalized_query in normalized_sentry:
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

def expand_pattern(pattern: str, date: datetime = None, hour: int = None) -> str:
    """
    Expands {YYYY}, {MM}, {DD}, {HH} placeholders in the pattern.
    If no date is provided, defaults to today.
    If no hour is provided, uses wildcard to match all hours.
    """
    if date is None:
        date = datetime.now()
    
    # For hour, if not specified, use wildcard to match all hours of the day
    hour_str = f"{hour:02d}" if hour is not None else "*"
    
    return pattern.format(
        YYYY=date.strftime("%Y"),
        MM=date.strftime("%m"),
        DD=date.strftime("%d"),
        HH=hour_str,
        guid="*", # Handle guid placeholder as wildcard if present
    )

def find_log_files(service: ServiceConfig, start_hour: datetime = None, end_hour: datetime = None) -> List[str]:
    """
    Finds log files matching the service pattern for a UTC datetime range.
    
    Args:
        service: Service configuration
        start_hour: Start datetime in UTC (actually a datetime object, not just hour)
        end_hour: End datetime in UTC (actually a datetime object, not just hour)
    
    The parameter names are historical - they actually expect full datetime objects.
    Iterates hourly from start_hour to end_hour to find matching log files.
    """
    files = []
    project_root = Path(__file__).parent.parent
    
    # If config doesn't use placeholders, just return the glob (maybe it's a flat file)
    if "{YYYY}" not in service.path_pattern and "{MM}" not in service.path_pattern:
        p = Path(service.path_pattern)
        if not p.is_absolute():
            p = project_root / p
        return glob.glob(str(p), recursive=True)

    # Generate times to check by iterating hourly from start to end
    times_to_check = []
    if start_hour is not None and end_hour is not None and isinstance(start_hour, datetime):
        # Handle datetime range (UTC timestamps)
        current = start_hour
        end_time = end_hour
        while current <= end_time:
            times_to_check.append((current, True))  # True = specific hour
            current = current + timedelta(hours=1)
    else:
        # Fallback: search current hour only
        now = datetime.now()
        times_to_check.append((now, True))

    for date, specific_hour in times_to_check:
        # Construct pattern for this time period
        if specific_hour:
            # Search only current hour: replace HH with specific hour
            hour_str = date.strftime("%H")
            pattern = service.path_pattern.replace("{YYYY}", date.strftime("%Y")) \
                                          .replace("{MM}", date.strftime("%m")) \
                                          .replace("{DD}", date.strftime("%d")) \
                                          .replace("{HH}", hour_str) \
                                          .replace("{guid}", "*")
        else:
            # Search all hours of this day: use wildcard for HH
            pattern = service.path_pattern.replace("{YYYY}", date.strftime("%Y")) \
                                          .replace("{MM}", date.strftime("%m")) \
                                          .replace("{DD}", date.strftime("%d")) \
                                          .replace("{HH}", "*") \
                                          .replace("{guid}", "*")
        
        # Resolve path
        p = Path(pattern)
        if not p.is_absolute():
            p = project_root / p
            
        # Glob just this time period
        sys.stderr.write(f"[DEBUG] Globbing {str(p)}\n")
        sys.stderr.flush()
        day_files = glob.glob(str(p), recursive=True)
        sys.stderr.write(f"[DEBUG] Found {len(day_files)} files\n")
        sys.stderr.flush()
        files.extend(day_files)
        
    return files
