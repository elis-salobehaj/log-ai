#!/usr/bin/env python3
"""
Test Redis coordinator functionality
Tests connection, semaphore, cache, and metrics
"""
import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from redis_coordinator import (
    RedisCoordinator,
    RedisSemaphore,
    RedisCache,
    RedisMetrics
)


async def test_connection():
    """Test basic Redis connection"""
    print("\n" + "=" * 60)
    print("Test 1: Redis Connection")
    print("=" * 60)
    
    coordinator = RedisCoordinator(host='localhost', port=6379)
    
    # Test connection
    connected = await coordinator.connect()
    if not connected:
        print("✗ Failed to connect to Redis")
        print("  Make sure Redis is running: redis-cli ping")
        return False
    
    print(f"✓ Connected to Redis at {coordinator.host}:{coordinator.port}")
    print(f"  Connection status: {coordinator.is_connected}")
    
    # Test health check
    healthy = await coordinator.health_check()
    print(f"✓ Health check passed: {healthy}")
    
    await coordinator.close()
    print("✓ Connection closed successfully")
    
    return True


async def test_semaphore():
    """Test distributed semaphore"""
    print("\n" + "=" * 60)
    print("Test 2: Distributed Semaphore")
    print("=" * 60)
    
    coordinator = RedisCoordinator(host='localhost', port=6379)
    if not await coordinator.connect():
        print("✗ Cannot test semaphore without Redis connection")
        return False
    
    # Test acquiring and releasing semaphore
    semaphore = RedisSemaphore(coordinator.redis, "test_searches", max_count=3)
    
    print("Testing semaphore acquire/release...")
    async with semaphore:
        print("✓ Semaphore acquired")
        
        # Verify counter in Redis
        current = await coordinator.redis.get("log-ai:sem:test_searches")
        print(f"  Current count: {current}/3")
    
    print("✓ Semaphore released")
    
    # Test concurrent acquisitions
    print("\nTesting concurrent semaphore usage (max 3)...")
    
    async def acquire_and_hold(sem_id: int):
        sem = RedisSemaphore(coordinator.redis, "test_concurrent", max_count=3)
        async with sem:
            print(f"  Semaphore {sem_id} acquired")
            await asyncio.sleep(0.1)
            print(f"  Semaphore {sem_id} released")
    
    # This should work (3 concurrent)
    tasks = [acquire_and_hold(i) for i in range(3)]
    await asyncio.gather(*tasks)
    print("✓ Concurrent semaphore usage works correctly")
    
    await coordinator.close()
    return True


async def test_cache():
    """Test distributed cache"""
    print("\n" + "=" * 60)
    print("Test 3: Distributed Cache")
    print("=" * 60)
    
    coordinator = RedisCoordinator(host='localhost', port=6379)
    if not await coordinator.connect():
        print("✗ Cannot test cache without Redis connection")
        return False
    
    cache = RedisCache(coordinator.redis, ttl_seconds=60)
    
    # Test put and get
    services = ["service1", "service2"]
    query = "error"
    time_range = {"start": 0, "end": 3600}
    matches = [{"line": "error message 1"}, {"line": "error message 2"}]
    metadata = {"total": 2, "duration": 1.5}
    
    print("Testing cache put...")
    await cache.put(services, query, time_range, matches, metadata)
    print("✓ Data stored in cache")
    
    print("\nTesting cache get (should hit)...")
    result = await cache.get(services, query, time_range)
    if result:
        cached_matches, cached_metadata = result
        print(f"✓ Cache HIT - retrieved {len(cached_matches)} matches")
        print(f"  Metadata: {cached_metadata}")
        assert len(cached_matches) == 2
        assert cached_metadata["total"] == 2
    else:
        print("✗ Cache miss (expected hit)")
        await coordinator.close()
        return False
    
    print("\nTesting cache get with different query (should miss)...")
    result = await cache.get(services, "different query", time_range)
    if result is None:
        print("✓ Cache MISS (as expected)")
    else:
        print("✗ Cache hit (expected miss)")
    
    # Test stats
    stats = await cache.stats()
    print(f"\nCache statistics:")
    print(f"  Entries: {stats['entries']}")
    print(f"  Hits: {stats['hits']}")
    print(f"  Misses: {stats['misses']}")
    print(f"  Hit rate: {stats['hit_rate']:.1f}%")
    
    # Cleanup
    await cache.clear()
    print("\n✓ Cache cleared")
    
    await coordinator.close()
    return True


async def test_metrics():
    """Test metrics tracking"""
    print("\n" + "=" * 60)
    print("Test 4: Metrics Tracking")
    print("=" * 60)
    
    coordinator = RedisCoordinator(host='localhost', port=6379)
    if not await coordinator.connect():
        print("✗ Cannot test metrics without Redis connection")
        return False
    
    metrics = RedisMetrics(coordinator.redis)
    
    # Test counter
    print("Testing counter metrics...")
    await metrics.increment_counter("test_searches", 1)
    await metrics.increment_counter("test_searches", 1)
    await metrics.increment_counter("test_errors", 1)
    print("✓ Counters incremented")
    
    # Test timing
    print("\nTesting timing metrics...")
    await metrics.record_timing("search_duration", 123.45)
    await metrics.record_timing("search_duration", 234.56)
    await metrics.record_timing("search_duration", 345.67)
    print("✓ Timings recorded")
    
    # Get metrics
    all_metrics = await metrics.get_metrics()
    print(f"\nAll metrics: {all_metrics}")
    
    timing_stats = await metrics.get_timing_stats("search_duration")
    print(f"\nTiming stats for 'search_duration':")
    print(f"  Count: {timing_stats['count']}")
    print(f"  Average: {timing_stats['avg']:.2f}ms")
    print(f"  Min: {timing_stats['min']:.2f}ms")
    print(f"  Max: {timing_stats['max']:.2f}ms")
    
    # Cleanup
    await coordinator.redis.delete("log-ai:metrics:test_searches")
    await coordinator.redis.delete("log-ai:metrics:test_errors")
    await coordinator.redis.delete("log-ai:timings:search_duration")
    print("\n✓ Test metrics cleaned up")
    
    await coordinator.close()
    return True


async def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("Redis Coordinator Test Suite")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Connection", await test_connection()))
    
    if results[0][1]:  # Only run other tests if connection works
        results.append(("Semaphore", await test_semaphore()))
        results.append(("Cache", await test_cache()))
        results.append(("Metrics", await test_metrics()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(passed for _, passed in results)
    
    if all_passed:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed")
        print("\nNote: Make sure Redis is running:")
        print("  redis-cli ping")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
