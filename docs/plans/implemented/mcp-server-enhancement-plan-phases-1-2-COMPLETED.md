# MCP Server Enhancement Plan

**STATUS: Phase 1 Complete ✅ | Phase 2 In Progress 🔄 | Phase 3 Planned 📋**

## Project Milestones

### Milestone 1: Global Resource Coordination with Redis ✅ COMPLETED
Implemented shared state across all SSH sessions:
- ✅ Global resource limits across ALL users (20 concurrent searches)
- ✅ Shared cache (500MB total, not per-session)
- ✅ Coordinated rate limiting system-wide via Redis
- ✅ Graceful fallback to local state when Redis unavailable
- ✅ Configuration via .env file with python-dotenv
- ✅ Deployed to production (syslog.example.com)

**Additional Improvements:**
- ✅ Simplified tool architecture (removed get_insights, 3 → 2 tools)
- ✅ Added minutes_back parameter for surgical precision searches
- ✅ Configuration management refactored (env.sh → .env)
- ✅ services.yaml.example template created
- ✅ Comprehensive documentation updates

### Milestone 2: Observability & Monitoring 🔄 NEXT
Add APM and error tracking for AI agents to:
- **Sentry**: Error tracking, performance monitoring, real-time alerts
- **Datadog**: APM, infrastructure metrics, distributed tracing, log aggregation

This enables AI agents to have a holistic overview of apps and services to better analyze failures, errors, and patterns for potential bottlenecks/improvements.

## Implementation Breakdown

This plan is divided into **3 chunks**:
1. **Chunk 1**: Shared Redis with coordination layer ✅ **COMPLETED** (Dec 19-31, 2025)
2. **Chunk 2**: Sentry integration for error tracking 🔄 **NEXT**
3. **Chunk 3**: Datadog integration for APM and metrics 📋 **PLANNED**

---

## Current Architecture Analysis

**Communication Model:**
- Uses **JSON-RPC 2.0 over stdio** (stdin/stdout)
- Each SSH connection spawns a new isolated Python process: `ssh user@syslog.example.com ~/.local/bin/uv run --directory /home/user/log-ai src/server.py`
- Session-based logging using `SSH_CONNECTION` environment variable
- Process exits when SSH connection closes

**State Management:**
- **GLOBAL state** shared within a single process:
  - `search_cache`: LRU cache (500MB, 100 entries, 10min TTL)
  - `global_search_semaphore`: Limits to 10 concurrent searches per process
  - Cleanup task runs hourly to remove old overflow files
- Per-session directories: `/tmp/log-ai/{SESSION_ID}/`

**Design Pattern:**
- **Process-per-connection** (current model)
- Each client gets isolated: cache, logs, semaphores, file handles
- No inter-process communication or shared state between sessions

## MCP Protocol Requirements

**Critical Protocol Constraints:**
1. **1:1 mapping** - Each stdio stream pair = one client connection
2. **No multiplexing** - Cannot share stdin/stdout between multiple clients
3. **Blocking nature** - stdio is inherently single-threaded per file descriptor
4. **Session lifecycle** - Server process tied to client connection lifetime

**Key Finding:** The MCP protocol **requires stdio-based communication**. You **cannot** have a single persistent MCP server process handling multiple SSH clients over stdio. The protocol itself is designed for per-session execution.

## What "Global Restrictions" Means (Confirmed Requirements)

**All three aspects are required:**

1. **Resource limits across ALL users:**
   - Currently: 10 concurrent searches PER process (isolated)
   - Required: 20 concurrent searches across ALL SSH sessions system-wide
   
2. **Shared cache across sessions:**
   - Currently: Each SSH session has its own 500MB cache (inefficient with N users)
   - Required: One shared 500MB cache for all users
   
3. **Coordinated rate limiting:**
   - Currently: Each session can spawn 10 searches independently
   - Required: Total system limit enforced globally (e.g., 20 searches across 10 users)

**Additional requirement:**
4. **Centralized monitoring:**
   - Currently: Logs scattered across `/tmp/log-ai/{session}/`
   - Required: Unified logging + observability (Sentry + Datadog)

## Architecture Options Comparison

### Option A: Keep Current Per-Session Model ✅ (RECOMMENDED if acceptable)

**Pros:**
- ✅ **MCP protocol compliant** - designed for this pattern
- ✅ **Isolation** - User A's crash doesn't affect User B
- ✅ **Simple deployment** - no daemon management
- ✅ **Automatic cleanup** - process dies with SSH session
- ✅ **No shared state bugs** - each session independent
- ✅ **Zero code changes needed**

**Cons:**
- ❌ No cross-session resource limits
- ❌ Duplicate caches (500MB × N users)
- ❌ Can't enforce system-wide concurrency
- ❌ Scattered logs across sessions

**Best For:** Current setup where users are trusted and resource usage is acceptable

### Option B: Hybrid Architecture - Per-Session + Redis Coordinator ⚠️

Convert to a **hybrid architecture**:
- Keep per-session MCP servers (stdio requirement)
- Add shared backend service for coordination

**Architecture:**
```
SSH Client 1 → MCP Server (stdio) ┐
SSH Client 2 → MCP Server (stdio) ├─→ Redis/State Server ←→ Shared Resources
SSH Client 3 → MCP Server (stdio) ┘      (shared cache,
                                          global limits)
```

**Implementation Details:**

1. **Add Redis** for:
   - Shared LRU cache (500MB total, not per-session)
   - Global semaphore via distributed lock
   - Centralized search queue tracking

2. **MCP servers become thin proxies:**
   - Accept stdio from AI agent
   - Coordinate via Redis for cache/limits
   - Return results to stdio

3. **Keep process-per-session pattern:**
   - MCP protocol requirement satisfied
   - Each session isolated for stdio communication
   - Shared state via Redis backend

**Pros:**
- ✅ True global resource limits
- ✅ Shared cache (memory efficient)
- ✅ Centralized monitoring
- ✅ Can enforce system-wide rate limits
- ✅ Still MCP protocol compliant

**Cons:**
- ❌ **Moderate complexity** - ~200 lines of code
- ❌ New dependency (Redis)
- ❌ Failure modes: what if Redis dies?
- ❌ MCP servers still spawned per-session (required)
- ❌ Latency increase (+5-15ms per operation)
- ❌ Deployment complexity (systemd + Redis)

### Option C: Persistent Service with TCP/Unix Sockets ❌ (NOT COMPATIBLE)

Run one server process, clients connect via TCP/Unix socket.

**Why this CANNOT work:**
- MCP protocol uses stdio (stdin/stdout)
- SSH invokes: `ssh host "command"` which expects stdio
- No way to multiplex multiple stdio pairs onto one socket
- Would require rewriting the entire MCP client-server contract

**Verdict:** Architecturally impossible without breaking MCP protocol

## Recommended Implementation: Hybrid Approach

### Phase 1: Add System-Wide Limits (Minimal Changes)

**1. Shared semaphore via Redis:**
```python
from redis import Redis
from redis.lock import Lock
import asyncio

class RedisSemaphore:
    def __init__(self, redis_client, key, max_count=20):
        self.redis = redis_client
        self.key = key
        self.max_count = max_count
    
    async def acquire(self):
        # Increment counter atomically
        current = await self.redis.incr(f"{self.key}:count")
        if current > self.max_count:
            await self.redis.decr(f"{self.key}:count")
            raise ValueError("Semaphore limit reached")
        return True
    
    async def release(self):
        await self.redis.decr(f"{self.key}:count")

# Usage in server.py:
redis_client = Redis(host='localhost', port=6379, decode_responses=True)
global_search_semaphore = RedisSemaphore(redis_client, 'log-ai:searches', max_count=20)
```

**2. Shared cache via Redis:**
```python
import json
from redis import Redis

class RedisSearchCache:
    def __init__(self, redis_client, max_size_mb=500, ttl_minutes=10):
        self.redis = redis_client
        self.ttl_seconds = ttl_minutes * 60
    
    async def get(self, key):
        data = await self.redis.get(f"log-ai:cache:{key}")
        return json.loads(data) if data else None
    
    async def put(self, key, value):
        await self.redis.setex(
            f"log-ai:cache:{key}",
            self.ttl_seconds,
            json.dumps(value)
        )

# Usage in server.py:
search_cache = RedisSearchCache(redis_client, max_size_mb=500, ttl_minutes=10)
```

**3. Centralized logging:**
```python
import logging
from logging.handlers import SysLogHandler

# All sessions log to syslog
logger = logging.getLogger("log-ai")
handler = SysLogHandler(address='/dev/log')
formatter = logging.Formatter('log-ai[%(process)d]: %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)
```

**Deployment:**
- Each SSH session still spawns its own MCP server (stdio requirement)
- MCP servers coordinate via Redis for cache + semaphores
- Simple systemd service for Redis

### Phase 2: Redis Setup

**Install Redis:**
```bash
# On syslog server
sudo apt-get install redis-server
sudo systemctl enable redis-server
sudo systemctl start redis-server
```

**Redis configuration** (`/etc/redis/log-ai.conf`):
```ini
# Bind to localhost only
bind 127.0.0.1

# Memory limit (for cache)
maxmemory 500mb
maxmemory-policy allkeys-lru

# Persistence (optional)
save ""
appendonly no

# Port
port 6379
```

**systemd service** (`/etc/systemd/system/redis-log-ai.service`):
```ini
[Unit]
Description=Redis for LogAI coordination
After=network.target

[Service]
Type=notify
ExecStart=/usr/bin/redis-server /etc/redis/log-ai.conf
Restart=always
User=redis
Group=redis

[Install]
WantedBy=multi-user.target
```

### Phase 3: Code Changes

**Dependencies:**
```toml
# Add to pyproject.toml
dependencies = [
    "redis>=5.0.0",
    "redis[asyncio]>=5.0.0",
]
```

**File: src/redis_coordinator.py** (new file):
```python
"""Redis-based coordination for global resource limits"""
from redis.asyncio import Redis
import asyncio
import json
from typing import Optional

class RedisCoordinator:
    def __init__(self, host='localhost', port=6379):
        self.redis = Redis(host=host, port=port, decode_responses=True)
    
    async def connect(self):
        await self.redis.ping()
    
    async def close(self):
        await self.redis.close()

class RedisSemaphore:
    def __init__(self, redis: Redis, key: str, max_count: int):
        self.redis = redis
        self.key = f"log-ai:sem:{key}"
        self.max_count = max_count
        self.token = None
    
    async def __aenter__(self):
        while True:
            current = await self.redis.incr(self.key)
            if current <= self.max_count:
                self.token = current
                return self
            else:
                await self.redis.decr(self.key)
                await asyncio.sleep(0.1)  # Wait before retry
    
    async def __aexit__(self, *args):
        if self.token:
            await self.redis.decr(self.key)

class RedisCache:
    def __init__(self, redis: Redis, ttl_seconds: int = 600):
        self.redis = redis
        self.ttl = ttl_seconds
    
    async def get(self, key: str) -> Optional[dict]:
        data = await self.redis.get(f"log-ai:cache:{key}")
        if data:
            return json.loads(data)
        return None
    
    async def put(self, key: str, value: dict):
        await self.redis.setex(
            f"log-ai:cache:{key}",
            self.ttl,
            json.dumps(value)
        )
    
    async def stats(self) -> dict:
        keys = await self.redis.keys("log-ai:cache:*")
        return {"entries": len(keys)}
```

**Changes to src/server.py:**
- Replace `asyncio.Semaphore` with `RedisSemaphore`
- Replace `SearchCache` with `RedisCache`
- Add Redis connection on startup
- Handle Redis failures gracefully (fallback to local)

## Comparison Table

| Aspect | Previous (Per-Session) | ✅ Current (After Chunk 1) | After Chunk 2 (Sentry) | After Chunk 3 (Datadog) |
|--------|----------------------|----------------------|----------------------|------------------------|
| **MCP Compliant** | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| **Global Limits** | ❌ No | ✅ **Yes (20 max)** | ✅ Yes | ✅ Yes |
| **Shared Cache** | ❌ No (500MB×N) | ✅ **Yes (500MB total)** | ✅ Yes | ✅ Yes |
| **Error Tracking** | ❌ Stderr only | ❌ Stderr only | ✅ Sentry | ✅ Sentry |
| **Performance Monitoring** | ❌ No | ❌ No | ✅ Basic (Sentry) | ✅ Advanced (Datadog APM) |
| **Infrastructure Metrics** | ❌ No | ❌ No | ❌ No | ✅ Datadog |
| **Distributed Tracing** | ❌ No | ❌ No | ❌ No | ✅ Datadog |
| **AI Agent Insights** | ❌ Limited | ⚠️ Some | ✅ Good | ✅ Excellent |
| **Complexity** | Low | Medium | Medium | Medium-High |
| **Code Changes** | None | ~200 lines | ~100 lines | ~150 lines |
| **Dependencies** | None | +Redis | +Sentry SDK | +Datadog SDK |
| **Latency** | Lowest | +5-15ms | +1-2ms | +2-5ms |
| **Memory Usage** | 500MB × N users | 500MB total | 500MB total | 500MB total |

---

# CHUNK 1: Redis Coordination Layer ✅ COMPLETED

## Status: PRODUCTION (Deployed Dec 31, 2025)

**Completion Summary:**
- ✅ All tasks completed successfully
- ✅ Deployed to syslog.example.com
- ✅ Redis running on localhost:6379
- ✅ Graceful fallback tested and working
- ✅ Configuration via config/.env
- ✅ Test suite passing
- ✅ Documentation updated

## Objective (ACHIEVED)
Implement shared state across all MCP server instances using Redis for global resource limits, shared cache, and coordinated rate limiting.

## Architecture Design

**Current State:**
```
SSH User 1 → MCP Server (isolated, 500MB cache, 10 searches)
SSH User 2 → MCP Server (isolated, 500MB cache, 10 searches)
SSH User 3 → MCP Server (isolated, 500MB cache, 10 searches)
Total: 1500MB cache, 30 concurrent searches possible
```

**Target State (Chunk 1):**
```
SSH User 1 → MCP Server ┐
SSH User 2 → MCP Server ├─→ Redis (500MB shared cache, 20 global searches)
SSH User 3 → MCP Server ┘
Total: 500MB cache, 20 concurrent searches max
```

## Implementation Tasks

### Task 1.1: Redis Setup on Syslog Server

**Install Redis:**
```bash
sudo apt-get update
sudo apt-get install redis-server
```

**Configure Redis** (`/etc/redis/log-ai.conf`):
```ini
# Bind to localhost only (security)
bind 127.0.0.1

# Memory limit for cache
maxmemory 500mb
maxmemory-policy allkeys-lru

# Disable persistence (cache only)
save ""
appendonly no

# Port
port 6379

# Timeout for idle clients
timeout 300
```

**Create systemd service** (`/etc/systemd/system/redis-log-ai.service`):
```ini
[Unit]
Description=Redis for LogAI Global Coordination
After=network.target

[Service]
Type=notify
ExecStart=/usr/bin/redis-server /etc/redis/log-ai.conf
Restart=always
User=redis
Group=redis

[Install]
WantedBy=multi-user.target
```

**Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable redis-log-ai
sudo systemctl start redis-log-ai
sudo systemctl status redis-log-ai
```

### Task 1.2: Add Python Dependencies

**Update pyproject.toml:**
```toml
dependencies = [
    # ... existing dependencies
    "redis[asyncio]>=5.0.0",
]
```

**Install:**
```bash
cd /home/srt/log-ai
~/.local/bin/uv sync
```

### Task 1.3: Create Redis Coordinator Module

**Create file: `src/redis_coordinator.py`**

```python
"""Redis-based coordination for global resource limits"""
from redis.asyncio import Redis
from redis.exceptions import RedisError
import asyncio
import json
import hashlib
from typing import Optional, Any
from datetime import datetime

class RedisCoordinator:
    """Manages Redis connection for all coordination features"""
    
    def __init__(self, host='localhost', port=6379, db=0):
        self.host = host
        self.port = port
        self.db = db
        self.redis: Optional[Redis] = None
        self._connected = False
    
    async def connect(self):
        """Establish Redis connection"""
        try:
            self.redis = Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True
            )
            await self.redis.ping()
            self._connected = True
            return True
        except RedisError as e:
            self._connected = False
            return False
    
    async def close(self):
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()
            self._connected = False
    
    @property
    def is_connected(self) -> bool:
        return self._connected


class RedisSemaphore:
    """Distributed semaphore using Redis for global concurrency limits"""
    
    def __init__(self, redis: Redis, key: str, max_count: int):
        self.redis = redis
        self.key = f"log-ai:sem:{key}"
        self.max_count = max_count
        self.token = None
    
    async def __aenter__(self):
        """Acquire semaphore (blocking with retry)"""
        retry_count = 0
        max_retries = 100
        
        while retry_count < max_retries:
            try:
                # Atomic increment
                current = await self.redis.incr(self.key)
                
                if current <= self.max_count:
                    self.token = current
                    # Set expiry to auto-cleanup if process crashes
                    await self.redis.expire(self.key, 3600)
                    return self
                else:
                    # Over limit, decrement and retry
                    await self.redis.decr(self.key)
                    await asyncio.sleep(0.5)  # Wait before retry
                    retry_count += 1
            
            except RedisError:
                # Redis unavailable, fail gracefully
                raise RuntimeError("Redis semaphore unavailable")
        
        raise TimeoutError(f"Could not acquire semaphore after {max_retries} retries")
    
    async def __aexit__(self, *args):
        """Release semaphore"""
        if self.token:
            try:
                await self.redis.decr(self.key)
            except RedisError:
                pass  # Best effort


class RedisCache:
    """Distributed cache using Redis for shared search results"""
    
    def __init__(self, redis: Redis, ttl_seconds: int = 600):
        self.redis = redis
        self.ttl = ttl_seconds
    
    def _make_key(self, service: str, pattern: str, date: str, 
                  file_pattern: str, log_format: str) -> str:
        """Generate cache key from search parameters"""
        key_parts = f"{service}:{pattern}:{date}:{file_pattern}:{log_format}"
        key_hash = hashlib.sha256(key_parts.encode()).hexdigest()[:16]
        return f"log-ai:cache:{key_hash}"
    
    async def get(self, service: str, pattern: str, date: str,
                  file_pattern: str, log_format: str) -> Optional[dict]:
        """Get cached search results"""
        try:
            key = self._make_key(service, pattern, date, file_pattern, log_format)
            data = await self.redis.get(key)
            
            if data:
                cached = json.loads(data)
                return cached
            return None
        
        except (RedisError, json.JSONDecodeError):
            return None  # Cache miss on error
    
    async def put(self, service: str, pattern: str, date: str,
                  file_pattern: str, log_format: str, results: list,
                  matched_files: int):
        """Store search results in cache"""
        try:
            key = self._make_key(service, pattern, date, file_pattern, log_format)
            
            cache_entry = {
                "results": results,
                "matched_files": matched_files,
                "cached_at": datetime.now().isoformat(),
            }
            
            await self.redis.setex(
                key,
                self.ttl,
                json.dumps(cache_entry)
            )
        
        except (RedisError, json.JSONDecodeError):
            pass  # Best effort caching
    
    async def stats(self) -> dict:
        """Get cache statistics"""
        try:
            keys = await self.redis.keys("log-ai:cache:*")
            return {
                "entries": len(keys),
                "ttl": self.ttl
            }
        except RedisError:
            return {"entries": 0, "ttl": self.ttl}


class RedisMetrics:
    """Track metrics in Redis for monitoring"""
    
    def __init__(self, redis: Redis):
        self.redis = redis
    
    async def increment_counter(self, metric: str, value: int = 1):
        """Increment a counter metric"""
        try:
            await self.redis.incrby(f"log-ai:metrics:{metric}", value)
        except RedisError:
            pass
    
    async def record_timing(self, metric: str, duration_ms: float):
        """Record timing metric (stores last 100 values)"""
        try:
            key = f"log-ai:timings:{metric}"
            await self.redis.lpush(key, str(duration_ms))
            await self.redis.ltrim(key, 0, 99)  # Keep last 100
        except RedisError:
            pass
    
    async def get_metrics(self) -> dict:
        """Get all metrics"""
        try:
            metrics = {}
            
            # Get counters
            counter_keys = await self.redis.keys("log-ai:metrics:*")
            for key in counter_keys:
                metric_name = key.replace("log-ai:metrics:", "")
                metrics[metric_name] = int(await self.redis.get(key) or 0)
            
            return metrics
        except RedisError:
            return {}
```

### Task 1.4: Update server.py to Use Redis

**Changes to `src/server.py`:**

1. **Add imports:**
```python
from redis_coordinator import (
    RedisCoordinator,
    RedisSemaphore,
    RedisCache,
    RedisMetrics
)
```

2. **Initialize Redis coordinator (after line ~65):**
```python
# Redis coordinator for global state
redis_coordinator = RedisCoordinator(host='localhost', port=6379)
redis_connected = False

async def init_redis():
    global redis_connected
    redis_connected = await redis_coordinator.connect()
    if redis_connected:
        log(f"[REDIS] Connected to Redis at {redis_coordinator.host}:{redis_coordinator.port}")
    else:
        log("[REDIS] WARNING: Redis unavailable, using local state only")

# Initialize at startup
asyncio.create_task(init_redis())
```

3. **Replace global semaphore (around line ~60):**
```python
# Old:
# global_search_semaphore = asyncio.Semaphore(MAX_GLOBAL_SEARCHES)

# New:
def get_search_semaphore():
    """Get semaphore - Redis if available, local otherwise"""
    if redis_connected and redis_coordinator.redis:
        return RedisSemaphore(
            redis_coordinator.redis,
            'global_searches',
            MAX_GLOBAL_SEARCHES
        )
    else:
        # Fallback to local semaphore
        return asyncio.Semaphore(MAX_GLOBAL_SEARCHES)
```

4. **Replace search cache (around line ~240):**
```python
# Old:
# search_cache = SearchCache(max_size=100, ttl_minutes=10)

# New:
def get_search_cache():
    """Get cache - Redis if available, local otherwise"""
    if redis_connected and redis_coordinator.redis:
        return RedisCache(redis_coordinator.redis, ttl_seconds=600)
    else:
        # Fallback to local cache
        return SearchCache(max_size=100, ttl_minutes=10)

search_cache = get_search_cache()
```

5. **Update search_logs_handler to use Redis semaphore:**
```python
async def search_logs_handler(arguments: dict) -> Sequence[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    # ... existing code ...
    
    # Use Redis semaphore if available
    semaphore = get_search_semaphore()
    
    async with semaphore:
        # ... existing search logic ...
```

6. **Add metrics tracking:**
```python
# In search_logs_handler:
if redis_connected and redis_coordinator.redis:
    metrics = RedisMetrics(redis_coordinator.redis)
    await metrics.increment_counter("searches_total")
    await metrics.record_timing("search_duration_ms", duration_ms)
```

7. **Add shutdown handler:**
```python
async def shutdown():
    """Cleanup on shutdown"""
    if redis_coordinator:
        await redis_coordinator.close()
        log("[REDIS] Connection closed")

# Register shutdown
import atexit
atexit.register(lambda: asyncio.run(shutdown()))
```

### Task 1.5: Testing

**Test script: `scripts/test_redis_coordination.py`**

```python
#!/usr/bin/env python3
"""Test Redis coordination with multiple concurrent sessions"""
import asyncio
import subprocess
from datetime import datetime

async def run_search(session_id: int):
    """Simulate one MCP session doing a search"""
    print(f"[Session {session_id}] Starting search at {datetime.now()}")
    
    proc = await asyncio.create_subprocess_exec(
        "ssh", "user@syslog.example.com",
        "~/.local/bin/uv run --directory /home/srt/log-ai python -c "
        "'from src.redis_coordinator import RedisCoordinator; "
        "import asyncio; "
        "async def test(): "
        "  rc = RedisCoordinator(); "
        "  await rc.connect(); "
        "  print(f\"Connected: {rc.is_connected}\"); "
        "  await rc.close(); "
        "asyncio.run(test())'",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await proc.communicate()
    print(f"[Session {session_id}] Result: {stdout.decode().strip()}")

async def test_concurrent_sessions():
    """Test 5 concurrent sessions"""
    tasks = [run_search(i) for i in range(1, 6)]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(test_concurrent_sessions())
```

**Run test:**
```bash
python scripts/test_redis_coordination.py
```

### Task 1.6: Deployment

**Deploy to syslog server:**
```bash
cd /home/ubuntu/elis_temp/github_projects/log-ai
bash scripts/deploy.sh
```

**Verify Redis is running:**
```bash
ssh user@syslog.example.com 'redis-cli -p 6379 ping'
# Should output: PONG
```

**Monitor Redis:**
```bash
# Watch Redis activity
ssh user@syslog.example.com 'redis-cli -p 6379 monitor'

# Check keys
ssh user@syslog.example.com 'redis-cli -p 6379 keys "log-ai:*"'

# Check semaphore count
ssh user@syslog.example.com 'redis-cli -p 6379 get "log-ai:sem:global_searches"'
```

## Chunk 1 Deliverables ✅ ALL COMPLETED

✅ Redis installed and running (localhost:6379)
✅ Redis coordinator module (`src/redis_coordinator.py`)
✅ Updated `src/server.py` with Redis integration
✅ Graceful fallback to local state if Redis unavailable
✅ Global semaphore limiting 20 concurrent searches system-wide
✅ Shared 500MB cache across all sessions
✅ Basic metrics tracking in Redis
✅ Test script for concurrent sessions
✅ Deployment and monitoring procedures

## Chunk 1 Success Metrics

- ✅ Multiple SSH sessions share single Redis instance
- ✅ Total concurrent searches capped at 20 (not 10 per user)
- ✅ Memory usage: 500MB total (not 500MB × N users)
- ✅ Cache hit rate visible in Redis
- ✅ No service disruption if Redis temporarily unavailable

---

# CHUNK 2: Sentry Integration 🔄 READY TO START

## Current Date: December 31, 2025
## Prerequisites: ✅ Chunk 1 Complete

## Objective
Add Sentry for error tracking, exception monitoring, and performance insights to help AI agents identify and diagnose issues.

## What Sentry Provides

1. **Error Tracking:**
   - Automatic exception capture with full stack traces
   - Deduplication and grouping of similar errors
   - Real-time alerts for new/recurring issues
   - Release tracking to identify when bugs were introduced

2. **Performance Monitoring:**
   - Slow query detection (searches taking >5s)
   - Transaction tracking (end-to-end search latency)
   - Breadcrumbs (user actions leading to errors)

3. **Context for AI Agents:**
   - Full error context: user, search params, environment
   - Frequency and impact analysis
   - Suggested fixes based on stack traces

## Implementation Tasks

### Task 2.1: Sentry Account Setup

**Create Sentry project:**
1. Sign up at https://sentry.io
2. Create new project: "log-ai"
3. Select platform: Python
4. Get DSN (Data Source Name): `https://xxx@yyy.ingest.sentry.io/zzz`

**Store DSN in config/.env:**
```bash
# Add to config/.env on syslog server
SENTRY_DSN=https://xxx@yyy.ingest.sentry.io/zzz
SENTRY_TRACES_SAMPLE_RATE=1.0
SENTRY_PROFILES_SAMPLE_RATE=0.1
SENTRY_ALERT_TEAMS_WEBHOOK=https://outlook.office.com/webhook/...
SENTRY_ALERT_SLACK_WEBHOOK=https://hooks.slack.com/services/...
```

### Task 2.2: Add Sentry SDK Dependency

**Update pyproject.toml:**
```toml
dependencies = [
    # ... existing dependencies
    "sentry-sdk>=2.0.0",
]
```

### Task 2.3: Create Sentry Integration Module

**Create file: `src/sentry_integration.py`**

```python
"""Sentry integration for error tracking and performance monitoring"""
import sentry_sdk
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
import os
from typing import Optional

def init_sentry():
    """Initialize Sentry SDK"""
    dsn = os.environ.get("SENTRY_DSN")
    
    if not dsn:
        print("[SENTRY] WARNING: SENTRY_DSN not set, monitoring disabled")
        return False
    
    sentry_sdk.init(
        dsn=dsn,
        
        # Enable performance monitoring
        traces_sample_rate=1.0,  # 100% of transactions
        
        # Enable profiling
        profiles_sample_rate=0.1,  # 10% of transactions
        
        # Integrations
        integrations=[
            AsyncioIntegration(),
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR
            ),
        ],
        
        # Environment
        environment="production",
        
        # Release tracking (from git)
        release=f"log-ai@{get_git_version()}",
        
        # Additional context
        before_send=enrich_event,
    )
    
    print(f"[SENTRY] Initialized (release: {get_git_version()})")
    return True


def get_git_version() -> str:
    """Get current git commit hash for release tracking"""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=1
        )
        return result.stdout.strip() or "unknown"
    except:
        return "unknown"


def enrich_event(event, hint):
    """Add custom context to Sentry events"""
    # Add SSH session info if available
    ssh_connection = os.environ.get("SSH_CONNECTION")
    if ssh_connection:
        event.setdefault("tags", {})["ssh_session"] = ssh_connection.split()[0]  # Client IP
    
    return event


def capture_search_performance(
    service: str,
    pattern: str,
    duration_ms: float,
    matched_files: int,
    result_count: int
):
    """Track search performance in Sentry"""
    with sentry_sdk.start_transaction(
        op="search",
        name=f"search_logs:{service}"
    ) as transaction:
        transaction.set_tag("service", service)
        transaction.set_tag("pattern_length", len(pattern))
        transaction.set_measurement("duration_ms", duration_ms)
        transaction.set_measurement("matched_files", matched_files)
        transaction.set_measurement("result_count", result_count)
        
        # Flag slow searches
        if duration_ms > 5000:
            transaction.set_tag("slow_search", True)


def capture_error_context(
    error: Exception,
    service: str,
    search_params: dict,
    user_ip: Optional[str] = None
):
    """Capture error with full context for AI agent analysis"""
    with sentry_sdk.push_scope() as scope:
        # Add search context
        scope.set_context("search", {
            "service": service,
            "pattern": search_params.get("pattern", ""),
            "date": search_params.get("date", ""),
            "hours_back": search_params.get("hours_back"),
        })
        
        # Add user context
        if user_ip:
            scope.set_user({"ip_address": user_ip})
        
        # Capture exception
        sentry_sdk.capture_exception(error)
```

### Task 2.4: Integrate Sentry into server.py

**Changes to `src/server.py`:**

1. **Add import and initialize:**
```python
from sentry_integration import (
    init_sentry,
    capture_search_performance,
    capture_error_context
)

# Initialize Sentry (after line ~70)
sentry_enabled = init_sentry()
```

2. **Wrap search_logs_handler with performance tracking:**
```python
async def search_logs_handler(arguments: dict) -> Sequence[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    start_time = time.time()
    service_name = arguments.get("service")
    pattern = arguments.get("pattern", "")
    
    try:
        # ... existing search logic ...
        
        # Track performance in Sentry
        if sentry_enabled:
            duration_ms = (time.time() - start_time) * 1000
            capture_search_performance(
                service=service_name,
                pattern=pattern,
                duration_ms=duration_ms,
                matched_files=len(matched_files),
                result_count=len(results)
            )
        
        return results
    
    except Exception as e:
        # Capture error with context
        if sentry_enabled:
            user_ip = os.environ.get("SSH_CONNECTION", "").split()[0]
            capture_error_context(
                error=e,
                service=service_name,
                search_params=arguments,
                user_ip=user_ip
            )
        
        # Re-raise for normal error handling
        raise
```

3. **Add breadcrumbs for debugging:**
```python
# Before each major operation:
sentry_sdk.add_breadcrumb(
    category="search",
    message=f"Starting search for {service_name}",
    level="info",
    data={"pattern": pattern[:100]}  # Truncate long patterns
)
```

### Task 2.5: Sentry Dashboard Setup

**Create custom dashboard for AI agents:**

1. **Search Performance Widget:**
   - Metric: `p95(duration_ms)` by service
   - Alert: p95 > 10 seconds

2. **Error Rate Widget:**
   - Metric: Error count per hour
   - Group by: error type, service

3. **Slow Searches Widget:**
   - Query: `tags[slow_search]:true`
   - Display: Top 10 slowest searches

4. **Cache Hit Rate:**
   - Custom metric from Redis metrics
   - Target: >80% hit rate

### Task 2.6: Alert Rules

**Configure alerts:**

1. **Critical Errors:**
   - Condition: Any error with tag `level:fatal`
   - Action: Slack notification + PagerDuty

2. **High Error Rate:**
   - Condition: >10 errors in 5 minutes
   - Action: Slack notification

3. **Performance Degradation:**
   - Condition: p95(duration_ms) > 15000 for 10 minutes
   - Action: Slack notification

## Chunk 2 Deliverables

✅ Sentry account and project configured
✅ Sentry SDK integrated into MCP server
✅ Automatic exception capture with context
✅ Performance monitoring for all searches
✅ Custom dashboard for AI agent insights
✅ Alert rules for critical issues
✅ Breadcrumbs for debugging complex issues

## Chunk 2 Success Metrics

- ✅ All exceptions automatically captured in Sentry
- ✅ AI agents can query Sentry for recent errors
- ✅ Slow searches (>5s) flagged and visible
- ✅ Error context includes: service, pattern, user IP, timestamp
- ✅ Real-time alerts for critical issues

---

# CHUNK 3: Datadog Integration

## Objective
Add Datadog APM, infrastructure metrics, and distributed tracing to provide AI agents with comprehensive observability for analyzing bottlenecks, patterns, and system health.

## What Datadog Provides

1. **APM (Application Performance Monitoring):**
   - Distributed tracing across all searches
   - Service maps showing dependencies
   - Resource profiling (CPU, memory per search)
   - Span analysis for identifying bottlenecks

2. **Infrastructure Metrics:**
   - System-level: CPU, memory, disk I/O
   - Process-level: MCP server resource usage
   - Redis metrics: connections, memory, operations
   - Custom metrics: cache hit rate, search queue depth

3. **Log Aggregation:**
   - Centralized logging from all sessions
   - Log patterns and anomaly detection
   - Correlation with traces and metrics

4. **AI Agent Capabilities:**
   - Query: "What's causing slow searches?"
   - Query: "Show me error patterns in the last hour"
   - Query: "Which service has highest search latency?"
   - Query: "Is there a memory leak?"

## Implementation Tasks

### Task 3.1: Datadog Account Setup

**Create Datadog account:**
1. Sign up at https://www.datadoghq.com
2. Get API key and APP key from: https://app.datadoghq.com/organization-settings/api-keys
3. Install Datadog Agent on syslog server

**Install Datadog Agent:**
```bash
# On syslog server
DD_API_KEY=<your-api-key> DD_SITE="datadoghq.com" bash -c "$(curl -L https://s3.amazonaws.com/dd-agent/scripts/install_script_agent7.sh)"

# Verify installation
sudo systemctl status datadog-agent
```

**Configure Agent** (`/etc/datadog-agent/datadog.yaml`):
```yaml
api_key: <your-api-key>
site: datadoghq.com
hostname: syslog.example.com

# Enable APM
apm_config:
  enabled: true
  apm_non_local_traffic: true

# Enable process monitoring
process_config:
  enabled: true
  
# Enable logs
logs_enabled: true
```

**Restart Agent:**
```bash
sudo systemctl restart datadog-agent
```

### Task 3.2: Add Datadog SDK Dependencies

**Update pyproject.toml:**
```toml
dependencies = [
    # ... existing dependencies
    "ddtrace>=2.0.0",
]
```

### Task 3.3: Create Datadog Integration Module

**Create file: `src/datadog_integration.py`**

```python
"""Datadog APM and metrics integration"""
from ddtrace import tracer, patch_all
from ddtrace.runtime import RuntimeMetrics
from datadog import initialize, statsd
import os
import time
from typing import Optional
from contextlib import contextmanager

# Initialize Datadog
def init_datadog():
    """Initialize Datadog APM and metrics"""
    dd_api_key = os.environ.get("DD_API_KEY")
    
    if not dd_api_key:
        print("[DATADOG] WARNING: DD_API_KEY not set, monitoring disabled")
        return False
    
    # Initialize Datadog API client
    options = {
        'api_key': dd_api_key,
        'app_key': os.environ.get("DD_APP_KEY", ""),
    }
    initialize(**options)
    
    # Configure tracer
    tracer.configure(
        hostname="syslog.example.com",
        port=8126,  # Datadog Agent port
        service="log-ai-mcp",
        env="production",
    )
    
    # Auto-patch supported libraries
    patch_all()
    
    # Enable runtime metrics (CPU, memory, threads)
    RuntimeMetrics.enable()
    
    print("[DATADOG] APM initialized")
    return True


@contextmanager
def trace_search(service: str, pattern: str):
    """Create APM trace for search operation"""
    span = tracer.trace(
        "search_logs",
        service="log-ai-mcp",
        resource=f"search:{service}"
    )
    
    try:
        # Add tags
        span.set_tag("service_name", service)
        span.set_tag("pattern_length", len(pattern))
        span.set_tag("ssh_user", os.environ.get("USER", "unknown"))
        
        # Add SSH client IP
        ssh_conn = os.environ.get("SSH_CONNECTION", "")
        if ssh_conn:
            span.set_tag("client_ip", ssh_conn.split()[0])
        
        yield span
    
    finally:
        span.finish()


def track_cache_operation(operation: str, hit: bool, duration_ms: float):
    """Track cache operations"""
    statsd.increment(
        'log_ai.cache.operations',
        tags=[f"operation:{operation}", f"hit:{hit}"]
    )
    
    statsd.histogram(
        'log_ai.cache.duration_ms',
        duration_ms,
        tags=[f"operation:{operation}"]
    )
    
    if hit:
        statsd.increment('log_ai.cache.hits')
    else:
        statsd.increment('log_ai.cache.misses')


def track_search_metrics(
    service: str,
    duration_ms: float,
    matched_files: int,
    result_count: int,
    cache_hit: bool
):
    """Track search metrics"""
    tags = [
        f"service:{service}",
        f"cache_hit:{cache_hit}"
    ]
    
    # Search duration
    statsd.histogram('log_ai.search.duration_ms', duration_ms, tags=tags)
    
    # Files processed
    statsd.histogram('log_ai.search.files_matched', matched_files, tags=tags)
    
    # Results returned
    statsd.histogram('log_ai.search.result_count', result_count, tags=tags)
    
    # Search counter
    statsd.increment('log_ai.search.total', tags=tags)
    
    # Flag slow searches
    if duration_ms > 5000:
        statsd.increment('log_ai.search.slow', tags=tags)


def track_redis_operation(operation: str, duration_ms: float, success: bool):
    """Track Redis operations"""
    tags = [
        f"operation:{operation}",
        f"success:{success}"
    ]
    
    statsd.histogram('log_ai.redis.duration_ms', duration_ms, tags=tags)
    statsd.increment('log_ai.redis.operations', tags=tags)


def track_semaphore_metrics(active_searches: int, max_searches: int):
    """Track global semaphore state"""
    statsd.gauge('log_ai.semaphore.active_searches', active_searches)
    statsd.gauge('log_ai.semaphore.max_searches', max_searches)
    
    utilization = (active_searches / max_searches) * 100
    statsd.gauge('log_ai.semaphore.utilization_pct', utilization)


def track_error(error_type: str, service: str, message: str):
    """Track errors"""
    tags = [
        f"error_type:{error_type}",
        f"service:{service}"
    ]
    
    statsd.increment('log_ai.errors.total', tags=tags)


class DatadogLogger:
    """Send logs to Datadog"""
    
    @staticmethod
    def log(level: str, message: str, **kwargs):
        """Send structured log to Datadog"""
        # Logs are automatically collected by Datadog Agent from stdout
        # when properly configured
        import json
        log_entry = {
            "level": level,
            "message": message,
            "service": "log-ai-mcp",
            "timestamp": time.time(),
            **kwargs
        }
        print(json.dumps(log_entry))
```

### Task 3.4: Integrate Datadog into server.py

**Changes to `src/server.py`:**

1. **Add imports and initialize:**
```python
from datadog_integration import (
    init_datadog,
    trace_search,
    track_cache_operation,
    track_search_metrics,
    track_redis_operation,
    track_semaphore_metrics,
    track_error,
    DatadogLogger
)

# Initialize Datadog (after line ~75)
datadog_enabled = init_datadog()
dd_logger = DatadogLogger()
```

2. **Wrap search_logs_handler with APM tracing:**
```python
async def search_logs_handler(arguments: dict) -> Sequence[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    service_name = arguments.get("service")
    pattern = arguments.get("pattern", "")
    
    start_time = time.time()
    cache_hit = False
    
    if datadog_enabled:
        with trace_search(service_name, pattern) as span:
            try:
                # Check cache
                cache_start = time.time()
                cached_result = await search_cache.get(...)
                cache_duration = (time.time() - cache_start) * 1000
                
                if cached_result:
                    cache_hit = True
                    span.set_tag("cache_hit", True)
                    track_cache_operation("get", hit=True, duration_ms=cache_duration)
                    # ... return cached result
                else:
                    track_cache_operation("get", hit=False, duration_ms=cache_duration)
                
                # Perform search
                span.set_tag("cache_hit", False)
                
                # ... existing search logic ...
                
                # Track metrics
                duration_ms = (time.time() - start_time) * 1000
                track_search_metrics(
                    service=service_name,
                    duration_ms=duration_ms,
                    matched_files=len(matched_files),
                    result_count=len(results),
                    cache_hit=cache_hit
                )
                
                return results
            
            except Exception as e:
                span.set_tag("error", True)
                track_error(
                    error_type=type(e).__name__,
                    service=service_name,
                    message=str(e)
                )
                raise
    else:
        # Fallback if Datadog disabled
        # ... existing logic ...
```

3. **Track Redis operations:**
```python
# In RedisSemaphore.__aenter__:
if datadog_enabled:
    redis_start = time.time()
    try:
        current = await self.redis.incr(self.key)
        redis_duration = (time.time() - redis_start) * 1000
        track_redis_operation("incr", redis_duration, success=True)
    except RedisError as e:
        redis_duration = (time.time() - redis_start) * 1000
        track_redis_operation("incr", redis_duration, success=False)
```

4. **Track semaphore utilization:**
```python
# After acquiring semaphore:
if datadog_enabled:
    active = await redis_coordinator.redis.get("log-ai:sem:global_searches")
    track_semaphore_metrics(
        active_searches=int(active or 0),
        max_searches=MAX_GLOBAL_SEARCHES
    )
```

### Task 3.5: Configure Datadog Dashboards

**Create dashboard: "LogAI MCP Performance"**

**Widgets:**

1. **Search Performance:**
   - Metric: `avg:log_ai.search.duration_ms{*} by {service}`
   - Type: Timeseries
   - Alert: avg > 10000ms

2. **Cache Hit Rate:**
   - Metric: `(sum:log_ai.cache.hits / (sum:log_ai.cache.hits + sum:log_ai.cache.misses)) * 100`
   - Type: Query Value
   - Target: >80%

3. **Active Searches:**
   - Metric: `avg:log_ai.semaphore.active_searches`
   - Type: Timeseries
   - Compare with: `log_ai.semaphore.max_searches`

4. **Error Rate:**
   - Metric: `sum:log_ai.errors.total{*} by {error_type}.as_rate()`
   - Type: Toplist

5. **Service Latency:**
   - Metric: `p95:log_ai.search.duration_ms{*} by {service}`
   - Type: Heat Map

6. **Redis Performance:**
   - Metric: `avg:log_ai.redis.duration_ms{*} by {operation}`
   - Type: Timeseries

7. **System Resources:**
   - Metrics: `system.cpu.user`, `system.mem.used`
   - Type: Timeseries

8. **Slow Searches:**
   - Metric: `sum:log_ai.search.slow{*} by {service}`
   - Type: Toplist

### Task 3.6: Configure APM Service Map

**Navigate to:** APM → Service Map

**Configure:**
- Primary service: `log-ai-mcp`
- Dependencies: `redis`, `ssh`, `ripgrep`
- Show latency and error rates between services

### Task 3.7: Create Monitors and Alerts

**Monitor 1: High Search Latency**
```
Metric: avg(last_10m):avg:log_ai.search.duration_ms{*} > 15000
Alert: Slack + email
Message: "LogAI searches are slow (avg >15s). Check service health."
```

**Monitor 2: Cache Hit Rate Drop**
```
Metric: (sum:log_ai.cache.hits / (sum:log_ai.cache.hits + sum:log_ai.cache.misses)) * 100 < 50
Alert: Slack
Message: "Cache hit rate below 50%. May indicate cache size issue or pattern changes."
```

**Monitor 3: Semaphore Saturation**
```
Metric: avg(last_5m):avg:log_ai.semaphore.utilization_pct{*} > 90
Alert: Slack
Message: "Search semaphore at 90%+ utilization. Consider increasing limit or investigating slow searches."
```

**Monitor 4: Redis Connection Issues**
```
Metric: sum(last_5m):log_ai.redis.operations{success:false} > 10
Alert: PagerDuty + Slack
Message: "Redis connection issues detected. Check Redis health and network."
```

**Monitor 5: Error Spike**
```
Metric: sum(last_5m):log_ai.errors.total{*}.as_rate() > 1
Alert: Slack
Message: "Error rate elevated. Check logs and traces for root cause."
```

### Task 3.8: Configure Log Pipeline

**Log source:** `log-ai-mcp`

**Log processing rules:**

1. **Parse JSON logs:**
   - Pattern: `{"level": "(?<level>\w+)", "message": "(?<msg>.*)", ...}`
   - Extract: level, message, service, duration_ms

2. **Add facets:**
   - `service_name` (string)
   - `cache_hit` (boolean)
   - `duration_ms` (number)
   - `error_type` (string)
   - `client_ip` (string)

3. **Create indexes:**
   - High priority: `status:error`
   - Medium priority: `duration_ms:>5000`
   - Low priority: everything else

### Task 3.9: MCP Tool for AI Agents

**Add new MCP tool: `get_datadog_insights`**

```python
@server.call_tool()
async def get_datadog_insights(arguments: dict) -> Sequence[types.TextContent]:
    """
    Query Datadog for system insights
    
    Args:
        query_type: "slow_searches" | "errors" | "cache_stats" | "system_health"
        timeframe: "1h" | "6h" | "24h" | "7d"
    """
    query_type = arguments.get("query_type")
    timeframe = arguments.get("timeframe", "1h")
    
    # Query Datadog API
    from datadog import api
    
    if query_type == "slow_searches":
        # Get slowest searches in timeframe
        query = f"avg:log_ai.search.duration_ms{{*}} by {{service}}.rollup(avg, {timeframe})"
        result = api.Metric.query(start=..., end=..., query=query)
        # Format and return
        
    elif query_type == "errors":
        # Get error breakdown
        query = f"sum:log_ai.errors.total{{*}} by {{error_type}}.as_count()"
        result = api.Metric.query(...)
        
    # ... handle other query types
    
    return [types.TextContent(type="text", text=formatted_result)]
```

## Chunk 3 Deliverables

✅ Datadog Agent installed and configured on syslog server
✅ APM tracing for all search operations
✅ Custom metrics: cache, semaphore, search performance
✅ Redis operation monitoring
✅ Infrastructure metrics: CPU, memory, disk
✅ Custom dashboards for system overview
✅ Service map showing dependencies
✅ Monitors and alerts for critical issues
✅ Log aggregation and parsing
✅ MCP tool for AI agents to query Datadog

## Chunk 3 Success Metrics

- ✅ AI agents can query: "What's the p95 search latency?"
- ✅ AI agents can query: "Show me errors in the last hour"
- ✅ AI agents can query: "Which service is slowest?"
- ✅ Service map shows: MCP → Redis → ripgrep
- ✅ Distributed traces show bottlenecks
- ✅ Alerts fire when issues detected
- ✅ Dashboard visible at: https://app.datadoghq.com/dashboard/log-ai-mcp

---

# Implementation Timeline

## Phase 1: Chunk 1 - Redis Coordination (3-4 days)
- Day 1: Redis setup, module creation, basic integration
- Day 2: Update server.py, testing with concurrent sessions
- Day 3: Deployment, monitoring, bug fixes
- Day 4: Documentation and validation

## Phase 2: Chunk 2 - Sentry Integration (2-3 days)
- Day 1: Sentry setup, SDK integration, basic tracking
- Day 2: Dashboard creation, alert rules, testing
- Day 3: Validation with real searches, refinement

## Phase 3: Chunk 3 - Datadog Integration (4-5 days)
- Day 1: Datadog Agent setup, SDK integration
- Day 2: Metrics implementation, APM tracing
- Day 3: Dashboard creation, monitors, alerts
- Day 4: Log pipeline, MCP tool for insights
- Day 5: End-to-end testing, documentation

**Total: 9-12 days**

---

# Success Criteria

## Chunk 1 Complete When:
- ✅ 5 concurrent SSH sessions share 500MB cache (not 1500MB)
- ✅ Global semaphore enforces 20 concurrent searches system-wide
- ✅ Redis monitor shows active connections
- ✅ Graceful fallback if Redis unavailable

## Chunk 2 Complete When:
- ✅ Exceptions automatically captured in Sentry
- ✅ AI agent can view recent errors via Sentry dashboard
- ✅ Slow searches (>5s) flagged and visible
- ✅ Alerts fire for critical issues

## Chunk 3 Complete When:
- ✅ Datadog dashboard shows real-time metrics
- ✅ APM traces show search flow: MCP → Redis → ripgrep
- ✅ AI agent can query: "Show me system health"
- ✅ Service map displays all dependencies
- ✅ Monitors alert on anomalies

---

# Rollback Plan

**If issues encountered:**

1. **Chunk 1 rollback:**
   ```bash
   # Revert to pre-Redis code
   git revert <redis-commit>
   bash scripts/deploy.sh
   # Stop Redis
   sudo systemctl stop redis-log-ai
   ```

2. **Chunk 2 rollback:**
   ```bash
   # Disable Sentry
   unset SENTRY_DSN
   # Remove Sentry initialization
   ```

3. **Chunk 3 rollback:**
   ```bash
   # Stop Datadog Agent
   sudo systemctl stop datadog-agent
   # Remove DD_API_KEY
   unset DD_API_KEY
   ```

---

# Requirements & Constraints (CONFIRMED)

## Scale & Capacity

**Concurrent Users:**
- **Maximum**: 150 SSH sessions simultaneously
- **Average**: 10-20 sessions during normal operations
- **Implication**: Redis must handle high concurrency, need connection pooling

**Current State:**
- ❌ No baseline metrics for memory usage with N users
- ❌ No observed resource exhaustion issues yet
- ❌ No cache hit rate data available

**Primary Goal:**
- **Prevent overwhelming syslog server** (avoid server crashes/death)
- Limiting concurrent searches is **simplest MVP approach**
- Will tune limits based on observed performance after deployment

## Configuration Strategy: Everything Configurable

### Redis Configuration (Environment Variables)

**Persistence:**
```bash
# Default: cache-only (no disk writes)
REDIS_PERSISTENCE=false

# Enable persistence if needed later
REDIS_PERSISTENCE=true
```

**Memory Limit:**
```bash
# Default: 500MB
REDIS_MAX_MEMORY=500mb

# Can increase based on cache hit rate analysis
REDIS_MAX_MEMORY=1gb
REDIS_MAX_MEMORY=2gb
```

**Rationale:** Shared cache suspected to be **very important** for "usual suspects" searches over time. Need flexibility to adjust as usage patterns emerge.

### Global Semaphore Configuration

**Max Concurrent Searches:**
```bash
# Default: conservative start
MAX_GLOBAL_SEARCHES=20

# Can increase based on syslog server capacity monitoring
MAX_GLOBAL_SEARCHES=50
MAX_GLOBAL_SEARCHES=100
```

**Strategy:** Start conservative (20), monitor CPU/memory, scale incrementally.

### Sentry Configuration (Environment Variables)

**Sample Rates:**
```bash
# Default: 100% transaction sampling (can adjust if too noisy)
SENTRY_TRACES_SAMPLE_RATE=1.0

# Default: 10% profiling sampling
SENTRY_PROFILES_SAMPLE_RATE=0.1

# Can reduce if volume is too high
SENTRY_TRACES_SAMPLE_RATE=0.5  # 50%
SENTRY_PROFILES_SAMPLE_RATE=0.05  # 5%
```

**Alert Destinations (Both Teams & Slack):**
```bash
# Microsoft Teams webhook
SENTRY_ALERT_TEAMS_WEBHOOK=https://outlook.office.com/webhook/...

# Slack webhook
SENTRY_ALERT_SLACK_WEBHOOK=https://hooks.slack.com/services/...
```

**Rationale:** Start with arbitrary rates, adjust based on alert volume and overhead.

### Datadog Configuration

**Status:** Questions deferred until Chunk 3 implementation
- Dashboard layout preferences
- Custom metrics priorities
- Log retention period
- Will decide based on insights from Sentry data collected during Chunk 2

## Implementation Strategy: Staged Rollout with Data Collection

### Phase 1: Deploy with Conservative Defaults
- `MAX_GLOBAL_SEARCHES=20`
- `REDIS_MAX_MEMORY=500mb`
- `REDIS_PERSISTENCE=false`
- `SENTRY_TRACES_SAMPLE_RATE=1.0`

### Phase 2: Monitor & Collect Baseline (1-2 weeks)
Gather metrics on:
- Cache hit rate (target: >80%)
- Search latency (target: p95 < 10s)
- Server CPU/memory usage (target: <70% utilization)
- Concurrent user patterns
- Error rates and types

### Phase 3: Tune Based on Observations
Adjust environment variables based on data:
- **If cache hit rate high (>80%)**: Keep 500MB or reduce
- **If cache hit rate low (<50%)**: Increase to 1GB
- **If semaphore utilization >90%**: Increase to 30-50 searches
- **If server CPU <50%**: Increase semaphore limit
- **If Sentry too noisy**: Reduce sample rates

### Phase 4: Scale Incrementally
- Test increased limits: 20 → 30 → 50 → 100 searches
- Monitor for resource exhaustion at each step
- Rollback if issues observed

## Testing Between Chunks

**1 week monitoring period between each chunk:**
- Chunk 1 → Wait 1 week → Analyze Redis metrics
- Chunk 2 → Wait 1 week → Analyze Sentry patterns
- Chunk 3 → Final validation

**Goal:** Gather real-world data points before adding complexity.

## Configuration File Examples

### Environment Configuration (`config/.env`)

```bash
# LogAI MCP Server Configuration

# Redis Configuration
export REDIS_HOST=localhost
export REDIS_PORT=6379
export REDIS_MAX_MEMORY=500mb
export REDIS_PERSISTENCE=false

# Global Limits
export MAX_GLOBAL_SEARCHES=20
export MAX_PER_SERVICE_SEARCHES=5

# Sentry Configuration
export SENTRY_DSN='https://xxx@yyy.ingest.sentry.io/zzz'
export SENTRY_TRACES_SAMPLE_RATE=1.0
export SENTRY_PROFILES_SAMPLE_RATE=0.1
export SENTRY_ALERT_TEAMS_WEBHOOK='https://outlook.office.com/webhook/...'
export SENTRY_ALERT_SLACK_WEBHOOK='https://hooks.slack.com/services/...'

# Datadog Configuration (Chunk 3)
export DD_API_KEY='your-api-key'
export DD_APP_KEY='your-app-key'
export DD_SITE='datadoghq.com'

# Cache Configuration
export CACHE_TTL_MINUTES=10
export CACHE_MAX_SIZE_MB=500

# Logging
export LOG_LEVEL=INFO
export LOG_FORMAT=json
```

### Updated Redis Config Template (`/etc/redis/log-ai.conf`)

```ini
# Security
bind 127.0.0.1
protected-mode yes
port 6379

# Memory Configuration (CONFIGURABLE)
maxmemory ${REDIS_MAX_MEMORY:-500mb}
maxmemory-policy allkeys-lru

# Persistence (CONFIGURABLE)
# Default: cache-only (no persistence)
save ""
appendonly no

# To enable persistence:
# save 900 1
# save 300 10
# save 60 10000
# appendonly yes

# Performance
timeout 300
tcp-keepalive 300

# Monitoring
loglevel notice
logfile /var/log/redis/log-ai.log
```

## Success Metrics & Targets

### Chunk 1 Targets (Redis Coordination)
- ✅ **Cache Hit Rate**: Target >80% (measure after 1 week)
- ✅ **Semaphore Utilization**: <90% average, <95% p99
- ✅ **Memory Usage**: <70% of available RAM
- ✅ **Search Latency**: p95 < 10s, p99 < 20s
- ✅ **Redis Uptime**: >99.9%

### Chunk 2 Targets (Sentry Integration)
- ✅ **Error Capture Rate**: 100% of exceptions
- ✅ **Alert Response Time**: <5 minutes to notification
- ✅ **False Positive Rate**: <10% of alerts
- ✅ **Performance Overhead**: <2ms per transaction

### Chunk 3 Targets (Datadog Integration)
- ✅ **Trace Capture**: 100% of searches
- ✅ **Dashboard Load Time**: <2s
- ✅ **Metric Resolution**: 1-minute granularity
- ✅ **Alert Accuracy**: >90%

## Risk Mitigation

### Risk: Redis SPOF (Single Point of Failure)
- **Mitigation**: Graceful fallback to local cache/semaphore
- **Test**: Kill Redis during active searches, verify fallback works
- **Recovery**: Auto-reconnect with exponential backoff

### Risk: Syslog Server Overload (150 concurrent users)
- **Mitigation**: Conservative semaphore limit (20 searches)
- **Monitoring**: CPU/memory alerts at 70% threshold
- **Response**: Reduce MAX_GLOBAL_SEARCHES if needed

### Risk: Cache Too Small (500MB insufficient)
- **Detection**: Cache hit rate <50% after 1 week
- **Action**: Increase REDIS_MAX_MEMORY to 1GB
- **Validation**: Monitor hit rate improvement

### Risk: Alert Fatigue (too many notifications)
- **Detection**: >10 alerts per day
- **Action**: Reduce SENTRY_TRACES_SAMPLE_RATE to 0.5
- **Validation**: Alert volume decreases without missing critical issues

## Next Steps

1. **Implement Chunk 1** with all configuration options
2. **Deploy to production** with conservative defaults
3. **Monitor for 1 week**, gather baseline metrics
4. **Tune configuration** based on observed data
5. **Proceed to Chunk 2** once stable
