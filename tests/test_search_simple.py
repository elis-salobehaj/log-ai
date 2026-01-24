#!/usr/bin/env python3
"""
Test search_logs with UTC timestamps
"""

import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import load_config, find_log_files
from dateutil import parser as date_parser

def test_search_params():
    """Test the exact parameters from user"""
    
    params = {
        "service_name": "hub-ca-auth",
        "query": "TimedRequestLog",
        "start_time_utc": "2026-01-07T15:20:00Z",
        "end_time_utc": "2026-01-07T15:30:00Z"
    }
    
    print("=" * 80)
    print("Testing search_logs with parameters:")
    print(json.dumps(params, indent=2))
    print("=" * 80)
    print()
    
    # Load config
    config = load_config()
    auth_service = next((s for s in config.services if s.name == "hub-ca-auth"), None)
    
    if not auth_service:
        print("❌ hub-ca-auth service not found")
        return
    
    # Parse timestamps
    try:
        start_dt = date_parser.isoparse(params["start_time_utc"])
        end_dt = date_parser.isoparse(params["end_time_utc"])
        
        print(f"Parsed start: {start_dt}")
        print(f"Parsed end: {end_dt}")
        print()
        
        # Find files
        files = find_log_files(auth_service, start_hour=start_dt, end_hour=end_dt)
        
        print(f"Files found: {len(files)}")
        
        if len(files) > 0:
            print("✅ File discovery works")
            print()
            print("Sample files:")
            for f in files[:3]:
                print(f"  {f}")
            print()
            
            # Test cache key generation (the part that was breaking)
            time_range = {
                "start_datetime": start_dt,
                "end_datetime": end_dt
            }
            
            print("Testing cache key generation...")
            try:
                # Convert datetime objects to ISO strings for JSON serialization
                time_range_serializable = {}
                for key, value in time_range.items():
                    if hasattr(value, 'isoformat'):  # datetime object
                        time_range_serializable[key] = value.isoformat()
                    else:
                        time_range_serializable[key] = value
                
                cache_test = json.dumps(time_range_serializable, sort_keys=True)
                print(f"✅ Cache key generation works: {cache_test[:80]}...")
            except Exception as e:
                print(f"❌ Cache key generation failed: {e}")
            
        else:
            print("⚠️  No files found for this time range")
            print("This might be expected if no logs exist for Jan 7, 15:20-15:30 UTC")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_search_params()
