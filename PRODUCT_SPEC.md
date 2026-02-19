# Product Spec: Claude Project Sync v7.1

## Product Overview

**Product Name:** Claude Project Sync (claudesync2)

**Problem Statement:** Developers using Claude Code (CLI) work across many projects, but Claude.ai (web) has no visibility into project status, progress, or recent work. Each new conversation starts from zero context. Chat history contains valuable project intelligence that's trapped in export zips. There's no bridge between the two environments.

**Solution:** A local-first system that:
1. Maintains per-project status files (`PROJECT_STATUS.md`)
2. Runs a live web dashboard with real-time project data
3. Parses Claude.ai chat history exports and matches conversations to initiatives
4. Automatically enriches and classifies using the Anthropic API when a key is present
5. Generates a downloadable PDF report for sharing with Claude.ai
6. Tracks open threads, blockers, and decisions across all projects
7. Uses AI to classify unmatched conversations into new or existing initiatives
8. Lets users manually assign, dismiss, or restore unmatched conversations
9. Color-codes projects by category for instant visual identification
10. Displays all timestamps in a configurable timezone (default: Central US)

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
        ├── Dashboard (stats, chart, category-colored project cards, filters)
        ├── Drill-down views (/view/projects, /events, /threads, /blockers)
        ├── What's Next triage (/view/whats-next)
        ├── Unmatched conversations (/view/unmatched) with assign/dismiss
        ├── Project detail pages (/project/<idx>)
        ├── Settings page (/settings) — timezone, AI config, scan paths
        ├── Non-blocking background processing (threading + progress polling)
        ├── AI integration (auto when key present, prompt when not)
        └── PDF generation (/generate-pdf)
```

**Persistence layer** (all `~/.claudesync_*.json`):
- `_ignored.json` — hidden/EOL project names
- `_resolved.json` — resolved thread keys
- `_archived.json` — archived project names
- `_ai.json` — API config (url, key, model)
- `_import_meta.json` — last chat import timestamp + filename
- `_item_actions.json` — item ignore/reassign decisions (What's Next)
- `_initiatives.json` — AI classification results + manual assignments for unmatched chats
- `_dismissed_chats.json` — user-dismissed/assigned conversation filenames
- `_settings.json` — dashboard settings (timezone, etc.)

---

## User Story

**Who:** A developer managing 5-30+ projects, using Claude Code for development and Claude.ai for planning/research.

**Workflow:**
1. Developer works in Claude Code — commits happen on `claude/*` branches, `PROJECT_STATUS.md` files get updated
2. Developer opens `http://localhost:5111` in their browser
3. **Server starts instantly** — projects load in background with visible progress banner
4. Dashboard is browsable immediately — no blocking wait for data
5. Clicks "Upload Chat History" — drops in a Claude.ai export zip + scan paths
6. **If API key exists:** AI enrichment + initiative classification runs automatically in the background
7. **If no API key:** A prompt appears asking "Enable AI-Enhanced Results?" with API key field
8. **Visible confirmation:** "Key saved!" with green flash when API key is saved
9. App stays fully usable during processing — sticky progress bar shows step-by-step status
10. Dashboard populates with category-colored project cards, activity charts, thread counts, blockers
11. Clicks into any project for full timeline and open threads
12. Checks "What's Next" for cross-project triage of all action items
13. Checks "Unmatched Conversations" — assigns chats to projects, dismisses irrelevant ones
14. Clicks "Generate PDF" for a downloadable report to share with Claude.ai

---

## Core Functionality

### 1. Project Status Files (`PROJECT_STATUS.md`)

Each project directory contains a `PROJECT_STATUS.md` with:
- Metadata table (name, repo, category, progress %, status, last worked, last synced, dev state)
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

**Startup behavior:**
- Server starts immediately — no blocking preload
- Initial project scan runs in background thread
- Progress banner auto-shows if background task is running on page load

**Dashboard page (`/`):**
- Sticky progress banner (right below top bar) — visible during all background processing
- 5 clickable stat cards: Projects, Events, Threads, Blockers, Unmatched Chats — each links to a drill-down view
- Stacked bar chart (Chart.js) showing activity across all projects, toggleable by Day/Week/Month
- Filter bar: Active, Possibly EOL, Ignored
- Project card grid (responsive, 320px min) with:
  - **Category color-coding** — colored left border + category badge per card
  - Progress bar (color-coded by %)
  - Activity counts (commits, chats, logs)
  - Last 3 decisions
  - First 3 open threads with color-coded tags
  - EOL detection with Ignore button
- Dark/light theme toggle (persisted in localStorage)
- Top-bar buttons: What's Next, Upload Chat History, Settings, Generate PDF

**Category colors (light + dark mode variants):**

| Category | Border Color | Badge Color |
|----------|-------------|-------------|
| Church | Purple (#7E57C2) | Purple bg/text |
| School | Blue (#1E88E5) | Blue bg/text |
| Product | Green (#43A047) | Green bg/text |
| Infrastructure | Orange (#EF6C00) | Orange bg/text |
| Personal | Pink (#C2185B) | Pink bg/text |
| Research | Teal (#00897B) | Teal bg/text |

**Drill-down list views:**
- `/view/projects` — all projects, split into Active and Archived sections, with Archive/Unarchive buttons
- `/view/events` — all timeline events across all projects, newest first, tagged by type (Commit/Chat/Log)
- `/view/threads` — all open threads with Resolve buttons, grouped by project
- `/view/blockers` — filtered to blocker-type threads only, with Resolve buttons
- `/view/whats-next` — cross-project triage (see Section 11)
- `/view/unmatched` — unmatched chat conversations with assign/dismiss/restore (see Section 12)

**Project detail page (`/project/<idx>`):**
- Header card with metadata, progress bar, narrative description
- Dev state dropdown (test/refine/continue) with color-coded badge
- "AI Assess" button to auto-classify dev state using AI
- Full decision timeline with dated entries, source tags, colored bullets
- Open threads card with Resolve buttons
- "Enrich with AI" button (when API key configured)

**Settings page (`/settings`):**
- Timezone selector (default: Central US / America/Chicago, auto-adjusts for DST)
- AI configuration: API URL, API key (with save confirmation), model selector
- Scan paths configuration
- "Save All Settings" button with visible success/error feedback

### 3. Non-Blocking Background Processing

All heavy work (scanning, parsing, chat matching, AI enrichment, AI classification) runs in a **background thread**. The app stays fully usable during processing.

**Sticky progress banner (right below top bar):**
- Visible on every page load if background task is running
- Shows spinner + step name + detail message
- Steps: Scanning → Parsing → Reading Chat → Matching Chat → AI Enrichment → AI Classifying → Building → Done
- Progress track fills based on current step
- Auto-reloads the page 1.5s after completion
- Error state shown in red if something fails
- `position: sticky; top: 0; z-index: 90` — stays visible while scrolling

**Implementation:** Background thread + `/api/progress` polling every 500ms. No SSE or WebSockets needed.

**Startup:** `__main__` block kicks off `_bg_run_load` in a daemon thread, server starts immediately.

### 4. Chat History Integration

**Upload flow:**
- User exports chat history from Claude.ai (zip file)
- Uploads via drag-and-drop or file picker in the Upload modal
- System extracts conversations from the zip (see JSON parsing below)
- Two-tier matching runs against all projects
- Import timestamp and filename saved for reference

**JSON conversation parsing (new):**
- Handles Claude.ai export format: single `conversations.json` containing array of conversation objects
- Extracts individual conversations from JSON arrays
- Handles wrapper dicts with keys like `conversations`, `chat_messages`, `data`, `items`
- Parses message text from multiple formats:
  - Claude.ai: `{sender: "human", text: "..."}` in `chat_messages` list
  - OpenAI-style: `{role: "user", content: "..."}` in `messages` list
  - Mapping format: `{node_id: {message: {author: {role: "..."}, content: {parts: [...]}}}}}`
- Extracts dates from: `created_at`, `updated_at`, `date`, `timestamp` (ISO 8601 + Unix timestamps)
- Accepts file types: `.md`, `.txt`, `.json`, `.jsonl`, `.csv`, `.yaml`, `.yml`
- JSONL support: one JSON object per line
- Prints extraction stats: "Extracted X conversations from Y files"

**Matching algorithm (two-tier):**
1. **Per-conversation:** If ANY paragraph in a chat file mentions a project, that whole file counts as a conversation event for that project
2. **Per-paragraph:** Best-scoring paragraphs become detailed timeline entries with excerpts

**Scoring:**
- Builds search terms per project: name variants, without version, squashed, first words, longest word
- Scores paragraphs by: term frequency * term length, length bonus, descriptive word bonus
- Deduplicates by word overlap ratio (>0.65 = skip)
- Keeps up to 50 snippets per project
- Minimum paragraph length: 30 characters
- Code ratio filter: skip if >60% code lines

**Unmatched tracking:**
- Chat files that don't match any project are collected with excerpts
- Stored in chat stats for the AI classification step
- Shown on the dashboard as an "Unmatched Chats" stat card

### 5. AI Integration

**Automatic behavior:**
- **When API key exists:** AI runs automatically on every Load & Refresh — no opt-in needed
  - Enriches all project descriptions
  - Classifies all unmatched chat conversations into initiatives
- **When no API key exists:** A prompt modal appears on Load asking "Enable AI-Enhanced Results?"
  - Shows what AI does (enrichment, classification, verification)
  - API key input field
  - **OK:** saves the key with visible "Key saved!" confirmation (green flash, 800ms delay), then proceeds with AI enabled
  - **Skip:** proceeds without AI
  - **Error handling:** "Failed — try again" on save error

**AI Settings (now in Settings page `/settings`):**
- API URL (default: `https://api.anthropic.com/v1/messages`)
- API Key (stored locally, masked display showing first 8 chars)
- Model dropdown: Haiku 4.5 (default, cheapest), Sonnet 4.5 (balanced), Opus 4.6 (most capable)
- Save button with "Saved!" / green confirmation, auto-reset after 2.5s

**Enrichment modes:**
- **Bulk enrichment** — during Load & Refresh background task
- **Per-project enrichment** — "Enrich with AI" button on project detail page

**Enrichment prompt:**
- Sends: project name, status, progress, category, features, not-working, recent timeline, open threads
- Asks for: 3-5 sentence summary covering what it does, current state, what's happening
- max_tokens: 250, timeout: 30s

### 6. PDF Generator (`generate_status_pdf.py`)

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

### 7. EOL Detection

Projects flagged as "Possibly EOL" if:
- Status contains: abandoned, archived, deprecated, eol, merged, completed, sunset, dead
- No activity in 90+ days
- 0% progress AND no timeline entries

### 8. Archive & Ignore System

**Ignore** (for EOL projects on dashboard):
- Ignore button on EOL-flagged cards
- Persisted to `~/.claudesync_ignored.json`
- Restore button to bring back

**Archive** (on /view/projects):
- Archive button per project
- Archived projects excluded from dashboard stats and chart
- Persisted to `~/.claudesync_archived.json`
- Unarchive to restore

### 9. Dev State Tracking

Each project can be assigned a development state reflecting its current work status:

| State | Color | Meaning |
|-------|-------|---------|
| **test** | Orange (#E67E22) | Code was pushed with no evidence of testing. Needs testing. |
| **refine** | Blue (#3498DB) | User satisfied or riffing/exploring. Chat abandoned in good state. |
| **continue** | Red (#E74C3C) | Active testing ongoing but not resolved. Work in progress. |

**Dashboard display:**
- Color-coded badge next to project name on cards and detail page
- Left border accent on project cards matching dev state color
- Dark mode variants for all badge colors

**Setting dev state:**
- Dropdown on project detail page (test/refine/continue/none)
- Persisted to `PROJECT_STATUS.md` via `| **Dev State** | value |` metadata row
- If the field doesn't exist in the file, it's auto-inserted after the Status row

**AI assessment:**
- "AI Assess" button on project detail page
- Sends project timeline + threads to AI
- AI responds with state classification + reasoning
- Auto-selects the suggested state in the dropdown

### 10. Thread Resolution

- Resolve button on threads in detail pages and list views
- Thread key: `project_name::thread_text[:100]`
- Persisted to `~/.claudesync_resolved.json`
- Resolved threads hidden from counts and displays

### 11. What's Next View (`/view/whats-next`)

Cross-project triage view showing every actionable item across all projects.

**Grouped by project**, sorted by priority:
1. Blockers (red)
2. Next Steps (blue)
3. Open Questions (orange)
4. Not Yet Built (gray)

**Per-item actions:**
- **Resolve** — marks the thread as resolved
- **Ignore** — dismisses the item, moves to Ignored section with Restore button
- **Reassign** — dropdown of all other projects, moves item to Reassigned section showing "From X → Y", with Undo button

**Sections:**
- Active items (grouped by project with progress bar and category)
- Reassigned items (with Undo)
- Ignored items (with Restore)

**AI Category Verification:**
- "Verify All Categories with AI" button at top of page
- Sends all projects to AI in a single call
- Flags low-confidence categorizations inline: red "AI: should be [category]" or green "OK"

**Persistence:** `~/.claudesync_item_actions.json`

### 12. Unmatched Conversations & Management (`/view/unmatched`)

Shows chat conversations not automatically matched to any project by fuzzy name matching.

**Stats bar:** Active Unmatched, New Initiatives Suggested, Matched to Existing, Dismissed/Assigned

**AI classification** (runs automatically during Load & Refresh when key is present):
- Sends unmatched conversations to AI in batches of 15
- AI responds per conversation with:
  - `MATCH initiative_name` — belongs to an existing project/initiative
  - `NEW suggested_initiative_name` — suggests a new 2-5 word initiative name
  - `SKIP` — too vague, greetings, small talk
- Results grouped by suggested initiative with conversation excerpts
- Can also be triggered manually via "Classify with AI" button

**Per-conversation actions:**
- **Assign to project** — dropdown of all existing projects; assigns and auto-dismisses the chat
  - Green flash confirmation: "Assigned to [Project Name]"
  - Smooth fade-out animation
- **Dismiss** — removes from active view, moves to Dismissed section
  - Fade-out animation on dismiss
- **Restore** — brings back a dismissed/assigned chat to active view

**Bulk actions:**
- **Dismiss All Skipped** — one-click dismissal of all AI-skipped chats (with confirmation dialog)

**Sections (top to bottom):**
1. Suggested New Initiatives (from AI, with assign/dismiss per conversation)
2. Matched to Existing Projects (from AI, with assign/dismiss per conversation)
3. Not Yet Classified (awaiting AI, with assign/dismiss per conversation)
4. Skipped / Small Talk (from AI, with "Dismiss All Skipped" bulk action)
5. Dismissed / Assigned (collapsed by default, click to show/hide, with Restore buttons)

**Persistence:**
- `~/.claudesync_initiatives.json` — AI classification results + manual assignment records
- `~/.claudesync_dismissed_chats.json` — set of dismissed/assigned filenames

### 13. Timezone-Aware Timestamps

All dashboard-generated timestamps use the configured timezone:
- Default: `America/Chicago` (Central US)
- Automatically adjusts for daylight savings (CST ↔ CDT)
- Format: `YYYY-MM-DD HH:MM AM/PM TZ` (e.g., `2026-02-11 06:09 PM CST`)
- Applied to: last import time, last classified time, assignment timestamps
- Configurable via Settings page (`/settings`)
- Uses Python `zoneinfo.ZoneInfo` for IANA timezone database
- Available zones: Central, Eastern, Mountain, Pacific, UTC, London

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

### Pages (HTML responses)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Dashboard with category-colored project cards |
| GET | `/project/<idx>` | Project detail with timeline + threads |
| GET | `/settings` | Settings page (timezone, AI config, scan paths) |
| GET | `/view/projects` | All projects list with Archive/Unarchive |
| GET | `/view/events` | All events list with type badges |
| GET | `/view/threads` | Open threads list with Resolve buttons |
| GET | `/view/blockers` | Blockers list with Resolve buttons |
| GET | `/view/whats-next` | Cross-project triage with assign/dismiss |
| GET | `/view/unmatched` | Unmatched conversations with assign/dismiss/restore |

### JSON API Endpoints

**Progress & Data:**

| Method | Path | Request | Response |
|--------|------|---------|----------|
| GET | `/api/progress` | — | `{running, step, detail, error, result_msg}` |
| GET | `/api/chart-data?mode=` | — | `[{date, projects: [...]}]` |

**Project Management:**

| Method | Path | Request | Response |
|--------|------|---------|----------|
| POST | `/api/ignore` | `{name}` | `{ok, ignored: [names]}` |
| POST | `/api/restore` | `{name}` | `{ok, ignored: [names]}` |
| POST | `/api/archive` | `{name}` | `{ok, archived: [names]}` |
| POST | `/api/unarchive` | `{name}` | `{ok, archived: [names]}` |

**Thread Management:**

| Method | Path | Request | Response |
|--------|------|---------|----------|
| POST | `/api/resolve-thread` | `{project, text}` | `{ok}` |

**What's Next Item Management:**

| Method | Path | Request | Response |
|--------|------|---------|----------|
| POST | `/api/item-action` | `{key, action, target_project?}` | `{ok}` |

**Dev State:**

| Method | Path | Request | Response |
|--------|------|---------|----------|
| POST | `/api/dev-state/<idx>` | `{dev_state}` | `{ok, dev_state}` |
| POST | `/api/ai-assess-state/<idx>` | — | `{dev_state, reason}` |

**AI Integration:**

| Method | Path | Request | Response |
|--------|------|---------|----------|
| GET/POST | `/api/ai-config` | `{api_url?, api_key?, model?}` | `{ok, ...config}` |
| POST | `/api/enrich/<idx>` | — | `{ok, narrative}` |
| POST | `/api/verify-categories` | — | `{ok}` |
| POST | `/api/classify-unmatched` | — | `{ok, total, classified, results}` |

**Chat Management:**

| Method | Path | Request | Response |
|--------|------|---------|----------|
| POST | `/api/dismiss-chat` | `{filename}` | `{ok, dismissed_count}` |
| POST | `/api/restore-chat` | `{filename}` | `{ok, dismissed_count}` |
| POST | `/api/assign-chat` | `{filename, project}` | `{ok, assigned_to}` |
| POST | `/api/dismiss-chat/bulk` | `{filenames: [...]}` | `{ok, dismissed_count}` |

**Settings:**

| Method | Path | Request | Response |
|--------|------|---------|----------|
| GET/POST | `/api/settings` | `{timezone?, api_key?, api_url?, model?}` | `{ok, ...}` or `{error}` |

**Upload & Export:**

| Method | Path | Request | Response |
|--------|------|---------|----------|
| POST | `/upload` | multipart/form-data | `{ok, message}` |
| GET | `/generate-pdf` | — | PDF file download |

---

## Data Model

### Project Object
```python
{
    'name': str,
    'file_path': str,             # Path to PROJECT_STATUS.md
    'project_path': str,          # Project directory
    'repo': str,                  # GitHub user/repo
    'category': str,              # Raw category
    'category_group': str,        # Normalized (Church, School, Product, etc.)
    'progress': int,              # 0-100
    'status': str,                # Not Started, In Progress, Beta, Complete, etc.
    'dev_state': str,             # test, refine, continue, or empty
    'has_repo': str,              # Yes/No
    'has_github_repo': bool,      # Computed
    'last_worked': str,           # YYYY-MM-DD
    'last_synced': str,           # YYYY-MM-DD
    'summary': str,               # Description from status file
    'narrative': str,             # AI-generated or summary-derived
    'features': [str],            # What's Working items
    'not_working': [str],         # What's Not Working items
    'blockers': [str],            # Blockers
    'next_steps': [str],          # Next Steps
    'open_questions': [str],      # Design Questions from tables
    'progress_log': [dict],       # Dated entries from Progress Log section
    'git_commits': [dict],        # Recent commits from git history
    'timeline': [dict],           # Merged timeline (progress + git + chat)
    'open_threads': [(str,str)],  # (type, text) — all unfinished items
    'chat_conversations': int,    # Number of chat files that mentioned this project
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

### Background Task State
```python
{
    'running': bool,
    'step': str,       # scanning, parsing, reading_chat, matching_chat, ai_enrichment, ai_classify, building, done
    'detail': str,     # Human-readable progress message
    'error': str,      # Error message if failed
    'result_msg': str, # Summary message on completion
}
```

### Chat Conversation (extracted from JSON)
```python
{
    'filename': str,   # Conversation name (sanitized) + .json extension
    'content': str,    # Full text of all messages (Human: ... \n\n Assistant: ...)
    'date': datetime,  # Extracted from created_at/updated_at/date/timestamp fields
}
```

### Initiative Classification Result
```python
{
    'idx': int,             # Index in unmatched_chats list
    'filename': str,        # Chat filename
    'date': str,            # YYYY-MM-DD
    'excerpt': str,         # First 150 chars
    'action': str,          # 'match', 'new', 'skip'
    'initiative': str,      # Project/initiative name
}
```

### Dismissed Chats File
```python
{
    'dismissed': ['filename1.json', 'filename2.json', ...]  # Set of dismissed filenames
}
```

### Initiative Assignments (in initiatives.json)
```python
{
    'assigned': {
        'filename.json': {
            'project': 'Project Name',
            'assigned_at': '2026-02-12 06:09 PM CST'
        }
    }
}
```

### Settings File
```python
{
    'timezone': 'America/Chicago'  # IANA timezone identifier
}
```

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
| **Dev State** | [test/refine/continue] |

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

## Color Coding Reference

### Progress Colors
| Progress | Color |
|----------|-------|
| > 75% | Green (#2ECC71) |
| 50-75% | Blue (#3498DB) |
| 25-49% | Yellow (#F1C40F) |
| < 25% | Red (#E74C3C) |

### Dev State Colors
| State | Color | Badge | Card Border |
|-------|-------|-------|-------------|
| test | Orange (#E67E22) | Orange bg/text | Left orange border |
| refine | Blue (#3498DB) | Blue bg/text | Left blue border |
| continue | Red (#E74C3C) | Red bg/text | Left red border |

### Category Colors
| Category | Border | Badge (Light) | Badge (Dark) |
|----------|--------|---------------|--------------|
| Church | Purple (#7E57C2) | Purple on lavender | Purple on deep purple |
| School | Blue (#1E88E5) | Blue on light blue | Light blue on navy |
| Product | Green (#43A047) | Green on light green | Light green on dark green |
| Infrastructure | Orange (#EF6C00) | Dark orange on peach | Orange on dark brown |
| Personal | Pink (#C2185B) | Pink on light pink | Pink on dark red |
| Research | Teal (#00897B) | Teal on light cyan | Teal on dark cyan |

---

## Theming

Light and dark themes via CSS custom properties on `[data-theme]`. Persisted in localStorage, applied before paint to prevent flash. Toggle button in top bar on every page. All category colors, dev state badges, and thread type tags have dark mode variants.

---

## Dependencies

### Python
```
flask
reportlab>=4.0.0
matplotlib>=3.7.0
numpy>=1.24.0
```

### Standard Library (no install needed)
- `zoneinfo` (Python 3.9+) — timezone support
- `json`, `threading`, `urllib`, `tempfile`, `zipfile`

### System
- Python 3.9+ (for `zoneinfo`)
- Git (commit history + remote detection)
- macOS or Linux

### Optional
- Anthropic API key (for AI enrichment + classification)

---

## File Structure

```
~/claudesync2/
├── web_app.py                  # Flask dashboard (~3400 lines)
├── generate_status_pdf.py      # Scanner, parser, chat matcher, PDF renderer (~1400 lines)
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
~/.claudesync_ignored.json          # Hidden project names (set)
~/.claudesync_resolved.json         # Resolved thread keys (set)
~/.claudesync_archived.json         # Archived project names (set)
~/.claudesync_ai.json               # {api_url, api_key, model}
~/.claudesync_import_meta.json      # {last_import, last_file}
~/.claudesync_item_actions.json     # {item_key: {action, target_project?}}
~/.claudesync_initiatives.json      # {last_classified, results: [...], assigned: {...}}
~/.claudesync_dismissed_chats.json  # {dismissed: [filenames]}
~/.claudesync_settings.json         # {timezone}
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

## Recent Changes (v7.0 → v7.1)

### This Session (2026-02-12)

1. **Non-blocking startup** — Server starts instantly, projects load in background. No more waiting before the browser opens.

2. **Sticky progress banner** — Moved to right below top bar, `position: sticky`, visible while scrolling. Auto-shows on page load if background task is running.

3. **API key save confirmation** — "Saved!" green flash with 800ms delay in both the AI prompt modal and Settings page. Error state: "Failed — try again".

4. **Settings page (`/settings`)** — Replaced the AI Settings modal with a full settings page combining:
   - Timezone configuration (Central US default, DST-aware)
   - AI API key, URL, and model
   - Scan paths
   - Single "Save All Settings" button with visible feedback

5. **Category color-coding** — Every project card now has:
   - Colored left border by category (6 colors)
   - Category badge next to project name (uppercase, small)
   - Full dark mode support for all category colors

6. **Timezone-aware timestamps** — All dashboard-generated timestamps (last import, last classified, assignment times) use the configured timezone with format `YYYY-MM-DD HH:MM AM/PM TZ`.

7. **Chat import overhaul** — Complete rewrite of `load_chat_files()`:
   - Parses Claude.ai JSON exports with multiple conversations in a single file
   - Handles wrapper objects, JSONL, multiple date formats
   - Extracts messages from Claude.ai `sender/text` and OpenAI `role/content` formats
   - Accepts `.jsonl`, `.csv`, `.yaml` files from zip archives
   - Extraction stats printed to console

8. **Unmatched chat management** — Full CRUD on the Unmatched Conversations page:
   - Assign dropdown (assigns to project, auto-dismisses)
   - Dismiss button (per-conversation, with fade animation)
   - Restore button (for dismissed/assigned chats)
   - "Dismiss All Skipped" bulk action with confirmation
   - Dismissed/Assigned section (collapsed by default)
   - Green flash confirmation on assignment

---

## Out of Scope (For Now)

1. **Automatic Claude.ai upload** — user must manually upload PDF
2. **Real-time sync** — PDF/dashboard is point-in-time snapshot
3. **Progress auto-calculation** — user sets progress % manually
4. **Multi-user support** — single developer only
5. **Cloud storage** — all data is local, nothing leaves the machine
6. **Windows support** — untested
7. **Mobile-optimized layout** — responsive but not mobile-first

---

*Last updated: 2026-02-12*
*Version: 7.1*
