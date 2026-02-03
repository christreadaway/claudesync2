#!/bin/bash
#
# Claude Project Sync - Daily Status Report
# Called by launchd at 6:00 AM daily
#

SCRIPT_DIR="$HOME/claude-project-sync"
LOG_FILE="$SCRIPT_DIR/daily_report.log"

mkdir -p "$SCRIPT_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

log "Starting daily status report"

if ! command -v python3 &> /dev/null; then
    log "ERROR: Python3 not found"
    exit 1
fi

if [ ! -f "$SCRIPT_DIR/generate_status_pdf.py" ]; then
    log "ERROR: generate_status_pdf.py not found"
    exit 1
fi

cd "$SCRIPT_DIR"
python3 generate_status_pdf.py >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    log "PDF generation completed"
else
    log "ERROR: PDF generation failed"
    exit 1
fi

log "Done"
exit 0
