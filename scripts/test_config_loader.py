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
    assert config.REDIS_HOST == "localhost"
    assert config.REDIS_PORT == 6379
    assert config.MAX_GLOBAL_SEARCHES == 20
    assert config.CACHE_MAX_SIZE_MB == 500
    assert config.REDIS_ENABLED is True
    
    print("✓ All default values loaded correctly")
    print()
    
    # Test environment variable override
    os.environ["MAX_GLOBAL_SEARCHES"] = "50"
    os.environ["REDIS_HOST"] = "redis.example.com"
    
    from config_loader import reload_config
    config = reload_config()
    
    assert config.MAX_GLOBAL_SEARCHES == 50
    assert config.REDIS_HOST == "redis.example.com"
    
    print("✓ Environment variable overrides working")
    print(f"  MAX_GLOBAL_SEARCHES: 20 → {config.MAX_GLOBAL_SEARCHES}")
    print(f"  REDIS_HOST: localhost → {config.REDIS_HOST}")
    print()
    
    # Cleanup
    del os.environ["MAX_GLOBAL_SEARCHES"]
    del os.environ["REDIS_HOST"]
    
    print("✓ Configuration loader test passed!")

if __name__ == "__main__":
    test_config_defaults()
