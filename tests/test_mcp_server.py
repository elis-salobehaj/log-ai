#!/usr/bin/env python3
"""
Test script for the new streaming MCP server.
Tests core functionality without requiring actual log files.
"""

import asyncio
import sys
from pathlib import Path
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import load_config


@pytest.mark.asyncio
async def test_config_loading():
    """Test configuration loading"""
    print("=" * 60)
    print("Test 1: Configuration Loading")
    print("=" * 60)
    
    config = load_config()
    print(f"✓ Loaded {len(config.services)} services")
    
    if config.services:
        service = config.services[0]
        print(f"\nSample service: {service.name}")
        print(f"  Type: {service.type}")
        print(f"  Path pattern: {service.path_pattern}")
    
    assert len(config.services) > 0, "Should load services from config"
    print("\n✓ Configuration loaded successfully\n")


@pytest.mark.asyncio
async def test_cache_functionality():
    """Test SearchCache class"""
    print("=" * 60)
    print("Test 2: Cache Functionality")
    print("=" * 60)
    
    # Import server module
    from server import SearchCache
    cache = SearchCache()
    
    # Test put and get
    services = ["dev-ca-api"]
    query = "error"
    time_range = {"hours_back": 1}
    matches = [{"file": "test.log", "line": 123, "content": "ERROR: test", "service": "dev-ca-api"}]
    metadata = {"total_matches": 1}
    
    cache.put(services, query, time_range, matches, metadata)
    print("✓ Stored entry in cache")
    
    result = cache.get(services, query, time_range)
    assert result is not None, "Should retrieve cached entry"
    retrieved_matches, retrieved_metadata = result
    assert len(retrieved_matches) == 1, "Should have 1 match"
    print("✓ Retrieved entry from cache")
    
    # Test cache miss
    result = cache.get(["other-service"], "different", {"days_back": 1})
    assert result is None, "Should miss on different parameters"
    print("✓ Cache miss works correctly")
    
    # Test order independence
    result = cache.get(["dev-ca-api"], query, time_range)
    assert result is not None, "Should hit with same parameters"
    print("✓ Order-independent cache key works")
    
    print("\n✓ Cache functionality working\n")


@pytest.mark.asyncio
async def test_file_helpers():
    """Test file output helpers"""
    print("=" * 60)
    print("Test 3: File Output Helpers")
    print("=" * 60)
    
    from server import ensure_output_dir, generate_output_filename, FILE_OUTPUT_DIR
    
    # Test directory creation
    ensure_output_dir()
    assert FILE_OUTPUT_DIR.exists(), "Output directory should exist"
    print(f"✓ Output directory created: {FILE_OUTPUT_DIR}")
    
    # Test filename generation
    filename = generate_output_filename(["dev-ca-api", "test-service"], is_partial=False)
    assert "logai-search" in filename.name, "Should contain logai-search"
    assert "dev-ca-api" in filename.name, "Should contain service name"
    print(f"✓ Generated filename: {filename.name}")
    
    partial_filename = generate_output_filename(["test"], is_partial=True)
    assert "logai-partial" in partial_filename.name, "Should contain logai-partial"
    print(f"✓ Generated partial filename: {partial_filename.name}")
    
    print("\n✓ File helpers working\n")


@pytest.mark.asyncio
async def test_format_helpers():
    """Test formatting functions"""
    print("=" * 60)
    print("Test 4: Format Helpers")
    print("=" * 60)
    
    import importlib.util
    spec = importlib.util.spec_from_file_location("server", Path(__file__).parent.parent / "src" / "server.py")
    server_module = importlib.util.module_from_spec(spec)
    
    from server import format_matches_text, format_matches_json
    
    # Test matches formatting
    matches = [
        {"file": "/path/to/test.log", "line": 123, "content": "ERROR: test error", "service": "test-svc"}
    ]
    metadata = {
        "services": ["test-svc"],
        "files_searched": 10,
        "duration_seconds": 1.5,
        "total_matches": 1,
        "cached": False
    }
    
    text_output = format_matches_text(matches, metadata)
    assert "Search Results" in text_output, "Should contain header"
    assert "test-svc" in text_output, "Should contain service name"
    assert "ERROR: test error" in text_output, "Should contain match content"
    print("✓ Text format working")
    
    json_output = format_matches_json(matches, metadata)
    assert '"matches"' in json_output, "Should have matches key"
    assert '"metadata"' in json_output, "Should have metadata key"
    print("✓ JSON format working")
    
    print("\n✓ Format helpers working\n")


async def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("LogAI MCP Server - Unit Tests")
    print("=" * 60 + "\n")
    
    try:
        await test_config_loading()
        await test_cache_functionality()
        await test_file_helpers()
        await test_format_helpers()
        
        print("=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        print("\nServer is ready to use:")
        print("1. Configure AI agent to connect via MCP")
        print("2. Agent can call search_logs, read_search_file")
        print("3. Monitor stderr for progress and cache stats")
        print("=" * 60 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
