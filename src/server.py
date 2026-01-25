import asyncio
import logging
import os
import sys
import subprocess
import shutil
import json
import time
import hashlib
import uuid
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from collections import OrderedDict

from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

from config import load_config, find_log_files, AppConfig, resolve_service_names, find_similar_services
from config_loader import get_config
from redis_coordinator import (
    RedisCoordinator,
    RedisSemaphore,
    RedisCache,
    RedisMetrics
)
from sentry_integration import (
    init_sentry,
    capture_search_performance,
    capture_error_context,
    add_search_breadcrumb,
    set_user_context,
    get_sentry_api
)
from datadog_integration import (
    init_datadog,
    trace_search_operation,
    record_metric,
    increment_counter,
    is_configured as is_datadog_configured
)
from metrics_collector import (
    get_metrics_collector,
    MetricsCollector
)
from infrastructure_monitoring import (
    get_infrastructure_monitor,
    InfrastructureMonitor
)
from datadog_log_handler import (
    setup_datadog_logging,
    DatadogLogHandler
)

# =============================================================================
# CONFIGURATION - Load from environment variables
# =============================================================================

# Load configuration
config = get_config()

# Cache settings
CACHE_MAX_SIZE_MB = config.cache_max_size_mb
CACHE_MAX_ENTRIES = config.cache_max_entries
CACHE_TTL_MINUTES = config.cache_ttl_minutes

# Concurrency limits
MAX_PARALLEL_SEARCHES_PER_CALL = config.max_parallel_searches_per_call
MAX_GLOBAL_SEARCHES = config.max_global_searches

# Search limits
AUTO_CANCEL_TIMEOUT_SECONDS = config.auto_cancel_timeout_seconds
PREVIEW_MATCHES_LIMIT = config.preview_matches_limit

# File output
FILE_OUTPUT_DIR = Path(config.file_output_dir)
CLEANUP_INTERVAL_HOURS = config.cleanup_interval_hours
FILE_RETENTION_HOURS = config.file_retention_hours

# Logging
# Create unique session ID: random alphanumeric + timestamp
import random
import string
random_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
timestamp = datetime.now().strftime("%Y-%m-%d")
SESSION_ID = f"{random_id}-{timestamp}"
LOG_DIR = Path(f"/tmp/log-ai/{SESSION_ID}")
LOG_FILE = LOG_DIR / "mcp-server.log"

# Progress reporting
PROGRESS_EVERY_N_MATCHES_SMALL = 10  # For <1000 matches
PROGRESS_EVERY_N_MATCHES_LARGE = 100  # For >1000 matches
PROGRESS_MIN_INTERVAL_SECONDS = 2  # Throttle to max 1 update per 2s

# =============================================================================
# GLOBAL STATE
# =============================================================================

# Ensure log directory exists
LOG_DIR.mkdir(parents=True, exist_ok=True)
sys.stderr.write(f"[INIT] Session log directory: {LOG_DIR}\n")
sys.stderr.flush()

# Configure logging to both file and stderr
log_level = getattr(logging, config.log_level.upper(), logging.INFO)
logging.basicConfig(
    level=log_level,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stderr)
    ],
    force=True  # Override any existing configuration
)
logger = logging.getLogger("log-ai")
logger.info(f"Log level set to: {config.log_level}")

# =============================================================================
# Date parsing utilities
# =============================================================================

def parse_time_range(time_str: str) -> Optional[Tuple[int, int]]:
    """
    Parse time range strings like "2 to 4pm", "14:00 to 16:00", "2pm-4pm".
    Returns (start_hour, end_hour) in 24-hour format, or None if can't parse.
    """
    if not time_str:
        return None
    
    time_str = time_str.strip().lower()
    
    # Pattern: "2 to 4pm", "2pm to 4pm", "2-4pm", "14 to 16"
    patterns = [
        r'(\d{1,2})\s*(?:am|pm)?\s*(?:to|-)\s*(\d{1,2})\s*(am|pm)',  # "2 to 4pm" or "2pm-4pm"
        r'(\d{1,2}):(\d{2})\s*(?:to|-)\s*(\d{1,2}):(\d{2})',  # "14:00 to 16:00"
        r'(\d{1,2})\s*(?:am|pm)\s*(?:to|-)\s*(\d{1,2})\s*(am|pm)',  # "2am to 4pm"
    ]
    
    # Try pattern 1: "2 to 4pm" or "2pm-4pm"
    match = re.search(r'(\d{1,2})\s*(?:am|pm)?\s*(?:to|-)\s*(\d{1,2})\s*(am|pm)', time_str)
    if match:
        start = int(match.group(1))
        end = int(match.group(2))
        period = match.group(3)
        
        # Convert to 24-hour format
        if period == 'pm' and end < 12:
            end += 12
        if period == 'pm' and start < 12 and start < end:
            start += 12
        elif period == 'am' and start == 12:
            start = 0
        
        return (start, end)
    
    # Try pattern 2: "14:00 to 16:00"
    match = re.search(r'(\d{1,2}):(\d{2})\s*(?:to|-)\s*(\d{1,2}):(\d{2})', time_str)
    if match:
        start_hour = int(match.group(1))
        end_hour = int(match.group(3))
        return (start_hour, end_hour)
    
    # Try pattern 3: "2am to 4pm"
    match = re.search(r'(\d{1,2})\s*(am|pm)\s*(?:to|-)\s*(\d{1,2})\s*(am|pm)', time_str)
    if match:
        start = int(match.group(1))
        start_period = match.group(2)
        end = int(match.group(3))
        end_period = match.group(4)
        
        # Convert to 24-hour format
        if start_period == 'pm' and start < 12:
            start += 12
        elif start_period == 'am' and start == 12:
            start = 0
            
        if end_period == 'pm' and end < 12:
            end += 12
        elif end_period == 'am' and end == 12:
            end = 0
        
        return (start, end)
    
    return None

def parse_date_string(date_str: str) -> Optional[Tuple[datetime, datetime]]:
    """
    Parse natural language date strings into start/end datetime range.
    
    Supports:
    - Day names: "Sunday", "Monday", etc. (interprets as most recent)
    - Specific dates: "Dec 14", "December 14", "Dec 14 2025", "2025-12-14"
    - Relative: "today", "yesterday"
    
    Returns: (start_datetime, end_datetime) tuple covering full day, or None if can't parse
    """
    if not date_str:
        return None
    
    date_str = date_str.strip().lower()
    now = datetime.now()
    
    # Handle "today"
    if date_str == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return (start, end)
    
    # Handle "yesterday"
    if date_str == "yesterday":
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return (start, end)
    
    # Handle day names (Sunday, Monday, etc.)
    days_of_week = {
        "sunday": 6, "sun": 6,
        "monday": 0, "mon": 0,
        "tuesday": 1, "tue": 1, "tues": 1,
        "wednesday": 2, "wed": 2,
        "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
        "friday": 4, "fri": 4,
        "saturday": 5, "sat": 5
    }
    
    if date_str in days_of_week:
        target_weekday = days_of_week[date_str]
        current_weekday = now.weekday()
        
        # If today is the target day, use today
        if current_weekday == target_weekday:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            # Find most recent occurrence
            days_back = (current_weekday - target_weekday) % 7
            if days_back == 0:
                days_back = 7  # Last week if not today
            start = (now - timedelta(days=days_back)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        end = start + timedelta(days=1)
        return (start, end)
    
    # Try parsing specific dates
    # Format: "Dec 14", "December 14", "Dec 14 2025", "2025-12-14", "12/14/2025"
    
    # ISO format: 2025-12-14
    match = re.match(r'(\d{4})-(\d{1,2})-(\d{1,2})', date_str)
    if match:
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        start = datetime(year, month, day)
        end = start + timedelta(days=1)
        return (start, end)
    
    # US format: 12/14/2025 or 12/14
    match = re.match(r'(\d{1,2})/(\d{1,2})(?:/(\d{4}))?', date_str)
    if match:
        month, day = int(match.group(1)), int(match.group(2))
        year = int(match.group(3)) if match.group(3) else now.year
        start = datetime(year, month, day)
        end = start + timedelta(days=1)
        return (start, end)
    
    # Month name formats: "Dec 14", "December 14 2025"
    month_names = {
        'jan': 1, 'january': 1,
        'feb': 2, 'february': 2,
        'mar': 3, 'march': 3,
        'apr': 4, 'april': 4,
        'may': 5,
        'jun': 6, 'june': 6,
        'jul': 7, 'july': 7,
        'aug': 8, 'august': 8,
        'sep': 9, 'sept': 9, 'september': 9,
        'oct': 10, 'october': 10,
        'nov': 11, 'november': 11,
        'dec': 12, 'december': 12
    }
    
    # Try "Month Day" or "Month Day Year"
    for month_name, month_num in month_names.items():
        # Pattern: "december 14" or "dec 14 2025"
        pattern = rf'{month_name}\s+(\d{{1,2}})(?:\s+(\d{{4}}))?'
        match = re.search(pattern, date_str)
        if match:
            day = int(match.group(1))
            year = int(match.group(2)) if match.group(2) else now.year
            start = datetime(year, month_num, day)
            end = start + timedelta(days=1)
            return (start, end)
    
    return None

# Check for ripgrep availability at startup
HAS_RIPGREP = shutil.which("rg") is not None

# =============================================================================
# REDIS COORDINATION - Global state management
# =============================================================================

# Redis coordinator (initialized on startup)
redis_coordinator: Optional[RedisCoordinator] = None
redis_connected: bool = False

# Sentry error tracking (initialized on startup)
sentry_enabled: bool = False

# Datadog APM and metrics (Phase 3 - initialized on startup)
datadog_enabled: bool = False

# Datadog log handler (Phase 3.5 - initialized on startup)
datadog_log_handler: Optional[DatadogLogHandler] = None


async def init_redis():
    """Initialize Redis connection for distributed coordination"""
    global redis_coordinator, redis_connected
    
    if not config.redis_enabled:
        sys.stderr.write("[REDIS] Redis disabled via config\n")
        return
    
    sys.stderr.write(f"[REDIS] Connecting to {config.redis_host}:{config.redis_port}...\n")
    redis_coordinator = RedisCoordinator(
        host=config.redis_host,
        port=config.redis_port,
        password=config.redis_password,
        db=config.redis_db
    )
    
    redis_connected = await redis_coordinator.connect()
    if redis_connected:
        sys.stderr.write("[REDIS] Connected successfully\n")
    else:
        sys.stderr.write("[REDIS] Failed to connect, will use local state\n")


async def shutdown_redis():
    """Close Redis connection on shutdown"""
    global redis_coordinator
    if redis_coordinator:
        await redis_coordinator.close()
        sys.stderr.write("[REDIS] Connection closed\n")


def shutdown_datadog_logs():
    """Cleanup Datadog log handler on shutdown"""
    global datadog_log_handler
    if datadog_log_handler:
        datadog_log_handler.stop()
        sys.stderr.write("[DATADOG] Log handler stopped and flushed\n")


def init_sentry_on_startup():
    """Initialize Sentry error tracking"""
    global sentry_enabled
    
    sys.stderr.write("[SENTRY] Initializing error tracking...\n")
    sentry_enabled = init_sentry()
    
    if sentry_enabled:
        # Set user context from SSH connection
        ssh_conn = os.environ.get("SSH_CONNECTION", "")
        username = os.environ.get("USER") or os.environ.get("SYSLOG_USER")
        
        if ssh_conn:
            client_ip = ssh_conn.split()[0]
            set_user_context(username=username, ip_address=client_ip)
            sys.stderr.write(f"[SENTRY] User context set: {username} from {client_ip}\n")
        
        sys.stderr.write("[SENTRY] Error tracking enabled\n")
    else:
        sys.stderr.write("[SENTRY] Error tracking disabled (SENTRY_DSN not configured)\n")


def init_datadog_on_startup():
    """Initialize Datadog APM and metrics (Phase 3)"""
    global datadog_enabled, datadog_log_handler
    
    # Check if Datadog is configured
    if not config.dd_configured:
        sys.stderr.write("[DATADOG] Not configured (DD_ENABLED=false or missing credentials)\n")
        return
    
    sys.stderr.write("[DATADOG] Initializing APM and metrics...\n")
    datadog_enabled = init_datadog(
        api_key=config.dd_api_key,
        app_key=config.dd_app_key,
        site=config.dd_site,
        service_name=config.dd_service_name,
        env=config.dd_env,
        version=config.dd_version,
        agent_host=config.dd_agent_host,
        agent_port=config.dd_agent_port,
        trace_agent_port=config.dd_trace_agent_port
    )
    
    if datadog_enabled:
        sys.stderr.write(f"[DATADOG] Enabled: service={config.dd_service_name}, env={config.dd_env}\n")
        
        # Phase 3.5: Setup log aggregation if configured
        if config.send_logs_to_datadog:
            sys.stderr.write("[DATADOG] Setting up log aggregation...\n")
            datadog_log_handler = setup_datadog_logging(
                api_key=config.dd_api_key,
                service=config.dd_service_name,
                env=config.dd_env,
                site=config.dd_site,
                logger_name="log-ai",
                level=log_level
            )
            
            if datadog_log_handler:
                sys.stderr.write("[DATADOG] Log aggregation enabled - logs will be sent to Datadog\n")
            else:
                sys.stderr.write("[DATADOG] Log aggregation setup failed\n")
        else:
            sys.stderr.write("[DATADOG] Log aggregation disabled (SEND_LOGS_TO_DATADOG=false)\n")
    else:
        sys.stderr.write("[DATADOG] Initialization failed, continuing without APM/metrics\n")


def get_search_semaphore():
    """
    Get search semaphore - uses Redis if available, falls back to local asyncio.Semaphore.
    Returns a context manager for 'async with' usage.
    """
    if redis_connected and redis_coordinator and redis_coordinator.redis:
        return RedisSemaphore(
            redis_coordinator.redis,
            key_name="global_searches",
            max_count=config.max_global_searches,
            retry_delay=config.redis_retry_delay,
            max_retries=config.redis_max_retries
        )
    else:
        # Fallback to local semaphore
        return asyncio.Semaphore(config.max_global_searches)


def get_search_cache():
    """
    Get search cache - uses Redis if available, falls back to local SearchCache.
    Returns a cache object with get() and put() methods.
    """
    if redis_connected and redis_coordinator and redis_coordinator.redis:
        return RedisCache(
            redis_coordinator.redis,
            ttl_seconds=config.cache_ttl_minutes * 60,
            max_size_mb=config.cache_max_size_mb
        )
    else:
        # Fallback to local cache
        return SearchCache()


def get_metrics():
    """
    Get metrics tracker - uses Redis if available, falls back to no-op.
    Returns a metrics object with increment_counter() and record_timing() methods.
    """
    if redis_connected and redis_coordinator and redis_coordinator.redis:
        return RedisMetrics(redis_coordinator.redis)
    else:
        # Return no-op metrics (could implement local metrics later)
        return None


# Global semaphore for concurrency control (deprecated, use get_search_semaphore())
global_search_semaphore = asyncio.Semaphore(MAX_GLOBAL_SEARCHES)

# =============================================================================
# CACHE IMPLEMENTATION
# =============================================================================

@dataclass
class CacheEntry:
    """Single cache entry with metadata"""
    key: str
    matches: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    size_bytes: int
    timestamp: float


class SearchCache:
    """LRU cache with size and TTL limits"""
    
    def __init__(self):
        self.entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self.total_size_bytes = 0
        self.config_mtime = 0
        self.hits = 0
        self.misses = 0
        
    def _check_config_invalidation(self):
        """Invalidate cache if config file changed"""
        config_path = Path(__file__).parent.parent / "config" / "services.yaml"
        if config_path.exists():
            current_mtime = config_path.stat().st_mtime
            if self.config_mtime == 0:
                self.config_mtime = current_mtime
            elif current_mtime > self.config_mtime:
                sys.stderr.write(f"[CACHE] Config file changed, invalidating cache\n")
                self.clear()
                self.config_mtime = current_mtime
    
    def _make_key(self, services: List[str], query: str, time_range: Dict[str, int]) -> str:
        """Generate cache key from search parameters"""
        # Sort services for order-independence
        services_sorted = tuple(sorted(services))
        
        # Convert datetime objects to ISO strings for JSON serialization
        time_range_serializable = {}
        for key, value in time_range.items():
            if isinstance(value, datetime):
                time_range_serializable[key] = value.isoformat()
            else:
                time_range_serializable[key] = value
        
        time_str = json.dumps(time_range_serializable, sort_keys=True)
        key_str = f"{services_sorted}:{query}:{time_str}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _evict_lru(self):
        """Evict least recently used entry"""
        if not self.entries:
            return
        key, entry = self.entries.popitem(last=False)
        self.total_size_bytes -= entry.size_bytes
        sys.stderr.write(f"[CACHE] Evicted LRU entry {key[:8]} ({entry.size_bytes / 1024:.1f} KB)\n")
    
    def _evict_until_fits(self, needed_bytes: int):
        """Evict entries until we have space"""
        max_bytes = CACHE_MAX_SIZE_MB * 1024 * 1024
        while self.entries and (self.total_size_bytes + needed_bytes > max_bytes or len(self.entries) >= CACHE_MAX_ENTRIES):
            self._evict_lru()
    
    def get(self, services: List[str], query: str, time_range: Dict[str, int]) -> Optional[Tuple[List[Dict], Dict]]:
        """Get cached result if valid"""
        self._check_config_invalidation()
        
        key = self._make_key(services, query, time_range)
        if key not in self.entries:
            self.misses += 1
            return None
        
        entry = self.entries[key]
        age_minutes = (time.time() - entry.timestamp) / 60
        
        if age_minutes > CACHE_TTL_MINUTES:
            # Expired
            del self.entries[key]
            self.total_size_bytes -= entry.size_bytes
            self.misses += 1
            sys.stderr.write(f"[CACHE] Entry {key[:8]} expired ({age_minutes:.1f} min old)\n")
            return None
        
        # Move to end (most recently used)
        self.entries.move_to_end(key)
        self.hits += 1
        hit_rate = self.hits / (self.hits + self.misses) * 100
        sys.stderr.write(f"[CACHE] HIT {key[:8]} (hit rate: {hit_rate:.1f}%)\n")
        
        return entry.matches, entry.metadata
    
    def put(self, services: List[str], query: str, time_range: Dict[str, int], 
            matches: List[Dict], metadata: Dict):
        """Store result in cache"""
        key = self._make_key(services, query, time_range)
        
        # Calculate size
        size_bytes = len(json.dumps({"matches": matches, "metadata": metadata}).encode())
        
        # Don't cache huge results
        if size_bytes > CACHE_MAX_SIZE_MB * 1024 * 1024 / 10:  # Max 10% of cache size
            sys.stderr.write(f"[CACHE] Skipping {key[:8]} (too large: {size_bytes / 1024 / 1024:.1f} MB)\n")
            return
        
        # Evict if necessary
        self._evict_until_fits(size_bytes)
        
        # Store
        entry = CacheEntry(
            key=key,
            matches=matches,
            metadata=metadata,
            size_bytes=size_bytes,
            timestamp=time.time()
        )
        
        if key in self.entries:
            # Update existing
            old_entry = self.entries[key]
            self.total_size_bytes -= old_entry.size_bytes
        
        self.entries[key] = entry
        self.total_size_bytes += size_bytes
        
        sys.stderr.write(f"[CACHE] PUT {key[:8]} ({size_bytes / 1024:.1f} KB, "
                        f"total: {self.total_size_bytes / 1024 / 1024:.1f} MB, "
                        f"entries: {len(self.entries)})\n")
    
    def clear(self):
        """Clear all cache entries"""
        self.entries.clear()
        self.total_size_bytes = 0


# Global cache instance (kept for backward compatibility/fallback)
# NOTE: Use get_search_cache() instead, which returns Redis cache if available
search_cache = SearchCache()

# =============================================================================
# FILE OUTPUT HELPERS
# =============================================================================

def ensure_output_dir():
    """Create output directory if it doesn't exist"""
    FILE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def generate_output_filename(services: List[str], is_partial: bool = False) -> Path:
    """Generate filename for overflow results in session directory"""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    services_str = "-".join(services)[:50]  # Limit length
    unique_id = str(uuid.uuid4())[:8]
    
    prefix = "logai-partial" if is_partial else "logai-search"
    filename = f"{prefix}-{timestamp}-{services_str}-{unique_id}.json"
    
    # Store results in session directory for easy retrieval
    return LOG_DIR / filename


def save_matches_to_file(matches: List[Dict], filepath: Path) -> bool:
    """Save matches to JSON file"""
    try:
        logger.debug(f"Saving {len(matches)} matches to {filepath}")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(matches, f, indent=2)
        sys.stderr.write(f"[FILE] Saved {len(matches)} matches to {filepath}\n")
        logger.info(f"Successfully saved {len(matches)} matches to {filepath}")
        return True
    except Exception as e:
        sys.stderr.write(f"[FILE] Error saving to {filepath}: {e}\n")
        logger.error(f"Failed to save to {filepath}: {e}")
        return False


async def cleanup_old_files_task():
    """Background task to clean up old result files"""
    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL_HOURS * 3600)
            
            if not FILE_OUTPUT_DIR.exists():
                continue
            
            cutoff_time = time.time() - (FILE_RETENTION_HOURS * 3600)
            deleted_count = 0
            freed_bytes = 0
            
            for filepath in FILE_OUTPUT_DIR.glob("logai-*.json"):
                try:
                    # Parse timestamp from filename
                    parts = filepath.stem.split('-')
                    if len(parts) >= 3:
                        timestamp_str = parts[2]  # YYYYMMDD
                        file_time = datetime.strptime(timestamp_str, "%Y%m%d").timestamp()
                        
                        if file_time < cutoff_time:
                            size = filepath.stat().st_size
                            filepath.unlink()
                            deleted_count += 1
                            freed_bytes += size
                except Exception as e:
                    sys.stderr.write(f"[CLEANUP] Error processing {filepath}: {e}\n")
            
            if deleted_count > 0:
                sys.stderr.write(f"[CLEANUP] Deleted {deleted_count} old files ({freed_bytes / 1024 / 1024:.1f} MB freed)\n")
                
        except Exception as e:
            sys.stderr.write(f"[CLEANUP] Task error: {e}\n")


# =============================================================================
# STREAMING SEARCH IMPLEMENTATION
# =============================================================================

class ProgressTracker:
    """Track and report search progress"""
    
    def __init__(self, total_files: int, services: List[str]):
        self.total_files = total_files
        self.services = services
        self.per_service_matches: Dict[str, int] = {svc: 0 for svc in services}
        self.total_matches = 0
        self.files_searched = 0
        self.last_report_time = time.time()
        self.last_report_count = 0
    
    def add_match(self, service: str):
        """Record a match"""
        self.per_service_matches[service] += 1
        self.total_matches += 1
    
    def should_report(self) -> bool:
        """Check if we should report progress"""
        now = time.time()
        time_since_last = now - self.last_report_time
        matches_since_last = self.total_matches - self.last_report_count
        
        # Use different thresholds based on result size
        threshold = PROGRESS_EVERY_N_MATCHES_LARGE if self.total_matches > 1000 else PROGRESS_EVERY_N_MATCHES_SMALL
        
        # Report if enough matches OR enough time passed
        if matches_since_last >= threshold or (matches_since_last > 0 and time_since_last >= PROGRESS_MIN_INTERVAL_SECONDS):
            self.last_report_time = now
            self.last_report_count = self.total_matches
            return True
        return False
    
    def report(self):
        """Emit progress to stderr"""
        if len(self.services) == 1:
            sys.stderr.write(f"[PROGRESS] {self.total_matches} matches\n")
        else:
            breakdown = ", ".join([f"{svc}: {count}" for svc, count in self.per_service_matches.items()])
            sys.stderr.write(f"[PROGRESS] {self.total_matches} total ({breakdown})\n")
        sys.stderr.flush()


def parse_json_content(content: str) -> Any:
    """
    Try to parse content as JSON. If successful, return parsed object.
    If parsing fails, return original string.
    """
    try:
        return json.loads(content)
    except (json.JSONDecodeError, ValueError):
        # Not JSON or invalid JSON, return as-is
        return content


async def stream_ripgrep_search(
    files: List[str],
    query: str,
    service_name: str,
    progress: ProgressTracker
) -> List[Dict[str, Any]]:
    """Stream search results from ripgrep subprocess"""
    matches = []
    
    try:
        # Track files searched
        progress.files_searched = len(files)
        
        # Build ripgrep command: pattern must come before files
        cmd = ["rg", "-i", "-n", "-j", "8", query] + files
        
        # Start subprocess
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Read stdout line by line
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            
            try:
                line_str = line.decode('utf-8').strip()
                if not line_str:
                    continue
                
                # Parse ripgrep output: file:line:content
                parts = line_str.split(':', 2)
                if len(parts) >= 3:
                    # Try to parse content as JSON
                    parsed_content = parse_json_content(parts[2])
                    
                    match = {
                        "file": parts[0],
                        "line": int(parts[1]) if parts[1].isdigit() else 0,
                        "content": parsed_content,
                        "service": service_name
                    }
                    matches.append(match)
                    progress.add_match(service_name)
                    
                    # Report progress if needed
                    if progress.should_report():
                        progress.report()
                        
            except Exception as e:
                sys.stderr.write(f"[SEARCH] Error parsing line: {e}\n")
        
        # Wait for process to complete
        await process.wait()
        
    except Exception as e:
        sys.stderr.write(f"[SEARCH] Ripgrep error for {service_name}: {e}\n")
        raise
    
    return matches


async def stream_grep_search(
    files: List[str],
    query: str,
    service_name: str,
    progress: ProgressTracker
) -> List[Dict[str, Any]]:
    """Stream search results from grep subprocess"""
    matches = []
    
    try:
        # Track files searched
        progress.files_searched = len(files)
        
        # Use xargs + grep
        file_list = "\0".join(files) + "\0"
        
        cmd = ["xargs", "-0", "-P", "8", "grep", "-i", "-n", query]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Write file list to stdin
        process.stdin.write(file_list.encode())
        process.stdin.close()
        
        # Read stdout line by line
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            
            try:
                line_str = line.decode('utf-8').strip()
                if not line_str:
                    continue
                
                # Parse grep output: file:line:content
                parts = line_str.split(':', 2)
                if len(parts) >= 3:
                    # Try to parse content as JSON
                    parsed_content = parse_json_content(parts[2])
                    
                    match = {
                        "file": parts[0],
                        "line": int(parts[1]) if parts[1].isdigit() else 0,
                        "content": parsed_content,
                        "service": service_name
                    }
                    matches.append(match)
                    progress.add_match(service_name)
                    
                    if progress.should_report():
                        progress.report()
                        
            except Exception as e:
                sys.stderr.write(f"[SEARCH] Error parsing line: {e}\n")
        
        await process.wait()
        
    except Exception as e:
        sys.stderr.write(f"[SEARCH] Grep error for {service_name}: {e}\n")
        raise
    
    return matches


async def search_single_service(
    service_name: str,
    query: str,
    config: AppConfig,
    time_range: Dict[str, int],
    progress: ProgressTracker,
    semaphore: asyncio.Semaphore
) -> List[Dict[str, Any]]:
    """Search a single service with concurrency control"""
    async with semaphore:
        target_service = next((s for s in config.services if s.name == service_name), None)
        if not target_service:
            sys.stderr.write(f"[SEARCH] Service not found: {service_name}\n")
            return []
        
        # Find log files using datetime range
        files = find_log_files(
            target_service,
            start_hour=time_range["start_datetime"],
            end_hour=time_range["end_datetime"]
        )
        
        if not files:
            sys.stderr.write(f"[SEARCH] No files found for {service_name}\n")
            return []
        
        sys.stderr.write(f"[SEARCH] Searching {len(files)} files for {service_name}\n")
        
        # Execute search
        if HAS_RIPGREP:
            return await stream_ripgrep_search(files, query, service_name, progress)
        else:
            return await stream_grep_search(files, query, service_name, progress)


# =============================================================================
# FORMAT HELPERS
# =============================================================================

def format_matches_text(matches: List[Dict], metadata: Dict) -> str:
    """Format matches as human-readable text"""
    lines = []
    
    # Header with metadata
    lines.append("=== Search Results ===")
    lines.append(f"Services: {', '.join(metadata['services'])}")
    lines.append(f"Files searched: {metadata['files_searched']}")
    lines.append(f"Duration: {metadata['duration_seconds']:.2f}s")
    lines.append(f"Total matches: {metadata['total_matches']}")
    
    if metadata.get('cached'):
        lines.append("Source: CACHED")
    
    if metadata.get('partial'):
        lines.append(f"⚠️  PARTIAL RESULTS (error occurred)")
    
    if metadata.get('overflow'):
        lines.append(f"Showing: first {len(matches)} of {metadata['total_matches']}")
    else:
        lines.append(f"Showing: {len(matches)}")
    
    lines.append("=== Matches ===")
    lines.append("")
    
    # Matches
    for match in matches:
        service = match.get('service', 'unknown')
        file = Path(match.get('file', '')).name
        line_num = match.get('line', 0)
        content = match.get('content', '')
        lines.append(f"[{service}] {file}:{line_num} {content}")
    
    # Show file location (always present now)
    if metadata.get('saved_to'):
        lines.append("")
        lines.append("=== Results File ===")
        lines.append(f"All results saved to: {metadata['saved_to']}")
        if metadata.get('overflow'):
            lines.append(f"(Showing first {PREVIEW_MATCHES_LIMIT} of {metadata['total_matches']} matches above)")
        lines.append(f"Use read_search_file tool to retrieve full results")
    
    if metadata.get('error'):
        lines.append("")
        lines.append(f"⚠️  Error: {metadata['error']}")
    
    return "\n".join(lines)


def format_matches_json(matches: List[Dict], metadata: Dict) -> str:
    """Format matches as JSON"""
    result = {
        "matches": matches,
        "metadata": metadata
    }
    return json.dumps(result, indent=2)


async def metrics_monitoring_task():
    """
    Background task to periodically report infrastructure metrics (Phase 3.3 & 3.4).
    Monitors Redis connection pool and system infrastructure every 60 seconds.
    """
    sys.stderr.write("[METRICS] Starting metrics monitoring task\n")
    
    # Initialize infrastructure monitor (Phase 3.4)
    infra_monitor = get_infrastructure_monitor(log_dir=LOG_DIR)
    
    while True:
        try:
            await asyncio.sleep(60)  # Report every 60 seconds
            
            metrics = get_metrics_collector()
            
            # Report Redis connection pool if available (Phase 3.3)
            if redis_connected and redis_coordinator and redis_coordinator.redis:
                try:
                    # Get connection pool info from Redis client
                    pool = redis_coordinator.redis.connection_pool
                    if hasattr(pool, '_available_connections') and hasattr(pool, '_created_connections'):
                        active = len(pool._created_connections) - len(pool._available_connections)
                        max_connections = pool.max_connections if hasattr(pool, 'max_connections') else 50
                        
                        metrics.report_redis_pool_status(
                            active_connections=active,
                            max_connections=max_connections
                        )
                        sys.stderr.write(f"[METRICS] Redis pool: {active}/{max_connections} active\n")
                except Exception as e:
                    sys.stderr.write(f"[METRICS] Failed to get Redis pool stats: {e}\n")
            
            # Collect and report infrastructure metrics (Phase 3.4)
            try:
                sys_metrics = infra_monitor.collect_metrics()
                infra_monitor.report_to_datadog(sys_metrics)
                
                # Monitor log directory
                log_stats = infra_monitor.monitor_log_directory()
                if log_stats:
                    sys.stderr.write(f"[METRICS] Log directory: {log_stats['file_count']} files, {log_stats['total_size_mb']:.2f} MB\n")
                
                # Get health summary
                health = infra_monitor.get_health_summary()
                if health['status'] != 'healthy':
                    sys.stderr.write(f"[METRICS] System health: {health['status']} - {', '.join(health['issues'])}\n")
                
                sys.stderr.write(f"[METRICS] System: CPU {sys_metrics.cpu_percent:.1f}%, Memory {sys_metrics.memory_percent:.1f}%, Disk {sys_metrics.disk_percent:.1f}%\n")
                sys.stderr.write(f"[METRICS] Process: {sys_metrics.process_memory_mb:.1f} MB, {sys_metrics.process_threads} threads\n")
            except Exception as e:
                sys.stderr.write(f"[METRICS] Failed to collect infrastructure metrics: {e}\n")
            
        except Exception as e:
            sys.stderr.write(f"[METRICS] Error in monitoring task: {e}\n")
            # Continue running even if error occurs


# =============================================================================
# MAIN SERVER
# =============================================================================

async def main():
    # Initialize Sentry first (synchronous)
    init_sentry_on_startup()
    
    # Initialize Datadog APM and metrics (Phase 3)
    init_datadog_on_startup()
    
    # Initialize Redis (if enabled)
    await init_redis()
    
    # Ensure output directory exists
    ensure_output_dir()
    
    # Start cleanup task
    cleanup_task = asyncio.create_task(cleanup_old_files_task())
    
    # Start metrics monitoring task (Phase 3.3)
    metrics_task = asyncio.create_task(metrics_monitoring_task())
    
    config = load_config()
    server = Server("log-ai")
    
    sys.stderr.write(f"[SERVER] Starting with {len(config.services)} services\n")
    sys.stderr.write(f"[SERVER] Ripgrep available: {HAS_RIPGREP}\n")
    sys.stderr.write(f"[SERVER] Output directory: {FILE_OUTPUT_DIR}\n")
    sys.stderr.write(f"[SERVER] Cache: {CACHE_MAX_ENTRIES} entries, {CACHE_MAX_SIZE_MB} MB, {CACHE_TTL_MINUTES} min TTL\n")
    sys.stderr.write(f"[SERVER] Concurrency: {MAX_PARALLEL_SEARCHES_PER_CALL} per call, {MAX_GLOBAL_SEARCHES} global\n")
    sys.stderr.write(f"[SERVER] Redis: {'Enabled' if redis_connected else 'Disabled (using local state)'}\n")
    sys.stderr.write(f"[SERVER] Datadog: {'Enabled' if datadog_enabled else 'Disabled'}\n")

    @server.list_resources()
    async def handle_list_resources() -> list[types.Resource]:
        return []

    @server.read_resource()
    async def handle_read_resource(uri: types.AnyUrl) -> str | bytes:
        return "Direct file reading disabled for scale performance."

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="search_logs",
                description="""Search for log entries across one or more services. Returns structured results with metadata.

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
                            "oneOf": [
                                {"type": "string"},
                                {"type": "array", "items": {"type": "string"}}
                            ],
                            "description": "Service name (flexible matching - can be exact name, base name like 'auth', or partial match like 'edr-proxy')"
                        },
                        "locale": {
                            "type": "string",
                            "description": "Optional locale filter: 'ca' (Canada), 'us' (United States), or 'na' (North America)",
                            "enum": ["ca", "us", "na"]
                        },
                        "query": {
                            "type": "string",
                            "description": "Keyword or pattern to search for"
                        },
                        "start_time_utc": {
                            "type": "string",
                            "description": "Start time in UTC (ISO 8601 format: '2026-01-05T23:00:00Z')"
                        },
                        "end_time_utc": {
                            "type": "string",
                            "description": "End time in UTC (ISO 8601 format: '2026-01-06T05:00:00Z')"
                        },
                        "format": {
                            "type": "string",
                            "enum": ["text", "json"],
                            "description": "Output format (default: text)",
                            "default": "text"
                        }
                    },
                    "required": ["service_name", "query", "start_time_utc", "end_time_utc"]
                }
            ),
            types.Tool(
                name="read_search_file",
                description="Read a previously saved search result file. Use this to retrieve full results when search returned a file path.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the search result file (e.g., /tmp/log-ai/logai-search-*.json)"
                        },
                        "format": {
                            "type": "string",
                            "enum": ["text", "json"],
                            "description": "Output format (default: text)",
                            "default": "text"
                        }
                    },
                    "required": ["file_path"]
                }
            ),
            types.Tool(
                name="query_sentry_issues",
                description="""Query Sentry issues for one or more services. Returns recent errors and their details.

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
                            "description": "Service name (supports fuzzy matching and variations like 'auth', 'edr-proxy', 'edr_proxy')"
                        },
                        "locale": {
                            "type": "string",
                            "description": "Optional: Filter to specific locale (ca/us/na)",
                            "enum": ["ca", "us", "na"]
                        },
                        "query": {
                            "type": "string",
                            "description": "Sentry query string (default: 'is:unresolved'). Examples: 'is:unresolved issue.priority:[high, medium]', 'is:unresolved assigned:me'",
                            "default": "is:unresolved"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max number of issues to return (default: 25)",
                            "default": 25
                        },
                        "statsPeriod": {
                            "type": "string",
                            "description": "Time period for stats: 1h, 24h, 7d, 14d, 30d (default: 24h)",
                            "default": "24h"
                        }
                    },
                    "required": ["service_name"]
                }
            ),
            types.Tool(
                name="get_sentry_issue_details",
                description="Get detailed information about a specific Sentry issue including stack traces, breadcrumbs, and context.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "issue_id": {
                            "type": "string",
                            "description": "Sentry issue ID (e.g., '18')"
                        }
                    },
                    "required": ["issue_id"]
                }
            ),
            types.Tool(
                name="search_sentry_traces",
                description="""Search performance traces in Sentry for one or more services. Useful for finding slow transactions.

Service name supports flexible matching:
- "auth" → all auth services
- "edr-proxy" → all edr-proxy services
- Use 'locale' to filter by region.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service_name": {
                            "type": "string",
                            "description": "Service name (supports fuzzy matching)"
                        },
                        "locale": {
                            "type": "string",
                            "description": "Optional: Filter to specific locale (ca/us/na)",
                            "enum": ["ca", "us", "na"]
                        },
                        "query": {
                            "type": "string",
                            "description": "Search query (e.g., 'transaction.duration:>5s' for slow traces)",
                            "default": ""
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max traces to return (default: 10)",
                            "default": 10
                        },
                        "statsPeriod": {
                            "type": "string",
                            "description": "Time period: 1h, 24h, 7d (default: 24h)",
                            "default": "24h"
                        }
                    },
                    "required": ["service_name"]
                }
            )
        ]

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        if not arguments:
            raise ValueError("Missing arguments")

        if name == "search_logs":
            return await search_logs_handler(arguments, config)
        elif name == "read_search_file":
            return await read_search_file_handler(arguments)
        elif name == "query_sentry_issues":
            return await query_sentry_issues_handler(arguments, config)
        elif name == "get_sentry_issue_details":
            return await get_sentry_issue_details_handler(arguments)
        elif name == "search_sentry_traces":
            return await search_sentry_traces_handler(arguments, config)
        else:
            raise ValueError(f"Unknown tool: {name}")

    async def search_logs_handler(args: dict, config: AppConfig) -> list[types.TextContent]:
        """Handle search_logs tool with streaming and all features"""
        start_time = time.time()
        
        # Parse arguments
        service_name_arg = args.get("service_name")
        locale = args.get("locale")
        query = args.get("query")
        format_type = args.get("format", "text")
        user_tz = args.get("timezone", "UTC")
        
        # Resolve service names with flexible matching
        service_queries = service_name_arg if isinstance(service_name_arg, list) else [service_name_arg]
        services = []
        for svc_query in service_queries:
            matched = resolve_service_names(svc_query, config.services, locale=locale)
            if not matched:
                suggestions = find_similar_services(svc_query, config.services)
                error_msg = f"Error: Service not found: {svc_query}"
                if suggestions:
                    error_msg += f"\n\nDid you mean one of these?\n  - " + "\n  - ".join(suggestions)
                return [types.TextContent(type="text", text=error_msg)]
            services.extend([s.name for s in matched])
        
        # Remove duplicates while preserving order
        services = list(dict.fromkeys(services))
        
        # Parse UTC timestamps (required)
        start_time_utc = args.get("start_time_utc")
        end_time_utc = args.get("end_time_utc")
        
        if not start_time_utc or not end_time_utc:
            return [types.TextContent(type="text", text="Error: Both start_time_utc and end_time_utc are required parameters.")]
        
        try:
            from dateutil import parser as date_parser
            start_dt = date_parser.isoparse(start_time_utc)
            end_dt = date_parser.isoparse(end_time_utc)
            
            time_range = {
                "start_datetime": start_dt,
                "end_datetime": end_dt
            }
            logger.info(f"UTC time range: {start_dt} to {end_dt}")
            
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error: Invalid UTC timestamp format. Expected ISO 8601 (e.g., '2026-01-05T23:00:00Z'). Error: {e}")]
        
        logger.info(f"search_logs: services={services}, query='{query}', time_range={time_range}, format={format_type}")
        sys.stderr.write(f"[REQUEST] search_logs: services={services}, query='{query}', time_range={time_range}, format={format_type}\n")
        
        # Start Datadog APM trace (Phase 3.2)
        with trace_search_operation(
            service=",".join(services),
            pattern=query,
            time_range=time_range
        ) as span:
            try:
                return await _execute_search(
                    services, query, time_range, format_type, user_tz,
                    config, start_time, span
                )
            except Exception as e:
                # Tag error in span
                if span:
                    span.set_tag("error", True)
                    span.set_tag("error.type", type(e).__name__)
                    span.set_tag("error.message", str(e))
                
                # Record error metrics (Phase 3.3)
                metrics = get_metrics_collector()
                metrics.record_error(
                    error_type=type(e).__name__,
                    service=services[0] if services else None
                )
                
                raise
    
    async def _execute_search(
        services: list,
        query: str,
        time_range: dict,
        format_type: str,
        user_tz: str,
        config: AppConfig,
        start_time: float,
        span: Any
    ) -> list[types.TextContent]:
        """Execute search with tracing - extracted for better trace context"""
        
        # Add Sentry breadcrumb for search start
        if sentry_enabled:
            for svc in services:
                add_search_breadcrumb(
                    service_name=svc,
                    action="search_started",
                    query=query[:50],  # Truncate long queries
                    time_range=str(time_range)
                )
        
        # Get cache instance (Redis or local)
        cache = get_search_cache()
        
        # Get metrics collector (Phase 3.3)
        metrics = get_metrics_collector()
        
        # Check cache
        cached = cache.get(services, query, time_range)
        if cached:
            matches, metadata = cached
            metadata["cached"] = True
            metadata["duration_seconds"] = time.time() - start_time
            
            # Record cache hit metrics (Phase 3.3)
            metrics.record_cache_hit(services[0] if services else "unknown")
            
            # Add Datadog APM tags for cache hit (Phase 3.2)
            if span:
                span.set_tag("cache.hit", True)
                span.set_tag("result.count", len(matches))
                span.set_tag("duration_ms", metadata["duration_seconds"] * 1000)
            
            # Record Datadog metrics (Phase 3.2)
            record_metric(
                "log_ai.search.duration_ms",
                metadata["duration_seconds"] * 1000,
                tags=[f"service:{services[0]}", "cached:true"],
                metric_type="histogram"
            )
            record_metric(
                "log_ai.search.result_count",
                len(matches),
                tags=[f"service:{services[0]}", "cached:true"],
                metric_type="histogram"
            )
            increment_counter("log_ai.cache.hits", tags=[f"service:{services[0]}"])
            
            # Track cache hit in Sentry
            if sentry_enabled:
                for svc in services:
                    service_config = next((s for s in config.services if s.name == svc), None)
                    if service_config:
                        capture_search_performance(
                            service_config=service_config,
                            pattern=query,
                            duration_ms=metadata["duration_seconds"] * 1000,
                            matched_files=metadata.get("files_searched", 0),
                            result_count=len(matches),
                            cache_hit=True
                        )
            
            if format_type == "json":
                return [types.TextContent(type="text", text=format_matches_json(matches, metadata))]
            else:
                return [types.TextContent(type="text", text=format_matches_text(matches, metadata))]
        
        # Get semaphore instance (Redis or local)
        search_semaphore = get_search_semaphore()
        
        # Report semaphore utilization before acquiring (Phase 3.3)
        if isinstance(search_semaphore, asyncio.Semaphore):
            # Local semaphore - report available slots
            metrics.report_semaphore_utilization(
                available_slots=search_semaphore._value,
                max_slots=MAX_GLOBAL_SEARCHES
            )
        
        # Acquire global semaphore
        async with search_semaphore:
            try:
                # Setup
                progress = ProgressTracker(0, services)
                per_call_semaphore = asyncio.Semaphore(MAX_PARALLEL_SEARCHES_PER_CALL)
                all_matches = []
                total_files = 0
                error_occurred = None
                
                # Execute searches with timeout
                try:
                    search_tasks = [
                        search_single_service(svc, query, config, time_range, progress, per_call_semaphore)
                        for svc in services
                    ]
                    
                    results = await asyncio.wait_for(
                        asyncio.gather(*search_tasks, return_exceptions=True),
                        timeout=AUTO_CANCEL_TIMEOUT_SECONDS
                    )
                    
                    # Collect results
                    for result in results:
                        if isinstance(result, Exception):
                            error_msg = str(result)
                            sys.stderr.write(f"[ERROR] Search failed: {error_msg}\n")
                            error_occurred = error_msg
                        elif isinstance(result, list):
                            all_matches.extend(result)
                     
                except asyncio.TimeoutError:
                    error_occurred = f"Search auto-cancelled after {AUTO_CANCEL_TIMEOUT_SECONDS} seconds"
                    sys.stderr.write(f"[TIMEOUT] {error_occurred}\n")
                
                # Build metadata
                duration = time.time() - start_time
                metadata = {
                    "files_searched": progress.total_files,
                    "duration_seconds": duration,
                    "total_matches": len(all_matches),
                    "cached": False,
                    "services": services
                }
                
                if error_occurred:
                    metadata["error"] = error_occurred
                    metadata["partial"] = True
                
                # Always save results to file for user retrieval
                saved_file = None
                logger.debug(f"Search returned {len(all_matches)} matches")
                
                # Save all results to file in session directory
                is_partial = error_occurred is not None
                saved_file = generate_output_filename(services, is_partial)
                logger.info(f"Saving {len(all_matches)} matches to {saved_file}")
                
                if save_matches_to_file(all_matches, saved_file):
                    metadata["saved_to"] = str(saved_file)
                    logger.info(f"Results saved successfully to {saved_file}")
                    
                    # Determine preview size
                    if len(all_matches) > PREVIEW_MATCHES_LIMIT:
                        metadata["overflow"] = True
                        preview_matches = all_matches[:PREVIEW_MATCHES_LIMIT]
                        logger.debug(f"Returning preview of {PREVIEW_MATCHES_LIMIT} matches (total: {len(all_matches)})")
                    else:
                        preview_matches = all_matches
                        logger.debug(f"Returning all {len(all_matches)} matches in response")
                else:
                    # File save failed, return what we can
                    preview_matches = all_matches[:PREVIEW_MATCHES_LIMIT] if len(all_matches) > PREVIEW_MATCHES_LIMIT else all_matches
                    logger.warning(f"File save failed, returning {len(preview_matches)} matches in memory")
                
                # Cache if successful and not too large
                if not error_occurred and not metadata.get("overflow"):
                    cache.put(services, query, time_range, all_matches, metadata)
                
                # Record cache miss and overflow metrics (Phase 3.3)
                metrics.record_cache_miss(services[0] if services else "unknown")
                if metadata.get("overflow"):
                    metrics.record_overflow(services[0] if services else "unknown")
                if error_occurred:
                    metrics.record_timeout(services[0] if services else "unknown")
                
                # Add Datadog APM tags (Phase 3.2)
                if span:
                    span.set_tag("cache.hit", False)
                    span.set_tag("result.count", len(all_matches))
                    span.set_tag("duration_ms", duration * 1000)
                    span.set_tag("files_searched", metadata["files_searched"])
                    span.set_tag("overflow", metadata.get("overflow", False))
                    if error_occurred:
                        span.set_tag("partial_results", True)
                
                # Record Datadog metrics (Phase 3.2)
                record_metric(
                    "log_ai.search.duration_ms",
                    duration * 1000,
                    tags=[f"service:{services[0]}", "cached:false", f"overflow:{metadata.get('overflow', False)}"],
                    metric_type="histogram"
                )
                record_metric(
                    "log_ai.search.result_count",
                    len(all_matches),
                    tags=[f"service:{services[0]}", "cached:false"],
                    metric_type="histogram"
                )
                record_metric(
                    "log_ai.search.files_searched",
                    metadata["files_searched"],
                    tags=[f"service:{services[0]}"],
                    metric_type="histogram"
                )
                increment_counter("log_ai.cache.misses", tags=[f"service:{services[0]}"])
                
                if metadata.get("overflow"):
                    increment_counter("log_ai.search.overflows", tags=[f"service:{services[0]}"])
                    # Track overflow file size
                    if saved_file and saved_file.exists():
                        file_size = saved_file.stat().st_size
                        record_metric(
                            "log_ai.overflow.file_size_bytes",
                            file_size,
                            tags=[f"service:{services[0]}"],
                            metric_type="histogram"
                        )
                
                if error_occurred:
                    increment_counter("log_ai.search.timeouts", tags=[f"service:{services[0]}"])
                
                # Track performance in Sentry
                if sentry_enabled:
                    for svc in services:
                        service_config = next((s for s in config.services if s.name == svc), None)
                        if service_config:
                            capture_search_performance(
                                service_config=service_config,
                                pattern=query,
                                duration_ms=duration * 1000,
                                matched_files=metadata["files_searched"],
                                result_count=len(all_matches),
                                cache_hit=False
                            )
                
                sys.stderr.write(f"[COMPLETE] {len(all_matches)} matches in {duration:.2f}s\n")
                
                # Format response
                if format_type == "json":
                    return [types.TextContent(type="text", text=format_matches_json(preview_matches, metadata))]
                else:
                    return [types.TextContent(type="text", text=format_matches_text(preview_matches, metadata))]
                
            except Exception as e:
                # Capture error in Sentry with context
                if sentry_enabled:
                    for svc in services:
                        service_config = next((s for s in config.services if s.name == svc), None)
                        if service_config:
                            capture_error_context(
                                error=e,
                                service_config=service_config,
                                search_params=args,
                                user_ip=os.environ.get("SSH_CONNECTION", "").split()[0] if os.environ.get("SSH_CONNECTION") else None
                            )
                
                sys.stderr.write(f"[ERROR] Unexpected error: {e}\n")
                import traceback
                traceback.print_exc()
                return [types.TextContent(type="text", text=f"Error: {str(e)}")]

    async def read_search_file_handler(args: dict) -> list[types.TextContent]:
        """Handle read_search_file tool"""
        file_path_str = args.get("file_path")
        format_type = args.get("format", "text")
        
        if not file_path_str:
            return [types.TextContent(type="text", text="Error: file_path parameter is required")]
        
        # Security: validate path
        try:
            file_path = Path(file_path_str).resolve()
            base_dir = FILE_OUTPUT_DIR.resolve()
            
            # Check if file is within FILE_OUTPUT_DIR (including subdirectories)
            if not str(file_path).startswith(str(base_dir)):
                return [types.TextContent(type="text", text=f"Error: Invalid file path. Must be in {base_dir}")]
            
            if not file_path.name.startswith("logai-"):
                return [types.TextContent(type="text", text="Error: Invalid file name. Must start with 'logai-'")]
            
            if not file_path.exists():
                return [types.TextContent(type="text", text=f"Error: File not found: {file_path}")]
            
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error: Invalid file path: {e}")]
        
        try:
            # Read JSON file
            with open(file_path, 'r', encoding='utf-8') as f:
                matches = json.load(f)
            
            file_size_mb = file_path.stat().st_size / 1024 / 1024
            
            # Handle large files - don't try to return all matches
            if file_size_mb > 10:
                return [types.TextContent(type="text", text=f"Error: File too large ({file_size_mb:.2f} MB). Files over 10MB cannot be read via this tool. Use command line tools instead.")]
            
            metadata = {
                "file": str(file_path),
                "total_matches": len(matches),
                "file_size_mb": round(file_size_mb, 2)
            }
            
            if format_type == "json":
                result = {
                    "matches": matches,
                    "metadata": metadata
                }
                # Safely serialize - handle any encoding issues
                try:
                    json_str = json.dumps(result, indent=2, ensure_ascii=False)
                    return [types.TextContent(type="text", text=json_str)]
                except (TypeError, ValueError) as e:
                    return [types.TextContent(type="text", text=f"Error serializing JSON: {e}. Try format='text' instead.")]
            else:
                # Convert to text
                lines = []
                lines.append(f"=== File: {file_path.name} ===")
                lines.append(f"Total matches: {len(matches)}")
                lines.append(f"File size: {file_size_mb:.2f} MB")
                lines.append("=== Matches ===")
                lines.append("")
                
                for match in matches:
                    service = match.get('service', 'unknown')
                    file = Path(match.get('file', '')).name
                    line_num = match.get('line', 0)
                    content = match.get('content', '')
                    lines.append(f"[{service}] {file}:{line_num} {content}")
                
                return [types.TextContent(type="text", text="\n".join(lines))]
                
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error reading file: {e}")]

    async def query_sentry_issues_handler(args: dict, config: AppConfig) -> list[types.TextContent]:
        """Handle query_sentry_issues tool with multi-service support"""
        service_name = args.get("service_name")
        locale = args.get("locale")
        query = args.get("query", "is:unresolved")
        limit = args.get("limit", 25)
        time_period = args.get("statsPeriod", "24h")
        
        logger.debug(f"[SENTRY] query_sentry_issues called: service_name={service_name}, locale={locale}")
        
        # Resolve service name(s) with flexible matching
        matched_services = resolve_service_names(service_name, config.services, locale=locale)
        
        logger.debug(f"[SENTRY] Matched {len(matched_services)} services: {[s.name for s in matched_services]}")
        
        if not matched_services:
            suggestions = find_similar_services(service_name, config.services)
            error_msg = f"Error: Service not found: {service_name}"
            if suggestions:
                error_msg += f"\n\nDid you mean one of these?\n  - " + "\n  - ".join(suggestions)
            return [types.TextContent(type="text", text=error_msg)]
        
        # Aggregate results from all matched services
        all_issues = []
        services_queried = []
        projects_without_sentry = []
        
        # Query Sentry API for each matched service
        sentry_api = get_sentry_api()
        if not sentry_api.is_available():
            return [types.TextContent(type="text", text="Error: Sentry API not configured. Set SENTRY_AUTH_TOKEN environment variable.")]
        
        for service in matched_services:
            logger.debug(f"[SENTRY] Checking service {service.name}: sentry_service_name={service.sentry_service_name}")
            
            if not service.sentry_service_name:
                logger.debug(f"[SENTRY] Service {service.name} has no sentry_service_name - skipping")
                projects_without_sentry.append(service.name)
                continue  # Skip services without Sentry configuration
            
            # Get Sentry project ID from DSN
            sentry_project_id = service.get_sentry_project_id()
            if not sentry_project_id:
                logger.debug(f"[SENTRY] Service {service.name} has no project ID in DSN - skipping")
                projects_without_sentry.append(service.name)
                continue
            
            sentry_project = service.sentry_service_name
            logger.debug(f"[SENTRY] Querying Sentry project '{sentry_project}' (ID: {sentry_project_id}) for service {service.name}")
            
            # Query Sentry API using project ID
            result = sentry_api.query_issues(
                project=sentry_project_id,  # Use project ID, not slug
                query=query,
                limit=limit,
                statsPeriod=time_period
            )
            
            if result.get("success"):
                # Tag each issue with originating service
                for issue in result.get("issues", []):
                    issue["_source_service"] = service.name
                    issue["_sentry_project"] = sentry_project
                
                all_issues.extend(result.get("issues", []))
                services_queried.append(f"{service.name} → {sentry_project}")
        
        if not services_queried:
            error_msg = f"No Sentry configuration found for: {', '.join(s.name for s in matched_services)}"
            if projects_without_sentry:
                error_msg += f"\n\nServices without Sentry: {', '.join(projects_without_sentry)}"
            return [types.TextContent(type="text", text=error_msg)]
        
        # Format aggregated results
        lines = []
        lines.append("=== Sentry Issues Query Results ===")
        lines.append(f"Services: {', '.join(services_queried)}")
        lines.append(f"Query: {query}")
        lines.append(f"Time period: {time_period}")
        lines.append(f"Total issues: {len(all_issues)}")
        lines.append("")
        
        if not all_issues:
            lines.append("No issues found matching the query.")
        else:
            # Sort by event count (descending) and limit
            all_issues.sort(key=lambda x: x.get("count", 0), reverse=True)
            display_issues = all_issues[:limit]
            
            for issue in display_issues:
                source_service = issue.get("_source_service", "unknown")
                sentry_project = issue.get("_sentry_project", "unknown")
                issue_id = issue.get("id", "")
                title = issue.get("title", "No title")
                count = issue.get("count", 0)
                user_count = issue.get("userCount", 0)
                first_seen = issue.get("firstSeen", "")
                last_seen = issue.get("lastSeen", "")
                status = issue.get("status", "unknown")
                level = issue.get("level", "unknown")
                
                lines.append(f"Issue #{issue_id} [{source_service}] - {status.upper()}")
                lines.append(f"  Project: {sentry_project}")
                lines.append(f"  Title: {title}")
                lines.append(f"  Level: {level}")
                lines.append(f"  Count: {count} events")
                lines.append(f"  Affected users: {user_count}")
                lines.append(f"  First seen: {first_seen}")
                lines.append(f"  Last seen: {last_seen}")
                
                # Add culprit if available
                culprit = issue.get("culprit")
                if culprit:
                    lines.append(f"  Location: {culprit}")
                
                lines.append("")
        
        return [types.TextContent(type="text", text="\n".join(lines))]

    async def get_sentry_issue_details_handler(args: dict) -> list[types.TextContent]:
        """Handle get_sentry_issue_details tool"""
        issue_id = args.get("issue_id")
        
        if not issue_id:
            return [types.TextContent(type="text", text="Error: issue_id is required")]
        
        # Query Sentry API
        sentry_api = get_sentry_api()
        if not sentry_api.is_available():
            return [types.TextContent(type="text", text="Error: Sentry API not configured. Set SENTRY_AUTH_TOKEN environment variable.")]
        
        result = sentry_api.get_issue_details(issue_id)
        
        if not result.get("success"):
            return [types.TextContent(type="text", text=f"Error: {result.get('error', 'Unknown error')}")]
        
        # Format results
        issue = result.get("issue", {})
        lines = []
        lines.append(f"=== Sentry Issue #{issue_id} ===")
        lines.append("")
        
        # Basic info
        lines.append(f"Title: {issue.get('title', 'No title')}")
        lines.append(f"Status: {issue.get('status', 'unknown').upper()}")
        lines.append(f"Level: {issue.get('level', 'unknown')}")
        lines.append(f"Type: {issue.get('type', 'unknown')}")
        lines.append("")
        
        # Statistics
        lines.append("Statistics:")
        lines.append(f"  Total events: {issue.get('count', 0)}")
        lines.append(f"  Affected users: {issue.get('userCount', 0)}")
        lines.append(f"  First seen: {issue.get('firstSeen', 'unknown')}")
        lines.append(f"  Last seen: {issue.get('lastSeen', 'unknown')}")
        lines.append("")
        
        # Location
        culprit = issue.get("culprit")
        if culprit:
            lines.append(f"Location: {culprit}")
        
        # Metadata
        metadata = issue.get("metadata", {})
        if metadata:
            lines.append("")
            lines.append("Error Details:")
            error_type = metadata.get("type", '')
            error_value = metadata.get("value", '')
            if error_type:
                lines.append(f"  Type: {error_type}")
            if error_value:
                lines.append(f"  Message: {error_value}")
        
        # Tags
        tags = issue.get("tags", [])
        if tags:
            lines.append("")
            lines.append("Tags:")
            for tag in tags[:10]:  # Limit to first 10 tags
                key = tag.get("key", "")
                value = tag.get("value", "")
                if key and value:
                    lines.append(f"  {key}: {value}")
        
        # Permalink
        permalink = issue.get("permalink")
        if permalink:
            lines.append("")
            lines.append(f"View in Sentry: {permalink}")
        
        return [types.TextContent(type="text", text="\n".join(lines))]

    async def search_sentry_traces_handler(args: dict, config: AppConfig) -> list[types.TextContent]:
        """Handle search_sentry_traces tool with multi-service support"""
        service_name = args.get("service_name")
        locale = args.get("locale")
        query = args.get("query", "")
        limit = args.get("limit", 10)
        time_period = args.get("statsPeriod", "24h")
        
        logger.debug(f"[SENTRY] search_sentry_traces called: service_name={service_name}, locale={locale}")
        
        # Resolve service name(s) with flexible matching
        matched_services = resolve_service_names(service_name, config.services, locale=locale)
        
        logger.debug(f"[SENTRY] Matched {len(matched_services)} services: {[s.name for s in matched_services]}")
        
        if not matched_services:
            suggestions = find_similar_services(service_name, config.services)
            error_msg = f"Error: Service not found: {service_name}"
            if suggestions:
                error_msg += f"\n\nDid you mean one of these?\n  - " + "\n  - ".join(suggestions)
            return [types.TextContent(type="text", text=error_msg)]
        
        # Aggregate traces from all matched services
        all_traces = []
        services_queried = []
        projects_without_sentry = []
        
        # Query Sentry API for each matched service
        sentry_api = get_sentry_api()
        if not sentry_api.is_available():
            return [types.TextContent(type="text", text="Error: Sentry API not configured. Set SENTRY_AUTH_TOKEN environment variable.")]
        
        for service in matched_services:
            logger.debug(f"[SENTRY] Checking service {service.name}: sentry_service_name={service.sentry_service_name}")
            
            if not service.sentry_service_name:
                logger.debug(f"[SENTRY] Service {service.name} has no sentry_service_name - skipping")
                projects_without_sentry.append(service.name)
                continue  # Skip services without Sentry configuration
            
            # Get Sentry project ID from DSN
            sentry_project_id = service.get_sentry_project_id()
            if not sentry_project_id:
                logger.debug(f"[SENTRY] Service {service.name} has no project ID in DSN - skipping")
                projects_without_sentry.append(service.name)
                continue
            
            sentry_project = service.sentry_service_name
            logger.debug(f"[SENTRY] Querying Sentry project '{sentry_project}' (ID: {sentry_project_id}) for service {service.name}")
            
            # Query Sentry API using project ID
            result = sentry_api.search_traces(
                project=sentry_project_id,  # Use project ID, not slug
                query=query,
                limit=limit,
                statsPeriod=time_period
            )
            
            if result.get("success"):
                # Tag each trace with originating service
                for trace in result.get("traces", []):
                    trace["_source_service"] = service.name
                    trace["_sentry_project"] = sentry_project
                
                all_traces.extend(result.get("traces", []))
                services_queried.append(f"{service.name} → {sentry_project}")
        
        if not services_queried:
            error_msg = f"No Sentry configuration found for: {', '.join(s.name for s in matched_services)}"
            if projects_without_sentry:
                error_msg += f"\n\nServices without Sentry: {', '.join(projects_without_sentry)}"
            return [types.TextContent(type="text", text=error_msg)]
        
        # Format aggregated results
        lines = []
        lines.append("=== Sentry Performance Traces Query Results ===")
        lines.append(f"Services: {', '.join(services_queried)}")
        lines.append(f"Query: {query if query else '(all traces)'}")
        lines.append(f"Time period: {time_period}")
        lines.append(f"Total traces: {len(all_traces)}")
        lines.append("")
        
        if not all_traces:
            lines.append("No traces found matching the query.")
        else:
            # Sort by duration (descending) and limit
            all_traces.sort(key=lambda x: x.get("transaction.duration", 0), reverse=True)
            display_traces = all_traces[:limit]
            
            for trace in display_traces:
                source_service = trace.get("_source_service", "unknown")
                sentry_project = trace.get("_sentry_project", "unknown")
                transaction = trace.get("transaction", "unknown")
                duration = trace.get("transaction.duration", 0)
                timestamp = trace.get("timestamp", "")
                
                lines.append(f"Transaction: {transaction} [{source_service}]")
                lines.append(f"  Project: {sentry_project}")
                lines.append(f"  Duration: {duration:.2f}ms")
                lines.append(f"  Timestamp: {timestamp}")
                lines.append("")
        
        return [types.TextContent(type="text", text="\n".join(lines))]

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        # Cleanup Redis connection
        if redis_coordinator:
            asyncio.run(shutdown_redis())
        
        # Cleanup Datadog log handler (Phase 3.5)
        shutdown_datadog_logs()

