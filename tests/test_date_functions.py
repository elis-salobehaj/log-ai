#!/usr/bin/env python3
"""
Direct test of date parsing functions without MCP protocol overhead
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from datetime import datetime
from zoneinfo import ZoneInfo

# Import the parsing functions from server
from server import parse_date_string, parse_time_range

def test_sunday_parsing():
    """Test parsing 'Sunday' to the correct date"""
    print("\n=== Test 1: Parsing 'Sunday' ===")
    today = datetime.now()
    result = parse_date_string("Sunday")
    
    print(f"Today is: {today.strftime('%Y-%m-%d (%A)')}")
    print(f"Parsed 'Sunday' as: {result}")
    
    # Verify it's actually a Sunday (result is tuple of (start_dt, end_dt))
    if result and isinstance(result, tuple):
        start_dt, end_dt = result
        print(f"Start: {start_dt.strftime('%Y-%m-%d %H:%M')}")
        print(f"End: {end_dt.strftime('%Y-%m-%d %H:%M')}")
        print(f"Day of week: {start_dt.strftime('%A')}")
        assert start_dt.strftime('%A') == 'Sunday', "Result should be a Sunday!"
        print("✓ Successfully parsed to a Sunday")
        return True
    else:
        print("✗ Failed to parse")
        return False

def test_time_range_parsing():
    """Test parsing '2 to 4pm' format"""
    print("\n=== Test 2: Parsing '2 to 4pm' ===")
    
    test_cases = [
        ("2 to 4pm", (14, 16)),
        ("2pm to 4pm", (14, 16)),
        ("14:00 to 16:00", (14, 16)),
        ("2pm-4pm", (14, 16)),
        ("9am to 11am", (9, 11)),
    ]
    
    all_passed = True
    for time_str, expected in test_cases:
        result = parse_time_range(time_str)
        if result == expected:
            print(f"✓ '{time_str}' → {result}")
        else:
            print(f"✗ '{time_str}' → {result} (expected {expected})")
            all_passed = False
    
    return all_passed

def test_timezone_conversion():
    """Test timezone conversion MST to UTC"""
    print("\n=== Test 3: Timezone Conversion (MST → UTC) ===")
    
    # MST is UTC-7 (no daylight saving)
    mst_tz = ZoneInfo("America/Denver")
    utc_tz = ZoneInfo("UTC")
    
    # 2pm MST should be 9pm UTC (21:00)
    test_date = datetime(2025, 12, 15, 14, 0, 0, tzinfo=mst_tz)
    utc_time = test_date.astimezone(utc_tz)
    
    print(f"MST time: {test_date.strftime('%Y-%m-%d %H:%M %Z')}")
    print(f"UTC time: {utc_time.strftime('%Y-%m-%d %H:%M %Z')}")
    
    assert utc_time.hour == 21, f"Expected 21:00 UTC, got {utc_time.hour}:00"
    print("✓ Timezone conversion correct (2pm MST = 9pm UTC)")
    
    return True

def test_specific_date():
    """Test parsing 'Dec 14 2025'"""
    print("\n=== Test 4: Parsing 'Dec 14 2025' ===")
    
    result = parse_date_string("Dec 14 2025")
    expected_date = "2025-12-14"
    
    print(f"Parsed 'Dec 14 2025' as: {result}")
    
    if result and isinstance(result, tuple):
        start_dt, end_dt = result
        result_date = start_dt.strftime("%Y-%m-%d")
        print(f"Date: {result_date}")
        print(f"Time range: {start_dt.strftime('%H:%M')} to {end_dt.strftime('%H:%M')}")
        
        if result_date == expected_date:
            print(f"✓ Correctly parsed as {result_date}")
            return True
        else:
            print(f"✗ Expected {expected_date}, got {result_date}")
            return False
    else:
        print("✗ Failed to parse")
        return False

def main():
    print("=" * 60)
    print("Testing Date Parsing and Timezone Features")
    print("=" * 60)
    
    results = []
    results.append(("Sunday parsing", test_sunday_parsing()))
    results.append(("Time range parsing", test_time_range_parsing()))
    results.append(("Timezone conversion", test_timezone_conversion()))
    results.append(("Specific date parsing", test_specific_date()))
    
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
        return 1

if __name__ == "__main__":
    sys.exit(main())
