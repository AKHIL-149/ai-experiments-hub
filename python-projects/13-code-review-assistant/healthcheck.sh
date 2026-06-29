#!/bin/bash
###############################################################################
# Docker Healthcheck Script
#
# This script is used by Docker's HEALTHCHECK instruction to verify that
# the application is running and responding to requests.
#
# Usage:
#   ./healthcheck.sh
#
# Exit codes:
#   0 - Healthy: Application is responding correctly
#   1 - Unhealthy: Application is not responding or returned error
###############################################################################

# Configuration
HOST="${HEALTHCHECK_HOST:-localhost}"
PORT="${HEALTHCHECK_PORT:-8000}"
TIMEOUT="${HEALTHCHECK_TIMEOUT:-5}"
ENDPOINT="${HEALTHCHECK_ENDPOINT:-/health}"

# Full URL for the health endpoint
URL="http://${HOST}:${PORT}${ENDPOINT}"

# Perform health check using curl
# - Silent mode (-s)
# - Fail on HTTP errors (-f)
# - Max time for request (--max-time)
# - Write response to stderr for debugging (--write-out)
RESPONSE=$(curl -sf --max-time "${TIMEOUT}" "${URL}" --write-out "\n%{http_code}" 2>&1)
EXIT_CODE=$?

# Extract HTTP status code from response
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

# Check if curl succeeded
if [ $EXIT_CODE -ne 0 ]; then
    echo "❌ Health check failed: Could not connect to ${URL}"
    echo "   Exit code: ${EXIT_CODE}"
    exit 1
fi

# Check if HTTP status code is 200
if [ "$HTTP_CODE" != "200" ]; then
    echo "❌ Health check failed: HTTP ${HTTP_CODE}"
    echo "   Response: ${BODY}"
    exit 1
fi

# Check if response contains expected health indicators
# The /health endpoint should return JSON with status information
if echo "$BODY" | grep -q '"status"'; then
    # Check if status is "healthy" or "ok"
    if echo "$BODY" | grep -qE '"status"\s*:\s*"(healthy|ok)"'; then
        echo "✅ Health check passed"
        exit 0
    else
        echo "⚠️  Health check warning: Response received but status not healthy"
        echo "   Response: ${BODY}"
        exit 1
    fi
else
    # Response doesn't contain expected JSON structure
    echo "⚠️  Health check warning: Unexpected response format"
    echo "   Response: ${BODY}"
    exit 1
fi
