#!/bin/bash
# Sends one request to the server every half second and prints what happened.
# usage: scripts/client.sh <name> [url]      (run from a Mininet host, see docs/DEMO.md)
NAME="${1:-client}"
URL="${2:-http://10.0.0.100:5000/health}"  # keep in sync with nettwin/netmodel.py

while true; do
    CODE=$(curl -s -m 1 -o /dev/null -w "%{http_code}" "$URL")
    if [ "$CODE" = "200" ]; then STATE="OK"; else STATE="FAILED"; fi
    echo "$(date +%H:%M:%S.%3N) $NAME request $STATE (HTTP $CODE)"
    sleep 0.5
done
