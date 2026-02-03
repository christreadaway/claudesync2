# Claude Project Sync

**Version:** v5 (February 2026)
**Author:** Chris Treadaway
**Status:** Active / In Production

Bridges Claude Code and Claude.ai with local status files and automated PDF reports.

## Architecture: Separation of Concerns

**IMPORTANT:** This system maintains strict separation between instructions and status data.

| File | Contains | Does NOT Contain |
|------|----------|------------------|
| `~/.claude/CLAUDE.md` | Behavioral instructions for Claude Code | Project status, progress, history |
| `PROJECT_STATUS.md` | Per-project status, progress log, blockers | Global instructions |
| `status_report_*.pdf` | Visual dashboard of ALL projects | Instructions |
| `SHARED_ASSETS.md` | Reusable component registry | Instructions or status |

### Why This Matters

- **CLAUDE.md** tells Claude Code HOW to behave (update status at session end, remind about sync)
- **PROJECT_STATUS.md** captures WHAT was done (progress, decisions, blockers)
- **PDF Dashboard** provides a visual overview to upload to Claude.ai

Mixing these creates confusion. Keep them separate.

## Installation

```bash
# Clone the repository
git clone https://github.com/christreadaway/claudesync2.git ~/claude-project-sync
cd ~/claude-project-sync

# Install dependencies
pip3 install -r requirements.txt --break-system-packages

# Copy the CLAUDE.md instructions template to your global config
cp templates/CLAUDE.md ~/.claude/CLAUDE.md

# Initialize a new project with status tracking
python3 init_project_status.py /path/to/your/project --name "My Project" --category School

# Generate the PDF dashboard
python3 generate_status_pdf.py
```

## Key Files

| File | Purpose |
|------|---------|
| `generate_status_pdf.py` | Creates daily visual PDF report with charts |
| `init_project_status.py` | Initializes PROJECT_STATUS.md for new projects |
| `sync_history.py` | Scans projects and builds SHARED_ASSETS.md registry |
| `daily_status_report.sh` | Shell wrapper for 6am automation |
| `com.ctreada.dailystatusreport.plist` | Mac launchd config for scheduling |

## Daily Workflow

| When | What Happens | Where Status Lives |
|------|--------------|-------------------|
| 6:00 AM | PDF dashboard auto-generates | `~/claude-project-sync/status_report_*.pdf` |
| During work | Claude Code updates status at session end | `PROJECT_STATUS.md` in project folder |
| Switching to chat | User uploads PDF to Claude.ai | Claude.ai conversation |
| During chat | Claude.ai reads status from PDF | Claude.ai conversation |

## Usage

### Generate PDF Dashboard
```bash
python3 generate_status_pdf.py
open ~/claude-project-sync/status_report_$(date +%Y-%m-%d).pdf
```

### Initialize a New Project
```bash
python3 init_project_status.py /path/to/project --name "My Project" --category School
```

### Build Asset Registry
```bash
python3 sync_history.py --assets
```

### Quick Copy Status to Clipboard (Mac)
```bash
cat PROJECT_STATUS.md | pbcopy
```

## Setting Up Daily Automation (Mac)

```bash
# Copy the plist to LaunchAgents
cp com.ctreada.dailystatusreport.plist ~/Library/LaunchAgents/

# Load the launch agent
launchctl load ~/Library/LaunchAgents/com.ctreada.dailystatusreport.plist

# Verify it's scheduled
launchctl list | grep dailystatusreport
```

The PDF will generate daily at 6:00 AM (or when Mac wakes if asleep).

## Project Categories

- Infrastructure
- School
- Church
- Product
- Research
- Personal

## License

Open Source

---

*If this tool saves you time: Venmo @ctreada*
