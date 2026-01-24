# Per-Service Sentry DSN Configuration Guide

## Overview

The log-ai MCP server now supports **per-service Sentry DSNs**, allowing each service to send errors and performance metrics to its own dedicated Sentry project.

## Why Per-Service DSNs?

Previously, all services shared one Sentry DSN. Now:
- ✅ Each service has its own Sentry project
- ✅ Errors/metrics go directly to the correct team's dashboard
- ✅ Better isolation and project-specific alerting
- ✅ Each team controls their own Sentry configuration

## Configuration Steps

### 1. Generate DSN Mapping Template

```bash
cd /home/ubuntu/elis_temp/github_projects/log-ai
python3 scripts/add_sentry_dsns.py --generate-template sentry_dsn_mapping.json
```

This creates a JSON file with all 55 unique Sentry projects.

### 2. Fill in DSNs from Sentry Dashboard

For each project, get the DSN from Sentry:

1. Go to: `https://sentry.example.com/settings/{ORG}/projects/<project>/keys/`
2. Copy the DSN (format: `https://<key>@sentry.example.com/<id>`)
3. Add to `sentry_dsn_mapping.json`

**Example:**
```json
{
  "activity-inference-engine": "https://d66f9d0542840df0ff1bb51ab0d74ed1@sentry.example.com/2",
  "auth-service": "https://abc123@sentry.example.com/4",
  "api-service": "https://def456@sentry.example.com/5"
}
```

### 3. Apply DSN Mappings

Preview changes (dry-run):
```bash
python3 scripts/add_sentry_dsns.py --mapping sentry_dsn_mapping.json --dry-run
```

Apply changes:
```bash
python3 scripts/add_sentry_dsns.py --mapping sentry_dsn_mapping.json
```

### 4. Deploy to Production

```bash
./scripts/deploy.sh
```

## Alternative: Interactive Mode

Configure DSNs one-by-one interactively:

```bash
python3 scripts/add_sentry_dsns.py --interactive
```

This will prompt you for each service's DSN.

## How It Works

### Service Configuration

Each service in `config/services.yaml` now has two Sentry fields:

```yaml
- name: hub-ca-auth
  type: json
  description: Hub CA Auth Service logs
  path_pattern: /syslog/application_logs/{YYYY}/{MM}/{DD}/{HH}/hub-ca-auth-kinesis-*
  path_date_formats: ["{YYYY}", "{MM}", "{DD}", "{HH}"]
  sentry_service_name: auth-service  # Sentry project name
  sentry_dsn: https://abc@sentry.example.com/4  # Project-specific DSN
```

### Locale-Aware Mapping

Multiple log services can share one Sentry project:

```yaml
# Both hub-ca-auth and hub-us-auth send to auth-service project
- name: hub-ca-auth
  sentry_service_name: auth-service
  sentry_dsn: https://abc@sentry.example.com/4

- name: hub-us-auth
  sentry_service_name: auth-service
  sentry_dsn: https://abc@sentry.example.com/4  # Same DSN
```

### Error Routing

When a search error occurs:
1. MCP server looks up the service configuration
2. Gets the `sentry_dsn` for that service
3. Temporarily initializes Sentry with that DSN
4. Sends error to the service's Sentry project
5. Flushes and ready for next service

## Verification

After deployment, verify errors appear in correct Sentry projects:

1. Trigger a search error for a specific service
2. Check that service's Sentry project dashboard
3. Verify error appears with correct tags:
   - `service`: Sentry project name
   - `log_ai_service`: Original service name
   - Environment, duration, etc.

## Script Reference

### add_sentry_dsns.py

**Generate template:**
```bash
python3 scripts/add_sentry_dsns.py --generate-template <output.json>
```

**Apply from mapping file:**
```bash
python3 scripts/add_sentry_dsns.py --mapping <mapping.json> [--dry-run]
```

**Interactive mode:**
```bash
python3 scripts/add_sentry_dsns.py --interactive
```

## Configuration Fields

| Field | Required | Description |
|-------|----------|-------------|
| `sentry_service_name` | Optional | Sentry project name (for locale mapping) |
| `sentry_dsn` | Optional | Per-service Sentry DSN |

**Behavior:**
- If `sentry_dsn` is **not configured**: Sentry disabled for that service
- If `sentry_dsn` is **configured**: Errors/metrics sent to that Sentry project

## Example Mapping File

```json
{
  "_comment": "Get DSNs from: https://sentry.example.com/settings/{ORG}/projects/<project>/keys/",
  
  "software-updater-service": "https://key1@sentry.example.com/1",
  "rig-info-service": "https://key2@sentry.example.com/2",
  "aie-service": "https://key3@sentry.example.com/3",
  "api-service": "https://key4@sentry.example.com/4",
  "auth-service": "https://key5@sentry.example.com/5"
}
```

## Troubleshooting

### "Invalid DSN format"

DSN must contain `@` symbol:
- ✅ `https://abc@sentry.example.com/4`
- ❌ `https://sentry.example.com/`

### "No DSN mapping for service"

Either:
1. Service missing from mapping file
2. `sentry_service_name` doesn't match mapping key

Check: mapping uses `sentry_service_name` (not `name`)

### Errors not appearing in Sentry

1. Verify `sentry_dsn` is configured for that service
2. Check DSN is valid (test in browser)
3. Check Sentry project exists: `https://sentry.example.com/organizations/{ORG}/projects/`
4. Verify environment filter: set to `qa` by default

## Migration from Global DSN

Old way (single DSN for all services):
```bash
SENTRY_DSN=https://key@sentry.example.com/1
```

New way (per-service DSNs in services.yaml):
```yaml
services:
  - name: my-service
    sentry_dsn: https://key@sentry.example.com/1
```

The global `SENTRY_DSN` in `.env` is no longer used. Each service needs its own DSN.

## Next Steps

1. ✅ Generate template: `--generate-template`
2. ✅ Fill in DSNs from Sentry dashboard
3. ✅ Apply mappings: `--mapping`
4. ✅ Deploy: `./scripts/deploy.sh`
5. ✅ Test with actual searches
6. ✅ Verify errors in Sentry project dashboards
