#!/usr/bin/env python3
"""
Update services.yaml to match actual Sentry projects from DSN mapping

This script ensures sentry_service_name matches the actual project names
in Sentry (from sentry_dsn_mapping.json). If no match exists, it removes
the sentry_service_name field.
"""

import yaml
import json
import sys
from pathlib import Path
from typing import Dict, Set

def load_services_config(config_path: Path) -> dict:
    """Load services.yaml"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def save_services_config(config_path: Path, data: dict):
    """Save services.yaml"""
    with open(config_path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

def load_dsn_mapping(mapping_path: Path) -> Set[str]:
    """Load DSN mapping and return set of project names"""
    with open(mapping_path, 'r') as f:
        mapping = json.load(f)
    
    # Filter out metadata fields (start with _)
    projects = {k for k in mapping.keys() if not k.startswith('_')}
    return projects

def find_matching_project(service_name: str, sentry_projects: Set[str]) -> str:
    """
    Try to find a matching Sentry project for a service
    
    Tries multiple strategies:
    1. Exact match
    2. Match after removing locale prefixes (hub-ca-, hub-us-, edr-na-, etc.)
    3. Match with -service suffix variations
    """
    # Strategy 1: Exact match
    if service_name in sentry_projects:
        return service_name
    
    # Strategy 2: Remove locale prefixes
    prefixes = ['hub-ca-', 'hub-us-', 'hub-na-', 'edr-na-', 'edrtier3-na-', 'hub-']
    clean_name = service_name
    for prefix in prefixes:
        if service_name.startswith(prefix):
            clean_name = service_name[len(prefix):]
            if clean_name in sentry_projects:
                return clean_name
            break
    
    # Strategy 3: Try with/without -service suffix
    for candidate in [clean_name, service_name]:
        # Try adding -service
        if f"{candidate}-service" in sentry_projects:
            return f"{candidate}-service"
        
        # Try removing -service
        if candidate.endswith('-service'):
            base = candidate[:-8]
            if base in sentry_projects:
                return base
    
    # Strategy 4: Check if clean name matches any project
    for project in sentry_projects:
        # Check if service name contains project name or vice versa
        if clean_name in project or project in clean_name:
            return project
    
    return None

def sync_sentry_names(config_path: Path, mapping_path: Path, dry_run: bool = False):
    """Update sentry_service_name to match actual Sentry projects"""
    
    # Load data
    config = load_services_config(config_path)
    sentry_projects = load_dsn_mapping(mapping_path)
    services = config.get('services', [])
    
    print("=" * 80)
    print("SYNC SENTRY SERVICE NAMES")
    print("=" * 80)
    print(f"Available Sentry projects: {len(sentry_projects)}")
    print(f"Services to process: {len(services)}")
    print()
    
    # Statistics
    stats = {
        'total': len(services),
        'matched': 0,
        'removed': 0,
        'unchanged': 0,
        'updated': 0
    }
    
    # Process each service
    for service in services:
        service_name = service.get('name')
        current_sentry_name = service.get('sentry_service_name')
        
        # Try to find matching Sentry project
        matched_project = find_matching_project(service_name, sentry_projects)
        
        if matched_project:
            # Found a match
            if current_sentry_name == matched_project:
                # Already correct
                print(f"✓ {service_name}: {matched_project} (unchanged)")
                stats['unchanged'] += 1
            elif current_sentry_name:
                # Update existing
                print(f"🔄 {service_name}: {current_sentry_name} → {matched_project}")
                service['sentry_service_name'] = matched_project
                stats['updated'] += 1
            else:
                # Add new
                print(f"✅ {service_name}: → {matched_project} (new)")
                service['sentry_service_name'] = matched_project
                stats['matched'] += 1
        else:
            # No match found
            if current_sentry_name:
                # Remove invalid mapping
                print(f"❌ {service_name}: {current_sentry_name} → (removed - no Sentry project)")
                del service['sentry_service_name']
                # Also remove DSN if exists
                if 'sentry_dsn' in service:
                    del service['sentry_dsn']
                stats['removed'] += 1
            else:
                # No mapping, leave as-is
                print(f"⏭️  {service_name}: (no Sentry project)")
                stats['unchanged'] += 1
    
    # Save if not dry run
    if not dry_run:
        save_services_config(config_path, config)
        print("\n✅ Updated config/services.yaml")
    else:
        print("\n🔍 DRY RUN - No changes made")
    
    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total services:          {stats['total']}")
    print(f"Matched to Sentry:       {stats['matched']}")
    print(f"Updated mapping:         {stats['updated']}")
    print(f"Removed (no match):      {stats['removed']}")
    print(f"Unchanged:               {stats['unchanged']}")
    print("=" * 80)
    
    return stats

def show_unmatched_services(config_path: Path, mapping_path: Path):
    """Show services that don't have Sentry projects"""
    config = load_services_config(config_path)
    sentry_projects = load_dsn_mapping(mapping_path)
    services = config.get('services', [])
    
    unmatched = []
    for service in services:
        service_name = service.get('name')
        matched_project = find_matching_project(service_name, sentry_projects)
        if not matched_project:
            unmatched.append(service_name)
    
    if unmatched:
        print("=" * 80)
        print(f"UNMATCHED SERVICES ({len(unmatched)})")
        print("=" * 80)
        print("These services don't have matching Sentry projects:")
        print()
        for name in sorted(unmatched):
            print(f"  • {name}")
        print()
        print("Consider creating Sentry projects for these services or")
        print("check if they should be mapped to existing projects.")
        print("=" * 80)
    else:
        print("✅ All services matched to Sentry projects!")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Sync sentry_service_name with actual Sentry projects')
    parser.add_argument('--dry-run', action='store_true', help='Show changes without saving')
    parser.add_argument('--show-unmatched', action='store_true', help='Show services without Sentry projects')
    parser.add_argument('--mapping', type=str, default='sentry_dsn_mapping.json', help='DSN mapping file')
    
    args = parser.parse_args()
    
    # Determine paths
    script_dir = Path(__file__).parent
    config_path = script_dir.parent / 'config' / 'services.yaml'
    mapping_path = script_dir.parent / args.mapping
    
    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        sys.exit(1)
    
    if not mapping_path.exists():
        print(f"❌ DSN mapping file not found: {mapping_path}")
        print()
        print("Generate it with:")
        print(f"  python scripts/tools/fetch_sentry_dsns.py --output {args.mapping}")
        sys.exit(1)
    
    # Sync names
    stats = sync_sentry_names(config_path, mapping_path, dry_run=args.dry_run)
    
    # Show unmatched if requested
    if args.show_unmatched:
        print()
        show_unmatched_services(config_path, mapping_path)
    
    # Suggest next steps
    if not args.dry_run and (stats['matched'] > 0 or stats['updated'] > 0 or stats['removed'] > 0):
        print()
        print("Next steps:")
        print("  1. Review changes: git diff config/services.yaml")
        print("  2. Apply DSNs: python scripts/tools/add_sentry_dsns.py --mapping sentry_dsn_mapping.json")
        print("  3. Deploy: ./scripts/deploy.sh")

if __name__ == '__main__':
    main()
