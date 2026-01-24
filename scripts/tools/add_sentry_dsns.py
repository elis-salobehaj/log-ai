#!/usr/bin/env python3
"""
Add Sentry DSNs to services configuration

This script helps you add per-service Sentry DSNs to your services.yaml file.
Each service can have its own Sentry project with its own DSN.

Example Sentry project structure:
- activity-inference-engine → https://key1@sentry.{ORG_DOMAIN}/2
- auth-service → https://key2@sentry.{ORG_DOMAIN}/4
- api-service → https://key3@sentry.{ORG_DOMAIN}/5

Usage:
  1. Get DSNs from Sentry dashboard:
     https://sentry.{ORG_DOMAIN}/settings/{org}/projects/{project}/keys/
  
  2. Create a JSON mapping file with DSNs:
     {
       "activity-inference-engine": "https://key@sentry.{ORG_DOMAIN}/2",
       "auth-service": "https://key@sentry.{ORG_DOMAIN}/4"
     }
  
  3. Run this script:
     python scripts/tools/add_sentry_dsns.py --mapping dsn_mapping.json
  
  Or use interactive mode:
     python scripts/tools/add_sentry_dsns.py --interactive
"""

import yaml
import json
import sys
from pathlib import Path
from typing import Dict

# Add src directory to Python path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))
from config_loader import get_config

# Load configuration from .env
config = get_config()

def load_services_config(config_path: Path) -> dict:
    """Load services.yaml"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def save_services_config(config_path: Path, data: dict):
    """Save services.yaml"""
    with open(config_path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

def add_dsns_from_mapping(config_path: Path, mapping: Dict[str, str], dry_run: bool = False):
    """
    Add Sentry DSNs to services based on mapping
    
    Mapping format:
    {
      "sentry_project_name": "https://key@host/id",
      "auth-service": "https://key@sentry.example.com/4"
    }
    """
    # Load config
    config = load_services_config(config_path)
    services = config.get('services', [])
    
    # Statistics
    stats = {
        'total': len(services),
        'updated': 0,
        'skipped': 0,
        'missing_mapping': 0
    }
    
    # Process each service
    for service in services:
        service_name = service.get('name')
        sentry_project = service.get('sentry_service_name')
        
        if not sentry_project:
            print(f"⚠️  {service_name}: No sentry_service_name configured, skipping")
            stats['skipped'] += 1
            continue
        
        # Look up DSN in mapping
        if sentry_project in mapping:
            dsn = mapping[sentry_project]
            
            # Validate DSN format
            if '@' not in dsn or 'sentry' not in dsn:
                print(f"❌ {service_name}: Invalid DSN format for {sentry_project}")
                stats['skipped'] += 1
                continue
            
            # Add or update DSN
            old_dsn = service.get('sentry_dsn')
            if old_dsn != dsn:
                service['sentry_dsn'] = dsn
                status = "UPDATED" if old_dsn else "ADDED"
                print(f"✅ {service_name} ({sentry_project}): {status}")
                stats['updated'] += 1
            else:
                print(f"⏭️  {service_name}: Already has correct DSN")
                stats['skipped'] += 1
        else:
            print(f"⚠️  {service_name}: No DSN mapping for {sentry_project}")
            stats['missing_mapping'] += 1
    
    # Save if not dry run
    if not dry_run:
        save_services_config(config_path, config)
        print("\n✅ Updated config/services.yaml")
    else:
        print("\n🔍 DRY RUN - No changes made")
    
    # Print statistics
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total services:        {stats['total']}")
    print(f"DSNs added/updated:    {stats['updated']}")
    print(f"Skipped (no change):   {stats['skipped']}")
    print(f"Missing mapping:       {stats['missing_mapping']}")
    print("=" * 60)

def interactive_mode(config_path: Path):
    """Interactive mode to add DSNs one by one"""
    services_config = load_services_config(config_path)
    services = services_config.get('services', [])
    
    print("=" * 60)
    print("INTERACTIVE DSN CONFIGURATION")
    print("=" * 60)
    print("For each service, enter the Sentry DSN or press Enter to skip.")
    print(f"Format: https://<key>@sentry.{config.org_domain}/<project_id>")
    print("Type 'quit' to exit.\n")
    
    updated = 0
    for service in services:
        service_name = service.get('name')
        sentry_project = service.get('sentry_service_name')
        current_dsn = service.get('sentry_dsn')
        
        if not sentry_project:
            continue
        
        print(f"\nService: {service_name}")
        print(f"Sentry project: {sentry_project}")
        if current_dsn:
            print(f"Current DSN: {current_dsn[:50]}...")
        
        dsn = input(f"Enter DSN (or Enter to skip): ").strip()
        
        if dsn.lower() == 'quit':
            break
        
        if dsn:
            if '@' not in dsn:
                print("❌ Invalid DSN format (missing @ symbol)")
                continue
            
            service['sentry_dsn'] = dsn
            updated += 1
            print(f"✅ Updated")
    
    if updated > 0:
        save_services_config(config_path, services_config)
        print(f"\n✅ Updated {updated} services in config/services.yaml")
    else:
        print("\n⏭️  No changes made")

def generate_template_mapping(config_path: Path, output_file: Path):
    """
    Generate a template mapping file with all Sentry projects
    
    You can fill in the DSNs and use it with --mapping
    """
    services_config = load_services_config(config_path)
    services = services_config.get('services', [])
    
    # Get unique Sentry projects
    projects = {}
    for service in services:
        sentry_project = service.get('sentry_service_name')
        if sentry_project and sentry_project not in projects:
            projects[sentry_project] = f"https://<key>@sentry.{config.org_domain}/<project_id> # TODO: Fill in from Sentry dashboard"
    
    # Add example
    example = {
        "_example_activity-inference-engine": f"https://key@sentry.{config.org_domain}/2",
        "_comment": f"Get DSNs from: https://sentry.{config.org_domain}/settings/{config.org_name}/projects/<project>/keys/"
    }
    
    template = {**example, **projects}
    
    with open(output_file, 'w') as f:
        json.dump(template, f, indent=2)
    
    print(f"✅ Template generated: {output_file}")
    print(f"📝 Found {len(projects)} unique Sentry projects")
    print(f"\nNext steps:")
    print(f"  1. Edit {output_file} and fill in real DSNs")
    print(f"  2. Run: python scripts/tools/add_sentry_dsns.py --mapping {output_file}")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Add Sentry DSNs to services configuration')
    parser.add_argument('--mapping', type=str, help='JSON file with DSN mappings')
    parser.add_argument('--interactive', action='store_true', help='Interactive mode')
    parser.add_argument('--dry-run', action='store_true', help='Show changes without saving')
    parser.add_argument('--generate-template', type=str, help='Generate template mapping file')
    
    args = parser.parse_args()
    
    # Determine config path (go up two levels from scripts/tools/)
    script_dir = Path(__file__).parent
    config_path = script_dir.parent.parent / 'config' / 'services.yaml'
    
    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        sys.exit(1)
    
    if args.generate_template:
        output_file = Path(args.generate_template)
        generate_template_mapping(config_path, output_file)
    elif args.interactive:
        interactive_mode(config_path)
    elif args.mapping:
        mapping_file = Path(args.mapping)
        if not mapping_file.exists():
            print(f"❌ Mapping file not found: {mapping_file}")
            sys.exit(1)
        
        with open(mapping_file, 'r') as f:
            mapping = json.load(f)
        
        # Remove example entries
        mapping = {k: v for k, v in mapping.items() if not k.startswith('_')}
        
        add_dsns_from_mapping(config_path, mapping, dry_run=args.dry_run)
    else:
        parser.print_help()
        print("\n💡 Quick start:")
        print("  1. Generate template: python scripts/tools/add_sentry_dsns.py --generate-template dsn_mapping.json")
        print("  2. Fill in DSNs in dsn_mapping.json")
        print("  3. Apply: python scripts/tools/add_sentry_dsns.py --mapping dsn_mapping.json")

if __name__ == '__main__':
    main()
