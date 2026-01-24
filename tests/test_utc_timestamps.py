#!/usr/bin/env python3
"""
Test UTC timestamp-only search implementation.
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import find_log_files, load_config

def test_utc_timestamp_search():
    """Test find_log_files with UTC datetime objects"""
    config = load_config()
    auth_service = next((s for s in config.services if s.name == "hub-ca-auth"), None)
    
    if not auth_service:
        print("❌ hub-ca-auth service not found in config")
        return
    
    print("=" * 80)
    print("UTC TIMESTAMP TEST")
    print("=" * 80)
    print()
    print("Scenario: Sunday 4pm-10pm MST = Sunday 23:00 UTC to Monday 05:00 UTC")
    print("UTC Range: 2026-01-05T23:00:00Z to 2026-01-06T05:00:00Z")
    print()
    
    # Parse timestamps
    from dateutil import parser
    start_dt = parser.isoparse("2026-01-05T23:00:00Z")
    end_dt = parser.isoparse("2026-01-06T05:00:00Z")
    
    print(f"Start: {start_dt}")
    print(f"End: {end_dt}")
    print()
    
    # Call find_log_files
    files = find_log_files(
        auth_service,
        start_hour=start_dt,  # Historical parameter name
        end_hour=end_dt
    )
    
    print(f"Files found: {len(files)}")
    
    if len(files) > 0:
        print("✅ SUCCESS! UTC timestamps work")
        print()
        
        # Count files by hour
        from collections import defaultdict
        hours = defaultdict(int)
        for f in files:
            parts = f.split('/')
            if len(parts) >= 7:
                date = parts[-4]
                day = parts[-3]
                hour = parts[-2]
                hours[f"{date}/{day}/{hour}"] += 1
        
        print("Files by hour:")
        for key in sorted(hours.keys()):
            print(f"  {key}: {hours[key]} files")
        
        print()
        
        # Verify we have files from both days
        has_jan5 = any("2026/01/05" in f for f in files)
        has_jan6 = any("2026/01/06" in f for f in files)
        
        if has_jan5 and has_jan6:
            print("✅ Confirmed: Files from BOTH Jan 5 and Jan 6")
        elif has_jan5:
            print("⚠️  Only found files from Jan 5")
        elif has_jan6:
            print("⚠️  Only found files from Jan 6")
    else:
        print("❌ FAIL: No files found")
    
    print()

if __name__ == "__main__":
    print()
    test_utc_timestamp_search()
    
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()
    print("✅ Simplified Implementation:")
    print("   - Removed: date, time_range, timezone, hours_back, minutes_back")
    print("   - Kept: start_time_utc, end_time_utc (required)")
    print("   - Agent converts user requests to UTC timestamps")
    print("   - Single code path, no timezone math")
    print()
