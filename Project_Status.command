#!/bin/bash
#
# Project Status Dashboard - Double-click to launch
#
# Pulls all repos, syncs status, then launches the web dashboard.
# Place this file (or a symlink) on your Desktop for quick access.
#

SCRIPT_DIR="$HOME/claudesync2"
LOG_FILE="$SCRIPT_DIR/daily_report.log"
PORT=5111
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

banner "PROJECT STATUS DASHBOARD"
echo "  Started: $TIMESTAMP"
echo ""

# ── Step 1: Pull latest for all repos ───────────────────────────────────
banner "Step 1/3: Pulling latest from all repositories"
log "Starting dashboard launch"

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
    vibecoach
    repodoctor
    repodoctor2
    claudecodearchiver
    sacramentalrecords
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

# ── Step 3: Launch web dashboard ────────────────────────────────────────
banner "Step 3/3: Launching web dashboard"

# Kill any existing instance on this port
lsof -ti:$PORT 2>/dev/null | xargs kill 2>/dev/null

echo "  Starting dashboard on http://localhost:$PORT"
echo "  (PDF export available from the web interface)"
echo ""
log "Launching web dashboard on port $PORT"

# Open browser after a short delay (give Flask time to start)
(sleep 2 && open "http://localhost:$PORT") &

# Run the web app (this blocks until you close the terminal)
python3 "$SCRIPT_DIR/web_app.py"
