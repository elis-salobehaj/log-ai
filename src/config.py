import yaml
import glob
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel
import os

class InsightRule(BaseModel):
    patterns: List[str]
    recommendation: str
    severity: str

class ServiceConfig(BaseModel):
    name: str
    type: str
    description: str
    path_pattern: str
    path_date_formats: Optional[List[str]] = None
    insight_rules: Optional[List[InsightRule]] = []

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

def expand_pattern(pattern: str, date: datetime = None) -> str:
    """
    Expands {YYYY}, {MM}, {DD} placeholders in the pattern.
    If no date is provided, defaults to today.
    Note: For globbing multiple dates, we might want to replace with '*' 
    but for now let's assume we look for specific dates or use wildcards in the config.
    """
    if date is None:
        date = datetime.now()
    
    return pattern.format(
        YYYY=date.strftime("%Y"),
        MM=date.strftime("%m"),
        DD=date.strftime("%d"),
        guid="*", # Handle guid placeholder as wildcard if present
    )

def find_log_files(service: ServiceConfig, days_back: int = 1) -> List[str]:
    """
    Finds log files matching the service pattern for the last N days.
    Avoids expensive full scans by effectively constructing the path for each day.
    """
    files = []
    # If no date formats specified, falling back to glob all is dangerous for 300GB, 
    # but for POC we might have to if schema isn't robust.
    # We added 'path_date_formats' to config.
    
    project_root = Path(__file__).parent.parent
    
    # Calculate dates to check
    dates_to_check = []
    for i in range(days_back):
        dates_to_check.append(datetime.now() - datetime.timedelta(days=i))
    
    # If config doesn't use placeholders, just return the glob (maybe it's a flat file)
    if "{YYYY}" not in service.path_pattern and "{MM}" not in service.path_pattern:
         # Check if absolute or relative
        p = Path(service.path_pattern)
        if not p.is_absolute():
            p = project_root / p
        return glob.glob(str(p), recursive=True)

    for date in dates_to_check:
        # Construct specific pattern for this date
        pattern = service.path_pattern.replace("{YYYY}", date.strftime("%Y")) \
                                      .replace("{MM}", date.strftime("%m")) \
                                      .replace("{DD}", date.strftime("%d")) \
                                      .replace("{guid}", "*") # Keep guid as wildcard
        
        # Resolve path
        p = Path(pattern)
        if not p.is_absolute():
            p = project_root / p
            
        # Glob just this specific day
        # print(f"DEBUG: Globbing {str(p)}", file=sys.stderr)
        day_files = glob.glob(str(p), recursive=True)
        files.extend(day_files)
        
    return files
