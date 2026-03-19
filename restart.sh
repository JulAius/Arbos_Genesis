#!/usr/bin/env bash
# Immediate self-restart for Arbos.
# Spawns a detached process that survives the pm2 kill chain,
# waits DELAY seconds, then tells pm2 to restart arbos.
# Usage: ./restart.sh [delay_seconds]

DELAY="${1:-5}"
nohup bash -c "sleep $DELAY && pm2 restart arbos" > /dev/null 2>&1 &
disown
echo "Restart scheduled in ${DELAY}s"
