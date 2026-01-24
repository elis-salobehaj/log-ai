#!/usr/bin/env python3
"""
Restore sentry_dsn entries to config/services.yaml based on sentry_dsn_mapping.json
"""

import json
import yaml
from pathlib import Path

def load_dsn_mapping():
    """Load the DSN mapping from JSON file"""
    mapping_file = Path(__file__).parent / "tools" / "sentry_dsn_mapping.json"
    with open(mapping_file, 'r') as f:
        data = json.load(f)
    
    # Remove metadata fields
    return {k: v for k, v in data.items() if not k.startswith('_')}

def restore_dsns():
    """Restore sentry_dsn entries to services.yaml"""
    config_file = Path(__file__).parent.parent / "config" / "services.yaml"
    
    # Load DSN mapping
    dsn_mapping = load_dsn_mapping()
    print(f"Loaded {len(dsn_mapping)} DSN mappings")
    
    # Load services.yaml
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    
    # Track statistics
    services_updated = 0
    services_with_sentry = 0
    
    # Add sentry_dsn to each service that has sentry_service_name
    for service in config.get('services', []):
        if 'sentry_service_name' in service:
            services_with_sentry += 1
            sentry_name = service['sentry_service_name']
            
            if sentry_name in dsn_mapping:
                # Add sentry_dsn right after sentry_service_name
                service['sentry_dsn'] = dsn_mapping[sentry_name]
                services_updated += 1
                print(f"✓ {service['name']:40} -> {sentry_name:30} -> {dsn_mapping[sentry_name]}")
            else:
                print(f"✗ {service['name']:40} -> {sentry_name:30} -> NOT FOUND IN MAPPING")
    
    # Save updated config
    with open(config_file, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, width=120)
    
    print(f"\n{'='*80}")
    print(f"Summary:")
    print(f"  Services with sentry_service_name: {services_with_sentry}")
    print(f"  Services updated with sentry_dsn: {services_updated}")
    print(f"  Config file updated: {config_file}")
    print(f"{'='*80}")
    
    return services_updated

if __name__ == "__main__":
    restore_dsns()
