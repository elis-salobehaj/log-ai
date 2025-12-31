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

from config import load_config, find_log_files, AppConfig
from config_loader import get_config
from redis_coordinator import (
    RedisCoordinator,
    RedisSemaphore,
    RedisCache,
    RedisMetrics
)

# =============================================================================
# CONFIGURATION - Load from environment variables
# =============================================================================

# Load configuration
config = get_config()

# Cache settings
CACHE_MAX_SIZE_MB = config.CACHE_MAX_SIZE_MB
CACHE_MAX_ENTRIES = config.CACHE_MAX_ENTRIES
CACHE_TTL_MINUTES = config.CACHE_TTL_MINUTES

# Concurrency limits
MAX_PARALLEL_SEARCHES_PER_CALL = config.MAX_PARALLEL_SEARCHES_PER_CALL
MAX_GLOBAL_SEARCHES = config.MAX_GLOBAL_SEARCHES

# Search limits
AUTO_CANCEL_TIMEOUT_SECONDS = config.AUTO_CANCEL_TIMEOUT_SECONDS
PREVIEW_MATCHES_LIMIT = config.PREVIEW_MATCHES_LIMIT

# File output
FILE_OUTPUT_DIR = Path(config.FILE_OUTPUT_DIR)
CLEANUP_INTERVAL_HOURS = config.CLEANUP_INTERVAL_HOURS
FILE_RETENTION_HOURS = config.FILE_RETENTION_HOURS

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
log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
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
logger.info(f"Log level set to: {config.LOG_LEVEL}")

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


async def init_redis():
    """Initialize Redis connection for distributed coordination"""
    global redis_coordinator, redis_connected
    
    if not config.REDIS_ENABLED:
        sys.stderr.write("[REDIS] Redis disabled via config\n")
        return
    
    sys.stderr.write(f"[REDIS] Connecting to {config.REDIS_HOST}:{config.REDIS_PORT}...\n")
    redis_coordinator = RedisCoordinator(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        password=config.REDIS_PASSWORD,
        db=config.REDIS_DB
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


def get_search_semaphore():
    """
    Get search semaphore - uses Redis if available, falls back to local asyncio.Semaphore.
    Returns a context manager for 'async with' usage.
    """
    if redis_connected and redis_coordinator and redis_coordinator.redis:
        return RedisSemaphore(
            redis_coordinator.redis,
            key_name="global_searches",
            max_count=config.MAX_GLOBAL_SEARCHES,
            retry_delay=config.REDIS_RETRY_DELAY,
            max_retries=config.REDIS_MAX_RETRIES
        )
    else:
        # Fallback to local semaphore
        return asyncio.Semaphore(config.MAX_GLOBAL_SEARCHES)


def get_search_cache():
    """
    Get search cache - uses Redis if available, falls back to local SearchCache.
    Returns a cache object with get() and put() methods.
    """
    if redis_connected and redis_coordinator and redis_coordinator.redis:
        return RedisCache(
            redis_coordinator.redis,
            ttl_seconds=config.CACHE_TTL_MINUTES * 60,
            max_size_mb=config.CACHE_MAX_SIZE_MB
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
        time_str = json.dumps(time_range, sort_keys=True)
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
        
        # Find log files
        if "specific_date" in time_range:
            files = find_log_files(
                target_service, 
                specific_date=time_range["specific_date"],
                start_hour=time_range.get("start_hour"),
                end_hour=time_range.get("end_hour")
            )
        elif "minutes_back" in time_range:
            files = find_log_files(target_service, minutes_back=time_range["minutes_back"])
        elif "hours_back" in time_range:
            files = find_log_files(target_service, hours_back=time_range["hours_back"])
        else:
            # Default: search today
            files = find_log_files(target_service, specific_date=datetime.now().strftime("%Y-%m-%d"))
        
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


# =============================================================================
# MAIN SERVER
# =============================================================================

async def main():
    # Initialize Redis (if enabled)
    await init_redis()
    
    # Ensure output directory exists
    ensure_output_dir()
    
    # Start cleanup task
    cleanup_task = asyncio.create_task(cleanup_old_files_task())
    
    config = load_config()
    server = Server("log-ai")
    
    sys.stderr.write(f"[SERVER] Starting with {len(config.services)} services\n")
    sys.stderr.write(f"[SERVER] Ripgrep available: {HAS_RIPGREP}\n")
    sys.stderr.write(f"[SERVER] Output directory: {FILE_OUTPUT_DIR}\n")
    sys.stderr.write(f"[SERVER] Cache: {CACHE_MAX_ENTRIES} entries, {CACHE_MAX_SIZE_MB} MB, {CACHE_TTL_MINUTES} min TTL\n")
    sys.stderr.write(f"[SERVER] Concurrency: {MAX_PARALLEL_SEARCHES_PER_CALL} per call, {MAX_GLOBAL_SEARCHES} global\n")
    sys.stderr.write(f"[SERVER] Redis: {'Enabled' if redis_connected else 'Disabled (using local state)'}\n")

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
                description="Search for log entries across one or more services. Returns structured results with metadata.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service_name": {
                            "oneOf": [
                                {"type": "string"},
                                {"type": "array", "items": {"type": "string"}}
                            ],
                            "description": "Service name(s) to search. Can be a single string or array for multi-service search."
                        },
                        "query": {
                            "type": "string",
                            "description": "Keyword or pattern to search for"
                        },
                        "hours_back": {
                            "type": "integer",
                            "description": "Number of hours to search back from now"
                        },
                        "minutes_back": {
                            "type": "integer",
                            "description": "Number of minutes to search back from now (for surgical precision in large log files)"
                        },
                        "date": {
                            "type": "string",
                            "description": "Specific date to search. Supports: day names (Sunday, Monday), specific dates (Dec 14, 2025-12-14), or relative (today, yesterday)"
                        },
                        "time_range": {
                            "type": "string",
                            "description": "Time range within the date. Examples: '2 to 4pm', '14:00 to 16:00', '2pm-4pm'. User timezone is converted to UTC automatically."
                        },
                        "timezone": {
                            "type": "string",
                            "description": "User's timezone (e.g., 'America/Denver', 'EST'). Defaults to UTC if not specified."
                        },
                        "format": {
                            "type": "string",
                            "enum": ["text", "json"],
                            "description": "Output format (default: text)",
                            "default": "text"
                        }
                    },
                    "required": ["service_name", "query"]
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
        else:
            raise ValueError(f"Unknown tool: {name}")

    async def search_logs_handler(args: dict, config: AppConfig) -> list[types.TextContent]:
        """Handle search_logs tool with streaming and all features"""
        start_time = time.time()
        
        # Parse arguments
        service_name_arg = args.get("service_name")
        services = service_name_arg if isinstance(service_name_arg, list) else [service_name_arg]
        query = args.get("query")
        format_type = args.get("format", "text")
        user_tz = args.get("timezone", "UTC")
        
        # Handle date and time range parsing
        time_range = {}
        date_str = args.get("date")
        time_range_str = args.get("time_range")
        
        if date_str:
            # Parse natural language date
            date_range = parse_date_string(date_str)
            if date_range:
                start_date, end_date = date_range
                logger.info(f"Parsed date '{date_str}' as {start_date.date()}")
                time_range["specific_date"] = start_date.strftime("%Y-%m-%d")
                
                # Parse time range if provided (e.g., "2 to 4pm")
                if time_range_str:
                    hours = parse_time_range(time_range_str)
                    if hours:
                        start_hour, end_hour = hours
                        logger.info(f"Parsed time range '{time_range_str}' as {start_hour}:00 to {end_hour}:00 in {user_tz}")
                        
                        # Convert user timezone to UTC (logs are in UTC)
                        try:
                            import zoneinfo
                            tz = zoneinfo.ZoneInfo(user_tz)
                            
                            # Create datetime with user's timezone
                            user_start = start_date.replace(hour=start_hour, tzinfo=tz)
                            user_end = start_date.replace(hour=end_hour, tzinfo=tz)
                            
                            # Convert to UTC
                            utc_start = user_start.astimezone(zoneinfo.ZoneInfo("UTC"))
                            utc_end = user_end.astimezone(zoneinfo.ZoneInfo("UTC"))
                            
                            # If timezone conversion crosses date boundary, adjust
                            if utc_start.date() != start_date.date():
                                time_range["specific_date"] = utc_start.strftime("%Y-%m-%d")
                                logger.info(f"Timezone conversion: {user_tz} {start_hour}:00 → UTC {utc_start.hour}:00 on {utc_start.date()}")
                            
                            time_range["start_hour"] = utc_start.hour
                            time_range["end_hour"] = utc_end.hour
                            
                        except Exception as e:
                            logger.warning(f"Could not convert timezone {user_tz}: {e}, assuming UTC")
                            time_range["start_hour"] = start_hour
                            time_range["end_hour"] = end_hour
                    else:
                        logger.warning(f"Could not parse time range: {time_range_str}")
            else:
                logger.warning(f"Could not parse date: {date_str}, using today")
                time_range["specific_date"] = datetime.now().strftime("%Y-%m-%d")
        elif args.get("minutes_back"):
            time_range["minutes_back"] = int(args["minutes_back"])
        elif args.get("hours_back"):
            time_range["hours_back"] = int(args["hours_back"])
        else:
            # Default to today
            time_range["specific_date"] = datetime.now().strftime("%Y-%m-%d")
        
        logger.info(f"search_logs: services={services}, query='{query}', time_range={time_range}, format={format_type}")
        sys.stderr.write(f"[REQUEST] search_logs: services={services}, query='{query}', time_range={time_range}, format={format_type}\n")
        
        # Get cache instance (Redis or local)
        cache = get_search_cache()
        
        # Check cache
        cached = cache.get(services, query, time_range)
        if cached:
            matches, metadata = cached
            metadata["cached"] = True
            metadata["duration_seconds"] = time.time() - start_time
            
            if format_type == "json":
                return [types.TextContent(type="text", text=format_matches_json(matches, metadata))]
            else:
                return [types.TextContent(type="text", text=format_matches_text(matches, metadata))]
        
        # Get semaphore instance (Redis or local)
        search_semaphore = get_search_semaphore()
        
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
                
                sys.stderr.write(f"[COMPLETE] {len(all_matches)} matches in {duration:.2f}s\n")
                
                # Format response
                if format_type == "json":
                    return [types.TextContent(type="text", text=format_matches_json(preview_matches, metadata))]
                else:
                    return [types.TextContent(type="text", text=format_matches_text(preview_matches, metadata))]
                
            except Exception as e:
                sys.stderr.write(f"[ERROR] Unexpected error: {e}\n")
                import traceback
                traceback.print_exc()
                return [types.TextContent(type="text", text=f"Error: {str(e)}")]

    async def read_search_file_handler(args: dict) -> list[types.TextContent]:
        """Handle read_search_file tool"""
        file_path_str = args.get("file_path")
        format_type = args.get("format", "text")
        
        # Security: validate path
        file_path = Path(file_path_str)
        if not str(file_path).startswith(str(FILE_OUTPUT_DIR)):
            return [types.TextContent(type="text", text=f"Error: Invalid file path. Must be in {FILE_OUTPUT_DIR}")]
        
        if not file_path.name.startswith("logai-"):
            return [types.TextContent(type="text", text="Error: Invalid file name. Must start with 'logai-'")]
        
        if not file_path.exists():
            return [types.TextContent(type="text", text=f"Error: File not found: {file_path}")]
        
        try:
            # Read JSON file
            with open(file_path, 'r', encoding='utf-8') as f:
                matches = json.load(f)
            
            file_size_mb = file_path.stat().st_size / 1024 / 1024
            
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
                return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
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

