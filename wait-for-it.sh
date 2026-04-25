#!/bin/bash
# wait-for-it.sh

set -e

TIMEOUT=30
QUIET=0

echo "Waiting for $HOST:$PORT..."

for i in $(seq 1 $TIMEOUT); do
    if nc -z "$HOST" "$PORT"; then
        echo "✅ $HOST:$PORT is available!"
        exec "$@"
        exit $?
    fi
    sleep 1
done

echo "❌ Timeout waiting for $HOST:$PORT"
exit 1
