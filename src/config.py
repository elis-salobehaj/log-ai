import yaml
import glob
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel
import os

class ServiceConfig(BaseModel):
    name: str
    type: str
    description: str
    path_pattern: str
    path_date_formats: Optional[List[str]] = None

class AppConfig(BaseModel):
    services: List[ServiceConfig]

def load_config(config_path: str = None) -> AppConfig:
    if config_path is None:
        # Default to ../config/services.yaml relative to this file
        base_dir = Path(__file__).parent.parent
        config_path = base_dir / "config" / "services.yaml"
    
    with open(config_path, "r") as f:
        data = yaml.safe_load(f)
    
    return AppConfig(**data)

def expand_pattern(pattern: str, date: datetime = None, hour: int = None) -> str:
    """
    Expands {YYYY}, {MM}, {DD}, {HH} placeholders in the pattern.
    If no date is provided, defaults to today.
    If no hour is provided, uses wildcard to match all hours.
    """
    if date is None:
        date = datetime.now()
    
    # For hour, if not specified, use wildcard to match all hours of the day
    hour_str = f"{hour:02d}" if hour is not None else "*"
    
    return pattern.format(
        YYYY=date.strftime("%Y"),
        MM=date.strftime("%m"),
        DD=date.strftime("%d"),
        HH=hour_str,
        guid="*", # Handle guid placeholder as wildcard if present
    )

def find_log_files(service: ServiceConfig, hours_back: int = None, minutes_back: int = None, specific_date: str = None, start_hour: int = None, end_hour: int = None) -> List[str]:
    """
    Finds log files matching the service pattern.
    
    Args:
        service: Service configuration
        hours_back: Number of hours to search back from now
        minutes_back: Number of minutes to search back from now (for surgical precision)
        specific_date: Specific date in YYYY-MM-DD format (searches all 24 hours)
        start_hour: Start hour (0-23) when combined with specific_date for time range
        end_hour: End hour (0-23) when combined with specific_date for time range
    
    Time range examples:
        - minutes_back=10: Last 10 minutes from now
        - hours_back=2: Last 2 hours from now
        - specific_date="2025-12-14": All of Dec 14, 2025 (00:00-23:59)
        - specific_date="2025-12-14", start_hour=14, end_hour=16: Dec 14, 2-4pm
    
    Avoids expensive full scans by constructing precise paths.
    """
    files = []
    project_root = Path(__file__).parent.parent
    
    # If config doesn't use placeholders, just return the glob (maybe it's a flat file)
    if "{YYYY}" not in service.path_pattern and "{MM}" not in service.path_pattern:
        p = Path(service.path_pattern)
        if not p.is_absolute():
            p = project_root / p
        return glob.glob(str(p), recursive=True)

    # Generate times to check: either specific date with time range, or hours back
    times_to_check = []
    if specific_date:
        # Search a specific date (YYYY-MM-DD format)
        try:
            target_date = datetime.strptime(specific_date, "%Y-%m-%d")
            
            # If start_hour and end_hour specified, search specific hour range
            if start_hour is not None and end_hour is not None:
                # Search each hour in the range (inclusive)
                for hour in range(start_hour, end_hour + 1):
                    hour_dt = target_date.replace(hour=hour)
                    times_to_check.append((hour_dt, True))  # True = specific hour
            else:
                # Search all hours of that day
                times_to_check.append((target_date, False))  # False = all hours
        except ValueError:
            sys.stderr.write(f"[ERROR] Invalid specific_date format: {specific_date}, expected YYYY-MM-DD\n")
            return []
    elif minutes_back is not None and minutes_back > 0:
        # Search specific minutes back from now
        # For minutes, we need to check current hour and possibly previous hour
        now = datetime.now()
        start_time = now - timedelta(minutes=minutes_back)
        
        # Add current hour
        times_to_check.append((now, True))  # True = specific hour
        
        # If minutes_back spans into previous hour(s), add those too
        if start_time.hour != now.hour or start_time.date() != now.date():
            current_check = now
            while current_check > start_time:
                current_check = current_check - timedelta(hours=1)
                if current_check >= start_time:
                    times_to_check.append((current_check, True))
    elif hours_back is not None and hours_back > 0:
        # Search specific hours back from now
        now = datetime.now()
        for i in range(hours_back):
            times_to_check.append((now - timedelta(hours=i), True))  # True = specific hour
    else:
        # Default: search today only
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        times_to_check.append((today, False))  # False = all hours

    for date, specific_hour in times_to_check:
        # Construct pattern for this time period
        if specific_hour:
            # Search only current hour: replace HH with specific hour
            hour_str = date.strftime("%H")
            pattern = service.path_pattern.replace("{YYYY}", date.strftime("%Y")) \
                                          .replace("{MM}", date.strftime("%m")) \
                                          .replace("{DD}", date.strftime("%d")) \
                                          .replace("{HH}", hour_str) \
                                          .replace("{guid}", "*")
        else:
            # Search all hours of this day: use wildcard for HH
            pattern = service.path_pattern.replace("{YYYY}", date.strftime("%Y")) \
                                          .replace("{MM}", date.strftime("%m")) \
                                          .replace("{DD}", date.strftime("%d")) \
                                          .replace("{HH}", "*") \
                                          .replace("{guid}", "*")
        
        # Resolve path
        p = Path(pattern)
        if not p.is_absolute():
            p = project_root / p
            
        # Glob just this time period
        import sys
        sys.stderr.write(f"[DEBUG] Globbing {str(p)}\n")
        sys.stderr.flush()
        day_files = glob.glob(str(p), recursive=True)
        sys.stderr.write(f"[DEBUG] Found {len(day_files)} files\n")
        sys.stderr.flush()
        files.extend(day_files)
        
    return files
