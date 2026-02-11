# Product Spec: Claude Project Sync v5

## Product Overview

**Product Name:** Claude Project Sync (claudesync2)

**Problem Statement:** Developers using Claude Code (CLI) work across many projects, but Claude.ai (web) has no visibility into project status, progress, or recent work. Each new conversation starts from zero context. Chat history contains valuable project intelligence that's trapped in export zips. There's no bridge between the two environments.

**Solution:** A local-first system that:
1. Maintains per-project status files (`PROJECT_STATUS.md`)
2. Runs a live web dashboard with real-time project data
3. Parses Claude.ai chat history exports and matches conversations to projects
4. Optionally enriches project descriptions using the Anthropic API
5. Generates a downloadable PDF report for sharing with Claude.ai
6. Tracks open threads, blockers, and decisions across all projects

---

## Architecture

```
PROJECT_STATUS.md files (per-project, in each repo)
        |
        v
generate_status_pdf.py — scanner, parser, chat matcher, PDF renderer
        |
        v
web_app.py — Flask dashboard (localhost:5111)
        |
        ├── Dashboard (stats, chart, project cards, filters)
        ├── Drill-down views (/view/projects, /events, /threads, /blockers)
        ├── Project detail pages (/project/<idx>)
        ├── Upload modal (chat history zip + scan paths)
        ├── AI enrichment (Anthropic API integration)
        └── PDF generation (/generate-pdf)
```

**Persistence layer** (all `~/.claudesync_*.json`):
- `_ignored.json` — hidden/EOL project names
- `_resolved.json` — resolved thread keys
- `_archived.json` — archived project names
- `_ai.json` — API config (url, key, model)
- `_import_meta.json` — last chat import timestamp + filename

---

## User Story

**Who:** A developer managing 5-30+ projects, using Claude Code for development and Claude.ai for planning/research.

**Workflow:**
1. Developer works in Claude Code — commits happen on `claude/*` branches, `PROJECT_STATUS.md` files get updated
2. Developer opens `http://localhost:5111` in their browser
3. Uploads a Claude.ai chat history export zip (optional — enriches timeline with chat data)
4. Dashboard shows all projects with activity charts, thread counts, blockers
5. Clicks into any project for full timeline and open threads
6. Clicks "Generate PDF" to get a downloadable report
7. Uploads PDF to Claude.ai for instant context across all projects

---

## Core Functionality

### 1. Project Status Files (`PROJECT_STATUS.md`)

Each project directory contains a `PROJECT_STATUS.md` with:
- Metadata table (name, repo, category, progress %, status, last worked, last synced)
- "What's Working" bullet list
- "What's Not Working" bullet list
- "Blockers" bullet list
- "Progress Log" with dated session entries (`### YYYY-MM-DD`)
- "Open Design Questions" markdown table
- "Next Steps" numbered/bulleted list
- "Reusable Assets" table

**Critical Design Decision:** `CLAUDE.md` contains ONLY behavioral instructions for Claude Code. Status data belongs ONLY in `PROJECT_STATUS.md`. These must never be mixed.

### 2. Web Dashboard (`web_app.py`)

Flask app running on `localhost:5111`. Fully local — nothing leaves the machine.

**Dashboard page (`/`):**
- 4 clickable stat cards: Projects, Events, Threads, Blockers — each links to a drill-down list view
- Stacked bar chart (Chart.js) showing activity across all projects, toggleable by Day/Week/Month
- Filter bar: Active, Possibly EOL, Ignored
- Project card grid (responsive, 320px min) with:
  - Progress bar (color-coded by %)
  - Activity counts (commits, chats, logs)
  - Last 3 decisions
  - First 3 open threads with color-coded tags
  - EOL detection with Ignore button
- Dark/light theme toggle (persisted in localStorage)
- Upload Chat History modal
- AI Settings modal
- Generate PDF button

**Drill-down list views:**
- `/view/projects` — all projects, split into Active and Archived sections, with Archive/Unarchive buttons
- `/view/events` — all timeline events across all projects, newest first, tagged by type (Commit/Chat/Log)
- `/view/threads` — all open threads with Resolve buttons, grouped by project
- `/view/blockers` — filtered to blocker-type threads only, with Resolve buttons

**Project detail page (`/project/<idx>`):**
- Header card with metadata, progress bar, narrative description
- Full decision timeline with dated entries, source tags, colored bullets
- Open threads card with Resolve buttons
- "Enrich with AI" button (when API key configured)

**Loading overlay:**
- Full-screen spinner shown during Load & Refresh and Generate PDF
- Blocks UI to prevent double-clicks
- Submit button disabled during processing

### 3. Chat History Integration

**Upload flow:**
- User exports chat history from Claude.ai (zip file)
- Uploads via drag-and-drop or file picker in the Upload modal
- System extracts .md/.txt/.json files from the zip
- Matches chat paragraphs to projects using fuzzy name matching + scoring
- Creates timeline entries with dates and source attribution
- Import timestamp and filename saved for reference

**Matching algorithm:**
- Builds search terms per project: name variants, without version, squashed, first words, longest word
- Scores paragraphs by: term frequency * term length, length bonus, descriptive word bonus
- Deduplicates by word overlap ratio (>0.5 = skip)
- Keeps top 8 snippets per project

**AI-powered analysis (optional):**
- Checkbox in upload modal: "Analyze chats with AI for richer project descriptions"
- Only shown when API key is configured
- Sends each project's context (timeline, features, threads) to the AI
- AI generates 3-5 sentence narrative per project
- Stored in project's `narrative` field

### 4. AI Integration

**Configuration (AI Settings modal):**
- API URL (default: `https://api.anthropic.com/v1/messages`)
- API Key (stored locally in `~/.claudesync_ai.json`, masked in UI)
- Model dropdown: Haiku 4.5 (default, cheapest), Sonnet 4.5 (balanced), Opus 4.6 (most capable)

**Two modes:**
- **Bulk enrichment** — during Load & Refresh, enriches all projects at once
- **Per-project enrichment** — "Enrich with AI" button on project detail page

**Prompt pattern:**
- Sends: project name, status, progress, category, features, not-working, recent timeline, open threads
- Asks for: 3-5 sentence summary covering what it does, current state, what's happening
- max_tokens: 250, timeout: 30s

### 5. PDF Generator (`generate_status_pdf.py`)

Generates a multi-page PDF grouped by category:

**Per-project block:**
- Header with progress % and status
- Meta line: last active, last synced
- Narrative paragraph
- Recent Activity (last 5 timeline items, human-readable dates)
- Open Threads (max 6, color-coded tags, truncated to 120 chars)

**Cross-project section:**
- "What's Left Unfinished" — shows all projects with open threads
- Grouped by project name, first 4 threads per project
- Color-coded by thread type

**Category ordering:** Church, School, Product, Infrastructure, Personal, Research

### 6. EOL Detection

Projects flagged as "Possibly EOL" if:
- Status contains: abandoned, archived, deprecated, eol, merged, completed, sunset, dead
- No activity in 90+ days
- 0% progress AND no timeline entries

### 7. Archive & Ignore System

**Ignore** (for EOL projects on dashboard):
- Ignore button on EOL-flagged cards
- Persisted to `~/.claudesync_ignored.json`
- Restore button to bring back

**Archive** (on /view/projects):
- Archive button per project
- Archived projects excluded from dashboard stats and chart
- Persisted to `~/.claudesync_archived.json`
- Unarchive to restore

### 8. Thread Resolution

- Resolve button on threads in detail pages and list views
- Thread key: `project_name::thread_text[:100]`
- Persisted to `~/.claudesync_resolved.json`
- Resolved threads hidden from counts and displays

---

## CLI Tools

### `init_project_status.py`
```bash
python3 init_project_status.py ~/myproject --name "My Project" --category School
```
Options: `--name` (required), `--category`, `--repo`, `--progress`, `--status`

### `update_repos.py`
```bash
python3 update_repos.py          # Auto-detect all
python3 update_repos.py --list   # Show current status
python3 update_repos.py --project "Name" --repo "user/repo"
```

### `sync_history.py`
```bash
python3 sync_history.py --assets  # Build SHARED_ASSETS.md registry
```

### `generate_status_pdf.py` (standalone CLI)
```bash
python3 generate_status_pdf.py --scan-paths "~ ~/projects" --chat-history ~/export.zip
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Dashboard |
| GET | `/project/<idx>` | Project detail |
| GET | `/view/projects` | All projects list |
| GET | `/view/events` | All events list |
| GET | `/view/threads` | Open threads list |
| GET | `/view/blockers` | Blockers list |
| GET | `/api/chart-data?mode=day\|week\|month` | Activity chart data |
| POST | `/api/ignore` | Hide project `{name}` |
| POST | `/api/restore` | Unhide project `{name}` |
| POST | `/api/archive` | Archive project `{name}` |
| POST | `/api/unarchive` | Unarchive project `{name}` |
| POST | `/api/resolve-thread` | Resolve thread `{project, text}` |
| POST | `/api/enrich/<idx>` | AI-enrich single project |
| GET/POST | `/api/ai-config` | Get/save AI configuration |
| POST | `/upload` | Upload chat zip + reload |
| GET | `/generate-pdf` | Download PDF report |

---

## Data Model

### Project Object
```python
{
    'name': str,
    'file_path': str,           # Path to PROJECT_STATUS.md
    'project_path': str,        # Project directory
    'repo': str,                # GitHub user/repo
    'category': str,            # Raw category
    'category_group': str,      # Normalized (Church, School, Product, etc.)
    'progress': int,            # 0-100
    'status': str,              # Not Started, In Progress, Beta, Complete, etc.
    'has_repo': str,            # Yes/No
    'has_github_repo': bool,    # Computed
    'last_worked': str,         # YYYY-MM-DD
    'last_synced': str,         # YYYY-MM-DD
    'summary': str,             # Description from status file
    'narrative': str,           # AI-generated or summary-derived
    'features': [str],          # What's Working items
    'not_working': [str],       # What's Not Working items
    'blockers': [str],          # Blockers
    'next_steps': [str],        # Next Steps
    'open_questions': [str],    # Design Questions from tables
    'progress_log': [dict],     # Dated entries from Progress Log section
    'git_commits': [dict],      # Recent commits from git history
    'timeline': [dict],         # Merged timeline (progress + git + chat)
    'open_threads': [(str,str)] # (type, text) — all unfinished items
}
```

### Timeline Entry
```python
{'date': 'YYYY-MM-DD', 'source': str, 'text': str}
```

### Thread Types
- **Blocker** (red) — from Blockers section
- **Open Question** (orange) — from Design Questions table
- **Next Step** (blue) — from Next Steps section
- **Not Yet Built** (gray) — from What's Not Working section

---

## PROJECT_STATUS.md Schema

```markdown
# PROJECT_STATUS: [Project Name]

## Metadata
| Field | Value |
|-------|-------|
| **Project Name** | [Name] |
| **Repository** | [user/repo or "(not created)"] |
| **Category** | [Infrastructure/School/Church/Product/Research/Personal] |
| **Progress** | [0-100]% |
| **Status** | [Not Started/In Progress/Beta/Complete/Shelved] |
| **Last Worked** | [YYYY-MM-DD] |
| **Has GitHub Repo** | [Yes/No] |
| **Last Synced to Claude.ai** | [YYYY-MM-DD] |

## Current State
### What's Working
### What's Not Working
### Blockers

## Progress Log
### YYYY-MM-DD (Source Description)

## Open Design Questions
| Question | Status | Notes |

## Next Steps

## Reusable Assets
| Asset | Description | Tags |
```

---

## Progress Color Coding

| Progress | Color |
|----------|-------|
| > 75% | Green (#2ECC71) |
| 50-75% | Blue (#3498DB) |
| 25-49% | Yellow (#F1C40F) |
| < 25% | Red (#E74C3C) |

---

## Theming

Light and dark themes via CSS custom properties on `[data-theme]`. Persisted in localStorage, applied before paint to prevent flash. Toggle button in top bar on every page.

---

## Dependencies

### Python
```
flask (included in stdlib-adjacent, no explicit requirement)
reportlab>=4.0.0
matplotlib>=3.7.0
numpy>=1.24.0
```

### System
- Python 3.8+
- Git (commit history + remote detection)
- macOS or Linux

### Optional
- Anthropic API key (for AI enrichment)

---

## File Structure

```
~/claudesync2/
├── web_app.py                  # Flask dashboard (1666 lines)
├── generate_status_pdf.py      # Scanner, parser, chat matcher, PDF renderer (1109 lines)
├── init_project_status.py      # Project initializer CLI
├── update_repos.py             # Batch repo updater CLI
├── sync_history.py             # Asset registry builder
├── requirements.txt            # Python dependencies
├── .gitignore
├── CLAUDE.md                   # Claude Code behavioral instructions
├── PRODUCT_SPEC.md             # This document
├── PROJECT_STATUS.md           # This project's own status
├── README.md
├── templates/
│   ├── CLAUDE.md               # Template for new projects
│   └── PROJECT_STATUS.md       # Template for new projects
├── daily_status_report.sh      # Shell script for cron/launchd
└── com.ctreada.dailystatusreport.plist  # macOS LaunchAgent
```

### Persistence Files (in `~/`)
```
~/.claudesync_ignored.json      # Hidden project names
~/.claudesync_resolved.json     # Resolved thread keys
~/.claudesync_archived.json     # Archived project names
~/.claudesync_ai.json           # AI API config (url, key, model)
~/.claudesync_import_meta.json  # Last chat import metadata
```

---

## Quick Start

```bash
# Install
cd ~/claudesync2
pip3 install -r requirements.txt

# Run the dashboard
python3 web_app.py
# Open http://localhost:5111

# Or generate PDF from CLI
python3 generate_status_pdf.py --scan-paths ~ --chat-history ~/export.zip
```

---

## Out of Scope (For Now)

1. **Automatic Claude.ai upload** — user must manually upload PDF
2. **Real-time sync** — PDF/dashboard is point-in-time snapshot
3. **Progress auto-calculation** — user sets progress % manually
4. **Multi-user support** — single developer only
5. **Cloud storage** — all data is local, nothing leaves the machine
6. **Windows support** — untested

---

*Last updated: 2026-02-11*
*Version: 5.0*
