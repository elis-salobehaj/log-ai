#!/usr/bin/env python3
"""
Bulk-add sentry_service_name to services.yaml with smart locale-aware mapping

This script adds the sentry_service_name field to all services in services.yaml.
It uses intelligent mapping to handle locale-specific services:

Examples:
  hub-ca-auth → auth-service  (strips hub-ca- prefix)
  hub-us-auth → auth-service  (strips hub-us- prefix)
  hub-ca-api → api-service
  hub-us-api → api-service
  edr-na-software-updater-service → software-updater-service

Mapping Logic:
  1. Remove locale prefixes: hub-{locale}-, edr-{locale}-, {locale}-
  2. If ends with "-service", keep it
  3. Otherwise append "-service"

Usage:
    python scripts/add_sentry_mapping.py [--dry-run] [--custom-mapping mapping.json]

Options:
    --dry-run: Preview changes without modifying services.yaml
    --custom-mapping FILE: Use custom name mappings from JSON file
        Example mapping.json:
        {
            "hub-ca-auth": "auth-service",
            "hub-us-api": "api-service"
        }
"""

import yaml
import argparse
import json
import re
from pathlib import Path
import sys

def smart_sentry_mapping(service_name: str) -> str:
    """
    Generate Sentry project name from service name using smart locale-aware logic
    
    Examples:
        hub-ca-auth → auth-service
        hub-us-auth → auth-service
        hub-ca-api → api-service
        edr-na-software-updater-service → software-updater-service
        hub-${ORG_NAME}-datastream → ${ORG_NAME}-datastream-service
    
    Args:
        service_name: LogAI service name
    
    Returns:
        Sentry project name
    """
    # Remove locale prefixes
    patterns = [
        r'^hub-ca-',      # hub-ca-auth → auth
        r'^hub-us-',      # hub-us-api → api
        r'^hub-na-',      # hub-na-das → das
        r'^edr-na-',      # edr-na-software-updater-service → software-updater-service
        r'^edrtier3-na-', # edrtier3-na-rig-info-server → rig-info-server
        r'^hub-',         # hub-jms_http_server → jms_http_server
    ]
    
    cleaned_name = service_name
    for pattern in patterns:
        cleaned_name = re.sub(pattern, '', cleaned_name)
    
    # If already ends with -service, keep it
    if cleaned_name.endswith('-service'):
        return cleaned_name
    
    # If ends with -server, replace with -service
    if cleaned_name.endswith('-server'):
        return cleaned_name[:-7] + '-service'
    
    # Otherwise append -service
    return f"{cleaned_name}-service"


def load_services(config_path: Path):
    """Load services.yaml"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def save_services(config_path: Path, data: dict, dry_run: bool = False):
    """Save services.yaml with proper formatting"""
    if dry_run:
        print("\n[DRY RUN] Would write to:", config_path)
        print(yaml.dump(data, default_flow_style=False, sort_keys=False))
        return
    
    with open(config_path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    
    print(f"✅ Updated {config_path}")

def add_sentry_mapping(services_data: dict, custom_mapping: dict = None):
    """
    Add sentry_service_name to each service using smart locale-aware mapping
    
    Args:
        services_data: Parsed services.yaml data
        custom_mapping: Optional dict of {service_name: sentry_project_name}
    
    Returns:
        Tuple of (updated_data, stats)
    """
    if 'services' not in services_data:
        raise ValueError("Invalid services.yaml: missing 'services' key")
    
    stats = {
        'total': 0,
        'added': 0,
        'updated': 0,
        'skipped': 0,
        'custom': 0
    }
    
    for service in services_data['services']:
        stats['total'] += 1
        service_name = service.get('name', '')
        
        # Determine Sentry project name
        if custom_mapping and service_name in custom_mapping:
            # Use custom mapping
            sentry_name = custom_mapping[service_name]
            stats['custom'] += 1
        else:
            # Use smart mapping
            sentry_name = smart_sentry_mapping(service_name)
        
        # Check if already has sentry_service_name
        if 'sentry_service_name' in service:
            if service['sentry_service_name'] != sentry_name:
                # Update if different
                service['sentry_service_name'] = sentry_name
                stats['updated'] += 1
            else:
                stats['skipped'] += 1
        else:
            # Add new field
            service['sentry_service_name'] = sentry_name
            stats['added'] += 1
    
    return services_data, stats

def main():
    parser = argparse.ArgumentParser(
        description='Bulk-add sentry_service_name to services.yaml',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without modifying files'
    )
    parser.add_argument(
        '--custom-mapping',
        type=Path,
        help='JSON file with custom name mappings'
    )
    parser.add_argument(
        '--config',
        type=Path,
        default=Path(__file__).parent.parent / 'config' / 'services.yaml',
        help='Path to services.yaml (default: config/services.yaml)'
    )
    
    args = parser.parse_args()
    
    # Validate config file exists
    if not args.config.exists():
        print(f"❌ Error: {args.config} not found")
        sys.exit(1)
    
    # Load custom mapping if provided
    custom_mapping = None
    if args.custom_mapping:
        if not args.custom_mapping.exists():
            print(f"❌ Error: {args.custom_mapping} not found")
            sys.exit(1)
        
        with open(args.custom_mapping, 'r') as f:
            custom_mapping = json.load(f)
        print(f"📋 Loaded {len(custom_mapping)} custom mappings from {args.custom_mapping}")
    
    # Load services
    print(f"📂 Loading {args.config}...")
    services_data = load_services(args.config)
    
    # Add sentry_service_name
    print("🔄 Adding sentry_service_name fields...")
    updated_data, stats = add_sentry_mapping(services_data, custom_mapping)
    
    # Display stats
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total services:     {stats['total']}")
    print(f"Added mappings:     {stats['added']}")
    print(f"Updated mappings:   {stats['updated']}")
    print(f"Skipped (no change): {stats['skipped']}")
    if custom_mapping:
        print(f"Custom mappings:    {stats['custom']}")
    print("="*60)
    
    # Save
    if args.dry_run:
        print("\n⚠️  DRY RUN MODE - No changes written")
        print("\nExample mappings (locale-aware):")
        examples = {}
        for service in updated_data['services'][:10]:
            svc_name = service['name']
            sentry_name = service.get('sentry_service_name')
            if svc_name != sentry_name:
                examples[svc_name] = sentry_name
        
        for svc, sentry in list(examples.items())[:5]:
            print(f"  {svc:<35} → {sentry}")
        
        if len(examples) > 5:
            print(f"  ... and {len(examples) - 5} more mappings")
    else:
        save_services(args.config, updated_data, dry_run=False)
        print(f"\n✅ Successfully updated {args.config}")
        print("\nNext steps:")
        print("  1. Review changes: git diff config/services.yaml")
        print("  2. Test with: python scripts/test_sentry_integration.py")
        print("  3. Deploy: bash scripts/deploy.sh")

if __name__ == '__main__':
    main()
