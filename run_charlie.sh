#!/bin/bash
# run_charlie.sh — reconnect ADB + nuke + charlie single cycle
# Called by cron or manually

VENV="/home/corban/good bots/venv/bin/python3"
DIR="/home/corban/charlie"
PHONE="192.168.68.50"
LOG="/home/corban/charlie/charlie_$(date +%Y%m%d_%H%M%S).log"

echo "[$(date)] Starting Charlie run..." >> "$LOG"

# Reconnect ADB if needed
echo "[$(date)] Checking ADB connection..." >> "$LOG"
CONNECTED=$(adb devices -l 2>/dev/null | grep "$PHONE" | grep "device" | head -1)
if [ -z "$CONNECTED" ]; then
    echo "[$(date)] Phone not connected. Scanning ports..." >> "$LOG"
    adb disconnect >> "$LOG" 2>&1
    sleep 1
    for PORT in $(seq 30000 49999); do
        if timeout 0.1 bash -c "echo >/dev/tcp/$PHONE/$PORT" 2>/dev/null; then
            echo "[$(date)] Port $PORT open — connecting..." >> "$LOG"
            RESULT=$(adb connect "$PHONE:$PORT" 2>&1)
            echo "  $RESULT" >> "$LOG"
            if echo "$RESULT" | grep -qi "connected"; then
                echo "[$(date)] ADB connected on port $PORT" >> "$LOG"
                break
            fi
        fi
    done
else
    echo "[$(date)] ADB already connected: $CONNECTED" >> "$LOG"
fi
sleep 2

# Nuke first
"$VENV" "$DIR/nuke.py" >> "$LOG" 2>&1
sleep 3

# Run 1 cycle
"$VENV" -u "$DIR/charlie.py" --cycles 1 >> "$LOG" 2>&1

echo "[$(date)] Charlie finished." >> "$LOG"
