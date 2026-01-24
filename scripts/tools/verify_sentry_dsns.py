#!/usr/bin/env python3
"""
Verify Sentry DSN configuration across all services

Shows which services have Sentry DSNs configured and validates the format.
"""

import yaml
import sys
from pathlib import Path
from collections import defaultdict

def load_services(config_path: Path):
    """Load services.yaml"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def verify_dsns(config_path: Path):
    """Verify DSN configuration"""
    config = load_services(config_path)
    services = config.get('services', [])
    
    # Statistics
    stats = {
        'total': len(services),
        'with_dsn': 0,
        'without_dsn': 0,
        'invalid_dsn': 0,
        'valid_dsn': 0
    }
    
    # Group by Sentry project
    by_project = defaultdict(list)
    services_without_dsn = []
    invalid_dsns = []
    
    print("=" * 80)
    print("SENTRY DSN VERIFICATION")
    print("=" * 80)
    print()
    
    # Check each service
    for service in services:
        name = service.get('name')
        sentry_project = service.get('sentry_service_name', 'N/A')
        dsn = service.get('sentry_dsn')
        
        if dsn:
            stats['with_dsn'] += 1
            
            # Validate DSN format
            if '@' in dsn and 'sentry' in dsn:
                stats['valid_dsn'] += 1
                by_project[sentry_project].append(name)
            else:
                stats['invalid_dsn'] += 1
                invalid_dsns.append({
                    'service': name,
                    'project': sentry_project,
                    'dsn': dsn[:50]
                })
        else:
            stats['without_dsn'] += 1
            services_without_dsn.append({
                'service': name,
                'project': sentry_project
            })
    
    # Print services grouped by Sentry project
    if by_project:
        print(f"✅ Services with valid Sentry DSN ({stats['valid_dsn']}):")
        print("-" * 80)
        for project in sorted(by_project.keys()):
            service_names = by_project[project]
            print(f"\n📦 {project} ({len(service_names)} services):")
            for svc in sorted(service_names):
                print(f"   • {svc}")
        print()
    
    # Print services without DSN
    if services_without_dsn:
        print(f"⚠️  Services without Sentry DSN ({stats['without_dsn']}):")
        print("-" * 80)
        for item in services_without_dsn:
            print(f"   • {item['service']}")
            if item['project'] != 'N/A':
                print(f"     Sentry project: {item['project']}")
        print()
    
    # Print invalid DSNs
    if invalid_dsns:
        print(f"❌ Services with invalid DSN format ({stats['invalid_dsn']}):")
        print("-" * 80)
        for item in invalid_dsns:
            print(f"   • {item['service']}")
            print(f"     Sentry project: {item['project']}")
            print(f"     DSN: {item['dsn']}...")
        print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total services:          {stats['total']}")
    print(f"With valid DSN:          {stats['valid_dsn']} ({stats['valid_dsn']/stats['total']*100:.1f}%)")
    print(f"Without DSN:             {stats['without_dsn']} ({stats['without_dsn']/stats['total']*100:.1f}%)")
    if stats['invalid_dsn'] > 0:
        print(f"With invalid DSN:        {stats['invalid_dsn']} ({stats['invalid_dsn']/stats['total']*100:.1f}%)")
    print("=" * 80)
    
    # Sentry project summary
    print()
    print("=" * 80)
    print("SENTRY PROJECT SUMMARY")
    print("=" * 80)
    print(f"Unique Sentry projects:  {len(by_project)}")
    print()
    print("Services per project:")
    for project in sorted(by_project.keys(), key=lambda p: len(by_project[p]), reverse=True):
        count = len(by_project[project])
        print(f"   {count:2d}  {project}")
    print("=" * 80)
    
    # Return status
    return {
        'success': stats['invalid_dsn'] == 0,
        'stats': stats
    }

def show_sample_dsns(config_path: Path, limit: int = 5):
    """Show sample DSNs for verification"""
    config = load_services(config_path)
    services = config.get('services', [])
    
    print()
    print("=" * 80)
    print(f"SAMPLE DSNs (first {limit} services with DSN)")
    print("=" * 80)
    
    count = 0
    for service in services:
        if count >= limit:
            break
        
        dsn = service.get('sentry_dsn')
        if dsn:
            name = service.get('name')
            project = service.get('sentry_service_name', 'N/A')
            
            # Show first 30 and last 20 characters for security
            if len(dsn) > 60:
                dsn_display = dsn[:30] + "..." + dsn[-20:]
            else:
                dsn_display = dsn
            
            print(f"\n{name}")
            print(f"  Project: {project}")
            print(f"  DSN:     {dsn_display}")
            count += 1
    
    print()
    print("=" * 80)

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Verify Sentry DSN configuration')
    parser.add_argument('--show-samples', type=int, metavar='N', help='Show N sample DSNs')
    parser.add_argument('--export-missing', type=str, metavar='FILE', help='Export services without DSN to JSON file')
    
    args = parser.parse_args()
    
    # Determine config path
    script_dir = Path(__file__).parent
    config_path = script_dir.parent / 'config' / 'services.yaml'
    
    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        sys.exit(1)
    
    # Run verification
    result = verify_dsns(config_path)
    
    # Show samples if requested
    if args.show_samples:
        show_sample_dsns(config_path, limit=args.show_samples)
    
    # Export missing if requested
    if args.export_missing:
        config = load_services(config_path)
        services = config.get('services', [])
        missing = [
            {
                'service': s.get('name'),
                'sentry_project': s.get('sentry_service_name')
            }
            for s in services
            if not s.get('sentry_dsn') and s.get('sentry_service_name')
        ]
        
        if missing:
            import json
            output_path = Path(args.export_missing)
            with open(output_path, 'w') as f:
                json.dump(missing, f, indent=2)
            print(f"✅ Exported {len(missing)} services without DSN to {output_path}")
    
    # Exit with appropriate code
    sys.exit(0 if result['success'] else 1)

if __name__ == '__main__':
    main()
