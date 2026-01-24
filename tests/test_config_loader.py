"""
Test configuration loader
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from config_loader import get_config

def test_config_defaults():
    """Test that config loads with defaults"""
    config = get_config()
    
    print("Configuration Test")
    print("=" * 60)
    print(config)
    print()
    
    # Verify defaults
    assert config.redis_host == "localhost"
    assert config.redis_port == 6379
    assert config.max_global_searches == 20
    assert config.cache_max_size_mb == 500
    assert config.redis_enabled is True
    
    print("✓ All default values loaded correctly")
    print()
    
    # Test environment variable override
    os.environ["MAX_GLOBAL_SEARCHES"] = "50"
    os.environ["REDIS_HOST"] = "redis.example.com"
    
    from config_loader import reload_config
    config = reload_config()
    
    assert config.max_global_searches == 50
    assert config.redis_host == "redis.example.com"
    
    print("✓ Environment variable overrides working")
    print(f"  max_global_searches: 20 → {config.max_global_searches}")
    print(f"  redis_host: localhost → {config.redis_host}")
    print()
    
    # Cleanup
    del os.environ["MAX_GLOBAL_SEARCHES"]
    del os.environ["REDIS_HOST"]
    
    print("✓ Configuration loader test passed!")

if __name__ == "__main__":
    test_config_defaults()
