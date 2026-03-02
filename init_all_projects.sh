#!/bin/bash
#
# Initialize PROJECT_STATUS.md for all tracked projects.
# Run this once on your Mac to seed every repo with a status file.
#
# Usage: bash ~/claudesync2/init_all_projects.sh
#

SCRIPT_DIR="$HOME/claudesync2"
INIT_SCRIPT="$SCRIPT_DIR/init_project_status.py"

if [ ! -f "$INIT_SCRIPT" ]; then
    echo "ERROR: init_project_status.py not found at $INIT_SCRIPT"
    exit 1
fi

echo ""
echo "═══════════════════════════════════════════════"
echo "  Initializing PROJECT_STATUS.md for all repos"
echo "═══════════════════════════════════════════════"
echo ""

init_project() {
    local dir="$1" name="$2" category="$3" repo="$4" progress="${5:-0}" status="${6:-Not Started}"

    if [ ! -d "$HOME/$dir" ]; then
        echo "  SKIP  $name — directory ~/$dir not found"
        return
    fi

    if [ -f "$HOME/$dir/PROJECT_STATUS.md" ]; then
        echo "  EXISTS $name — already has PROJECT_STATUS.md"
        return
    fi

    python3 "$INIT_SCRIPT" "$HOME/$dir" \
        --name "$name" \
        --category "$category" \
        --repo "$repo" \
        --progress "$progress" \
        --status "$status" 2>/dev/null

    if [ $? -eq 0 ]; then
        echo "  INIT   $name"
    else
        echo "  ERROR  $name — init failed"
    fi
}

# ── Infrastructure ──────────────────────────────────────────────────────
echo "Infrastructure:"
init_project "claudesync2"         "Claude Project Sync v2"  "Infrastructure" "christreadaway/claudesync2"         75 "Active"
init_project "desmond"             "Desmond"                 "Infrastructure" "christreadaway/desmond"              50 "In Progress"
init_project "repodoctor"          "RepoDoctor"              "Infrastructure" "christreadaway/repodoctor"           10 "Not Started"
init_project "repodoctor2"         "RepoDoctor v2"           "Infrastructure" "christreadaway/repodoctor2"          10 "Not Started"
init_project "claudecodearchiver"  "Claude Code Archiver"    "Infrastructure" "christreadaway/claudecodearchiver"   10 "Not Started"
init_project "claude-project-sync" "Claude Project Sync v1"  "Infrastructure" "christreadaway/claude-project-sync"  100 "Complete"
echo ""

# ── Church ──────────────────────────────────────────────────────────────
echo "Church:"
init_project "catholicevents"      "Catholic Events"         "Church" "christreadaway/catholicevents"       20 "In Progress"
init_project "ministryfair"        "Ministry Fair App"       "Church" "christreadaway/ministryfair"         40 "In Progress"
init_project "ministrylife"        "MinistryLife"            "Church" "christreadaway/ministrylife"         20 "In Progress"
init_project "sacramentalrecords"  "Sacramental Records"     "Church" ""                                   10 "Spec Complete"
echo ""

# ── School ──────────────────────────────────────────────────────────────
echo "School:"
init_project "grantfinder"         "GrantFinder AI"          "School" "christreadaway/grantfinder"          30 "In Progress"
init_project "parentpoint"         "ParentPoint"             "School" "christreadaway/parentpoint"          20 "In Progress"
init_project "parentpointedu"      "ParentPoint EDU"         "School" "christreadaway/parentpointedu"       30 "In Progress"
echo ""

# ── Product ─────────────────────────────────────────────────────────────
echo "Product:"
init_project "audioscribe"         "AudioScribe"             "Product" "christreadaway/audioscribe"          40 "In Progress"
init_project "polygraph"           "Polygraph (multiloc.ai)" "Product" "christreadaway/polygraph"            20 "In Progress"
init_project "vibecoach"           "VibeCoach"               "Product" "christreadaway/vibecoach"            10 "Not Started"
echo ""

# ── Personal ────────────────────────────────────────────────────────────
echo "Personal:"
init_project "personalcrm"         "Personal CRM"            "Personal" "christreadaway/personalcrm"          10 "Not Started"
init_project "imessage-dashboard-v6" "iMessage Dashboard v6" "Personal" "christreadaway/imessage-dashboard-v6" 20 "In Progress"
echo ""

echo "═══════════════════════════════════════════════"
echo "  Done! Now run: python3 ~/claudesync2/web_app.py"
echo "═══════════════════════════════════════════════"
