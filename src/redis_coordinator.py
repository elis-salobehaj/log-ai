"""
Redis-based coordination for global resource limits and shared cache.

Provides:
- RedisCoordinator: Connection management with health checks
- RedisSemaphore: Distributed semaphore for global concurrency limits
- RedisCache: Distributed cache compatible with existing SearchCache interface
- RedisMetrics: Basic metrics tracking for monitoring

All components gracefully handle Redis failures and support fallback to local state.
"""
import asyncio
import json
import hashlib
import time
import sys
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

try:
    from redis.asyncio import Redis
    from redis.exceptions import RedisError, ConnectionError as RedisConnectionError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    Redis = None
    RedisError = Exception
    RedisConnectionError = Exception


class RedisCoordinator:
    """Manages Redis connection with health checks and reconnection logic"""
    
    def __init__(self, host: str = 'localhost', port: int = 6379, password: Optional[str] = None, db: int = 0):
        if not REDIS_AVAILABLE:
            raise ImportError("redis package not installed. Install with: pip install redis")
        
        self.host = host
        self.port = port
        self.password = password
        self.db = db
        self.redis: Optional[Redis] = None
        self._connected = False
        self._connection_attempts = 0
        self._last_connection_attempt = 0
        self._reconnect_delay = 5  # seconds between reconnection attempts
    
    async def connect(self) -> bool:
        """
        Establish Redis connection with timeout.
        Returns True if connected, False otherwise.
        """
        # Rate limit connection attempts
        now = time.time()
        if now - self._last_connection_attempt < self._reconnect_delay:
            return self._connected
        
        self._last_connection_attempt = now
        self._connection_attempts += 1
        
        try:
            self.redis = Redis(
                host=self.host,
                port=self.port,
                password=self.password,
                db=self.db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
                health_check_interval=30
            )
            
            # Test connection
            await asyncio.wait_for(self.redis.ping(), timeout=5)
            self._connected = True
            self._connection_attempts = 0  # Reset on success
            
            sys.stderr.write(
                f"[REDIS] Connected to {self.host}:{self.port} (db={self.db})\n"
            )
            sys.stderr.flush()
            return True
            
        except (RedisError, RedisConnectionError, asyncio.TimeoutError) as e:
            self._connected = False
            sys.stderr.write(
                f"[REDIS] Connection failed (attempt {self._connection_attempts}): {e}\n"
            )
            sys.stderr.flush()
            return False
    
    async def close(self):
        """Close Redis connection gracefully"""
        if self.redis:
            try:
                await self.redis.close()
                sys.stderr.write("[REDIS] Connection closed\n")
                sys.stderr.flush()
            except Exception as e:
                sys.stderr.write(f"[REDIS] Error closing connection: {e}\n")
                sys.stderr.flush()
            finally:
                self._connected = False
    
    @property
    def is_connected(self) -> bool:
        """Check if Redis is currently connected"""
        return self._connected
    
    async def health_check(self) -> bool:
        """Perform health check and attempt reconnection if needed"""
        if not self._connected:
            return await self.connect()
        
        try:
            await asyncio.wait_for(self.redis.ping(), timeout=2)
            return True
        except Exception:
            self._connected = False
            return await self.connect()


class RedisSemaphore:
    """
    Distributed semaphore using Redis for global concurrency limits.
    
    Uses atomic INCR/DECR operations with automatic expiry for crash recovery.
    Falls back gracefully if Redis is unavailable.
    """
    
    def __init__(self, redis: Redis, key: str, max_count: int):
        self.redis = redis
        self.key = f"log-ai:sem:{key}"
        self.max_count = max_count
        self.token = None
        self._acquired = False
    
    async def __aenter__(self):
        """Acquire semaphore with retry logic"""
        retry_count = 0
        max_retries = 100
        retry_delay = 0.5
        
        while retry_count < max_retries:
            try:
                # Atomic increment
                current = await self.redis.incr(self.key)
                
                if current <= self.max_count:
                    self.token = current
                    self._acquired = True
                    # Set expiry to auto-cleanup if process crashes (1 hour)
                    await self.redis.expire(self.key, 3600)
                    
                    sys.stderr.write(
                        f"[SEMAPHORE] Acquired ({current}/{self.max_count})\n"
                    )
                    sys.stderr.flush()
                    return self
                else:
                    # Over limit, decrement and retry
                    await self.redis.decr(self.key)
                    await asyncio.sleep(retry_delay)
                    retry_count += 1
            
            except (RedisError, RedisConnectionError) as e:
                sys.stderr.write(
                    f"[SEMAPHORE] Redis error during acquire: {e}\n"
                )
                sys.stderr.flush()
                raise RuntimeError("Redis semaphore unavailable")
        
        raise TimeoutError(
            f"Could not acquire semaphore after {max_retries} retries "
            f"(limit: {self.max_count})"
        )
    
    async def __aexit__(self, *args):
        """Release semaphore"""
        if self._acquired and self.token:
            try:
                current = await self.redis.decr(self.key)
                sys.stderr.write(
                    f"[SEMAPHORE] Released ({current}/{self.max_count})\n"
                )
                sys.stderr.flush()
            except (RedisError, RedisConnectionError) as e:
                # Best effort - log but don't raise
                sys.stderr.write(
                    f"[SEMAPHORE] Error during release: {e}\n"
                )
                sys.stderr.flush()


class RedisCache:
    """
    Distributed cache using Redis for shared search results.
    
    Compatible with existing SearchCache interface:
    - get(services, query, time_range) -> Optional[Tuple[List[Dict], Dict]]
    - put(services, query, time_range, matches, metadata)
    
    Stores results as JSON with TTL. Automatically handles serialization errors.
    """
    
    def __init__(self, redis: Redis, ttl_seconds: int = 600):
        self.redis = redis
        self.ttl = ttl_seconds
        self.hits = 0
        self.misses = 0
    
    def _make_key(self, services: List[str], query: str, time_range: Dict[str, int]) -> str:
        """
        Generate cache key from search parameters.
        Compatible with existing SearchCache key format.
        """
        # Sort services for order-independence
        services_sorted = tuple(sorted(services))
        time_str = json.dumps(time_range, sort_keys=True)
        key_str = f"{services_sorted}:{query}:{time_str}"
        key_hash = hashlib.md5(key_str.encode()).hexdigest()
        return f"log-ai:cache:{key_hash}"
    
    async def get(
        self, 
        services: List[str], 
        query: str, 
        time_range: Dict[str, int]
    ) -> Optional[Tuple[List[Dict], Dict]]:
        """
        Get cached search results.
        Returns (matches, metadata) tuple or None if not found/expired.
        """
        try:
            key = self._make_key(services, query, time_range)
            data = await self.redis.get(key)
            
            if not data:
                self.misses += 1
                return None
            
            # Deserialize
            cached = json.loads(data)
            matches = cached.get("matches", [])
            metadata = cached.get("metadata", {})
            
            self.hits += 1
            hit_rate = self.hits / (self.hits + self.misses) * 100
            
            sys.stderr.write(
                f"[CACHE] HIT {key[:16]}... (hit rate: {hit_rate:.1f}%)\n"
            )
            sys.stderr.flush()
            
            return matches, metadata
        
        except (RedisError, json.JSONDecodeError) as e:
            self.misses += 1
            sys.stderr.write(f"[CACHE] Error during get: {e}\n")
            sys.stderr.flush()
            return None
    
    async def put(
        self,
        services: List[str],
        query: str,
        time_range: Dict[str, int],
        matches: List[Dict],
        metadata: Dict
    ):
        """
        Store search results in cache with TTL.
        Silently fails if Redis unavailable (best effort caching).
        """
        try:
            key = self._make_key(services, query, time_range)
            
            cache_entry = {
                "matches": matches,
                "metadata": metadata,
                "cached_at": datetime.now().isoformat(),
            }
            
            # Serialize and store with TTL
            data = json.dumps(cache_entry)
            await self.redis.setex(key, self.ttl, data)
            
            size_kb = len(data) / 1024
            sys.stderr.write(
                f"[CACHE] PUT {key[:16]}... ({size_kb:.1f} KB, TTL: {self.ttl}s)\n"
            )
            sys.stderr.flush()
        
        except (RedisError, json.JSONDecodeError, TypeError) as e:
            # Best effort - don't raise on cache failures
            sys.stderr.write(f"[CACHE] Error during put: {e}\n")
            sys.stderr.flush()
    
    async def clear(self):
        """Clear all cache entries (for testing/maintenance)"""
        try:
            keys = await self.redis.keys("log-ai:cache:*")
            if keys:
                await self.redis.delete(*keys)
                sys.stderr.write(f"[CACHE] Cleared {len(keys)} entries\n")
                sys.stderr.flush()
        except RedisError as e:
            sys.stderr.write(f"[CACHE] Error during clear: {e}\n")
            sys.stderr.flush()
    
    async def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        try:
            keys = await self.redis.keys("log-ai:cache:*")
            hit_rate = self.hits / (self.hits + self.misses) * 100 if (self.hits + self.misses) > 0 else 0
            
            return {
                "entries": len(keys),
                "ttl_seconds": self.ttl,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": hit_rate
            }
        except RedisError as e:
            sys.stderr.write(f"[CACHE] Error getting stats: {e}\n")
            sys.stderr.flush()
            return {
                "entries": 0,
                "ttl_seconds": self.ttl,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": 0
            }


class RedisMetrics:
    """
    Basic metrics tracking in Redis for monitoring.
    
    Tracks counters and timing information for:
    - Total searches
    - Search duration
    - Cache operations
    - Errors
    """
    
    def __init__(self, redis: Redis):
        self.redis = redis
    
    async def increment_counter(self, metric: str, value: int = 1):
        """Increment a counter metric"""
        try:
            await self.redis.incrby(f"log-ai:metrics:{metric}", value)
        except RedisError as e:
            # Silent failure for metrics
            sys.stderr.write(f"[METRICS] Error incrementing {metric}: {e}\n")
            sys.stderr.flush()
    
    async def record_timing(self, metric: str, duration_ms: float):
        """
        Record timing metric (stores last 100 values for percentile calculation).
        """
        try:
            key = f"log-ai:timings:{metric}"
            await self.redis.lpush(key, str(duration_ms))
            await self.redis.ltrim(key, 0, 99)  # Keep last 100
            await self.redis.expire(key, 3600)  # 1 hour TTL
        except RedisError as e:
            sys.stderr.write(f"[METRICS] Error recording timing {metric}: {e}\n")
            sys.stderr.flush()
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get all counter metrics"""
        try:
            metrics = {}
            
            # Get all counter keys
            counter_keys = await self.redis.keys("log-ai:metrics:*")
            for key in counter_keys:
                metric_name = key.replace("log-ai:metrics:", "")
                value = await self.redis.get(key)
                metrics[metric_name] = int(value) if value else 0
            
            return metrics
        except RedisError as e:
            sys.stderr.write(f"[METRICS] Error getting metrics: {e}\n")
            sys.stderr.flush()
            return {}
    
    async def get_timing_stats(self, metric: str) -> Dict[str, float]:
        """Get timing statistics (avg, min, max) for a metric"""
        try:
            key = f"log-ai:timings:{metric}"
            values = await self.redis.lrange(key, 0, -1)
            
            if not values:
                return {"count": 0, "avg": 0, "min": 0, "max": 0}
            
            floats = [float(v) for v in values]
            return {
                "count": len(floats),
                "avg": sum(floats) / len(floats),
                "min": min(floats),
                "max": max(floats)
            }
        except (RedisError, ValueError) as e:
            sys.stderr.write(f"[METRICS] Error getting timing stats for {metric}: {e}\n")
            sys.stderr.flush()
            return {"count": 0, "avg": 0, "min": 0, "max": 0}
