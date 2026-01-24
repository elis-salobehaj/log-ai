#!/usr/bin/env python3
"""
Fetch Sentry DSNs automatically using Sentry API

This script uses the Sentry API to retrieve DSN keys for all projects,
eliminating the need to manually copy them from the dashboard.

Requirements:
  - SENTRY_AUTH_TOKEN environment variable must be set
  - Token must have 'project:read' permission

Usage:
  python scripts/tools/fetch_sentry_dsns.py --output sentry_dsn_mapping.json
  python scripts/tools/fetch_sentry_dsns.py --output sentry_dsn_mapping.json --apply
"""

import os
import sys
import json
import requests
from pathlib import Path
from typing import Dict, List

# Load environment from config/.env if available
def load_env():
    """Load environment variables from config/.env"""
    script_dir = Path(__file__).parent
    # Script is in scripts/tools/, so go up two levels to project root
    project_root = script_dir.parent.parent
    env_file = project_root / 'config' / '.env'
    
    print(f"🔍 Looking for .env file at: {env_file}")
    
    if env_file.exists():
        print(f"✅ Loading environment from: {env_file}")
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    # Remove 'export ' prefix if present
                    if line.startswith('export '):
                        line = line[7:]
                    
                    key, value = line.split('=', 1)
                    # Remove quotes if present
                    value = value.strip('"').strip("'")
                    os.environ[key] = value
    else:
        print(f"⚠️  .env file not found at: {env_file}")

# Load environment on import
load_env()

class SentryDSNFetcher:
    """Fetch DSNs from Sentry API"""
    
    def __init__(self):
        self.base_url = os.environ.get("SENTRY_URL", "").rstrip("/")
        
        # Validate SENTRY_URL is set and not a placeholder
        if not self.base_url or "example.com" in self.base_url:
            print("❌ ERROR: SENTRY_URL environment variable not set or using placeholder")
            print()
            print("Expected a real Sentry URL from config/.env like:")
            print("  SENTRY_URL=https://sentry.example-org.com")
            print()
            print(f"Current value: {self.base_url or 'NOT SET'}")
            sys.exit(1)
        
        if not self.base_url.startswith("http"):
            self.base_url = "https://" + self.base_url
        
        # Extract base URL if it's a full DSN
        if "@" in self.base_url:
            parts = self.base_url.split("@")
            if len(parts) > 1:
                self.base_url = "https://" + parts[1].split("/")[0]
        
        self.org = os.environ.get("ORG_NAME", "")
        
        # Validate ORG_NAME is set and not a placeholder
        if not self.org or "example" in self.org.lower():
            print("❌ ERROR: ORG_NAME environment variable not set or using placeholder")
            print()
            print("Expected a real organization name from config/.env like:")
            print("  ORG_NAME=example-org")
            print()
            print(f"Current value: {self.org or 'NOT SET'}")
            sys.exit(1)
        
        self.auth_token = os.environ.get("SENTRY_AUTH_TOKEN")
        
        if not self.auth_token:
            print("❌ ERROR: SENTRY_AUTH_TOKEN environment variable not set")
            print()
            print("Get your auth token from:")
            print(f"  {self.base_url}/settings/account/api/auth-tokens/")
            print()
            print("Add it to config/.env:")
            print("  SENTRY_AUTH_TOKEN=your-token")
            sys.exit(1)
    
    def _headers(self) -> Dict[str, str]:
        """Get API request headers"""
        return {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json"
        }
    
    def fetch_projects(self) -> List[Dict]:
        """Fetch all projects in the organization"""
        url = f"{self.base_url}/api/0/organizations/{self.org}/projects/"
        
        try:
            print(f"🔍 Fetching projects from {self.org}...")
            response = requests.get(url, headers=self._headers(), timeout=30)
            response.raise_for_status()
            
            projects = response.json()
            print(f"✅ Found {len(projects)} projects")
            return projects
            
        except requests.RequestException as e:
            print(f"❌ Failed to fetch projects: {e}")
            sys.exit(1)
    
    def fetch_project_keys(self, project_slug: str) -> List[Dict]:
        """Fetch DSN keys for a specific project"""
        url = f"{self.base_url}/api/0/projects/{self.org}/{project_slug}/keys/"
        
        try:
            response = requests.get(url, headers=self._headers(), timeout=10)
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            print(f"  ⚠️  Failed to fetch keys for {project_slug}: {e}")
            return []
    
    def fetch_all_dsns(self) -> Dict[str, str]:
        """Fetch DSNs for all projects"""
        projects = self.fetch_projects()
        dsn_mapping = {}
        
        print()
        print("🔑 Fetching DSN keys for each project...")
        print("-" * 80)
        
        for project in projects:
            project_slug = project.get("slug")
            project_name = project.get("name")
            
            # Fetch keys for this project
            keys = self.fetch_project_keys(project_slug)
            
            if keys:
                # Use the first (default) key
                dsn = keys[0].get("dsn", {}).get("public")
                
                if dsn:
                    dsn_mapping[project_slug] = dsn
                    print(f"  ✅ {project_slug}: {dsn[:40]}...")
                else:
                    print(f"  ⚠️  {project_slug}: No public DSN found")
            else:
                print(f"  ⚠️  {project_slug}: No keys configured")
        
        print("-" * 80)
        print(f"✅ Retrieved {len(dsn_mapping)} DSNs")
        print()
        
        return dsn_mapping
    
    def save_mapping(self, dsn_mapping: Dict[str, str], output_file: Path):
        """Save DSN mapping to JSON file"""
        # Add helpful comments
        output = {
            "_comment": "Auto-generated by fetch_sentry_dsns.py",
            "_source": f"{self.base_url}/organizations/{self.org}/projects/",
            "_timestamp": None,  # Will be added below
            **dsn_mapping
        }
        
        # Add timestamp
        from datetime import datetime
        output["_timestamp"] = datetime.now().isoformat()
        
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)
        
        print(f"💾 Saved DSN mapping to: {output_file}")
        print()

def apply_dsns_to_services(mapping_file: Path):
    """Apply DSN mapping to services.yaml"""
    print("=" * 80)
    print("APPLYING DSNs TO SERVICES")
    print("=" * 80)
    print()
    
    # Import the existing script
    script_dir = Path(__file__).parent
    sys.path.insert(0, str(script_dir))
    
    # Use the add_sentry_dsns script
    import subprocess
    result = subprocess.run(
        ["python3", str(script_dir / "add_sentry_dsns.py"), "--mapping", str(mapping_file)],
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    
    return result.returncode == 0

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Fetch Sentry DSNs automatically from Sentry API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch DSNs and save to file
  python scripts/tools/fetch_sentry_dsns.py --output sentry_dsn_mapping.json
  
  # Fetch and automatically apply to services.yaml
  python scripts/tools/fetch_sentry_dsns.py --output sentry_dsn_mapping.json --apply
  
  # Dry-run: see what would be fetched without saving
  python scripts/tools/fetch_sentry_dsns.py --dry-run

Requirements:
  Set SENTRY_AUTH_TOKEN environment variable with a token that has 'project:read' permission.
  Get token from: https://sentry.{ORG_DOMAIN}/settings/account/api/auth-tokens/
        """
    )
    
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='sentry_dsn_mapping.json',
        help='Output JSON file for DSN mapping (default: sentry_dsn_mapping.json)'
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Automatically apply DSNs to services.yaml after fetching'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be fetched without saving'
    )
    parser.add_argument(
        '--project',
        type=str,
        help='Fetch DSN for a specific project only'
    )
    
    args = parser.parse_args()
    
    # Initialize fetcher
    fetcher = SentryDSNFetcher()
    
    print("=" * 80)
    print("SENTRY DSN FETCHER")
    print("=" * 80)
    print(f"Organization: {fetcher.org}")
    print(f"Sentry URL:   {fetcher.base_url}")
    print(f"Auth token:   {fetcher.auth_token[:20]}..." if fetcher.auth_token else "Not set")
    print("=" * 80)
    print()
    
    # Fetch DSNs
    if args.project:
        # Fetch single project
        print(f"🔍 Fetching DSN for project: {args.project}")
        keys = fetcher.fetch_project_keys(args.project)
        
        if keys:
            dsn = keys[0].get("dsn", {}).get("public")
            if dsn:
                print(f"✅ DSN: {dsn}")
                dsn_mapping = {args.project: dsn}
            else:
                print("❌ No public DSN found")
                sys.exit(1)
        else:
            print("❌ No keys found for project")
            sys.exit(1)
    else:
        # Fetch all projects
        dsn_mapping = fetcher.fetch_all_dsns()
    
    if not dsn_mapping:
        print("❌ No DSNs retrieved")
        sys.exit(1)
    
    # Save or show results
    output_file = Path(args.output)
    
    if args.dry_run:
        print("=" * 80)
        print("DRY RUN - Would save the following:")
        print("=" * 80)
        print(json.dumps(dsn_mapping, indent=2))
        print()
        print(f"💡 Run without --dry-run to save to {output_file}")
    else:
        # Save mapping
        fetcher.save_mapping(dsn_mapping, output_file)
        
        # Apply if requested
        if args.apply:
            success = apply_dsns_to_services(output_file)
            if success:
                print()
                print("=" * 80)
                print("✅ SUCCESS!")
                print("=" * 80)
                print("Next steps:")
                print("  1. Review changes: git diff config/services.yaml")
                print("  2. Deploy: ./scripts/deploy.sh")
                print("=" * 80)
            else:
                print()
                print("❌ Failed to apply DSNs to services.yaml")
                sys.exit(1)
        else:
            print("Next steps:")
            print(f"  1. Review: cat {output_file}")
            print(f"  2. Apply:  python scripts/add_sentry_dsns.py --mapping {output_file}")
            print(f"  3. Deploy: ./scripts/deploy.sh")

if __name__ == '__main__':
    main()
