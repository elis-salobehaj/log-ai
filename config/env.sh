#!/bin/bash
# Environment configuration script for LogAI MCP Server
# Source this file to load configuration: source config/env.sh

# Redis Configuration
export REDIS_HOST=localhost
export REDIS_PORT=6379
export REDIS_DB=0
export REDIS_MAX_MEMORY=500mb
export REDIS_PERSISTENCE=false
export REDIS_ENABLED=true

# Global Limits
export MAX_GLOBAL_SEARCHES=20
export MAX_PARALLEL_SEARCHES_PER_CALL=5

# Cache Configuration
export CACHE_MAX_SIZE_MB=500
export CACHE_MAX_ENTRIES=100
export CACHE_TTL_MINUTES=10

# Search Limits
export AUTO_CANCEL_TIMEOUT_SECONDS=300
export MAX_IN_MEMORY_MATCHES=1000

# File Output
export FILE_RETENTION_HOURS=24
export CLEANUP_INTERVAL_HOURS=1

# Logging
export LOG_LEVEL=INFO
export LOG_FORMAT=text

# Sentry Configuration (Chunk 2)
# export SENTRY_DSN='https://xxx@yyy.ingest.sentry.io/zzz'
# export SENTRY_TRACES_SAMPLE_RATE=1.0
# export SENTRY_PROFILES_SAMPLE_RATE=0.1
# export SENTRY_ALERT_TEAMS_WEBHOOK='https://outlook.office.com/webhook/...'
# export SENTRY_ALERT_SLACK_WEBHOOK='https://hooks.slack.com/services/...'

# Datadog Configuration (Chunk 3)
# export DD_API_KEY='your-api-key'
# export DD_APP_KEY='your-app-key'
# export DD_SITE='datadoghq.com'

echo "✓ LogAI environment configuration loaded"
echo "  Redis: ${REDIS_HOST}:${REDIS_PORT} (enabled=${REDIS_ENABLED})"
echo "  Max Global Searches: ${MAX_GLOBAL_SEARCHES}"
echo "  Cache: ${CACHE_MAX_SIZE_MB}MB, ${CACHE_TTL_MINUTES}min TTL"
