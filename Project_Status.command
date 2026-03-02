#!/bin/bash
#
# Project Status Report - Double-click to run
#
# Syncs all project repos, generates a PDF status report, and opens it.
# Place this file on your Desktop for quick access.
#

SCRIPT_DIR="$HOME/claudesync2"
LOG_FILE="$SCRIPT_DIR/daily_report.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# ── Helper ───────────────────────────────────────────────────────────────
log() { echo "[$TIMESTAMP] $1" >> "$LOG_FILE"; }
banner() { echo ""; echo "═══════════════════════════════════════════════"; echo "  $1"; echo "═══════════════════════════════════════════════"; echo ""; }

# ── Preflight checks ────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install Python 3 first."
    read -n 1 -s -r -p "Press any key to close..."
    exit 1
fi

cd "$SCRIPT_DIR" || {
    echo "ERROR: Could not find $SCRIPT_DIR"
    echo "Make sure claudesync2 is cloned to ~/claudesync2"
    read -n 1 -s -r -p "Press any key to close..."
    exit 1
}

banner "PROJECT STATUS REPORT"
echo "  Started: $TIMESTAMP"
echo ""

# ── Step 1: Pull latest for all repos ───────────────────────────────────
banner "Step 1/3: Pulling latest from all repositories"
log "Starting manual status report"

REPOS=(
    audioscribe
    catholicevents
    claude-project-sync
    claudesync2
    desmond
    grantfinder
    imessage-dashboard-v6
    ministryfair
    ministrylife
    polygraph
    parentpoint
    parentpointedu
    personalcrm
)

for repo in "${REPOS[@]}"; do
    REPO_DIR="$HOME/$repo"
    if [ -d "$REPO_DIR/.git" ]; then
        echo "  Pulling $repo..."
        git -C "$REPO_DIR" pull --quiet 2>/dev/null || echo "    (skipped — no remote or offline)"
    fi
done
echo ""
echo "  Done pulling repos."

# ── Step 2: Sync git activity into PROJECT_STATUS files ─────────────────
banner "Step 2/3: Syncing project status"

python3 "$SCRIPT_DIR/sync_all_status.py" 2>&1
log "Sync complete"

# ── Step 3: Generate PDF and open it ────────────────────────────────────
banner "Step 3/3: Generating PDF report"

python3 "$SCRIPT_DIR/generate_status_pdf.py" --open 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    log "PDF generation completed and opened"
    echo ""
    echo "  Done! Your PDF report should be open now."
else
    log "ERROR: PDF generation failed (exit code $EXIT_CODE)"
    echo ""
    echo "  ERROR: PDF generation failed."
    echo "  Check $LOG_FILE for details."
    echo ""
    echo "  Common fixes:"
    echo "    pip3 install -r $SCRIPT_DIR/requirements.txt"
fi

echo ""
echo "═══════════════════════════════════════════════"
echo "  Press any key to close this window"
echo "═══════════════════════════════════════════════"
read -n 1 -s -r
