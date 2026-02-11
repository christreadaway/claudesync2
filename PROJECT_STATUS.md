# PROJECT_STATUS: Claude Project Sync v2

---

## Metadata

| Field | Value |
|-------|-------|
| **Project Name** | Claude Project Sync v2 |
| **Repository** | christreadaway/claudesync2 |
| **Category** | Infrastructure |
| **Progress** | 60% |
| **Status** | Active |
| **Last Worked** | 2026-02-11 |
| **Has GitHub Repo** | Yes |
| **Last Synced to Claude.ai** | 2026-02-04 |

---

## Current State

### What's Working
- Web dashboard on localhost:5111 with full project portfolio view
- Clickable stat cards drill into /view/projects, /events, /threads, /blockers
- Project detail pages with full timeline and open threads
- Chat history upload and fuzzy matching to projects
- AI enrichment via Anthropic API (Haiku/Sonnet/Opus model selector)
- Bulk AI analysis checkbox on upload ("Analyze chats with AI")
- Loading overlay prevents double-clicks during Load & Refresh / PDF gen
- Archive/unarchive projects, ignore/restore EOL projects, resolve threads
- Dark/light theme with persistence
- PDF generation with category grouping, timeline, threads, cross-project summary
- Import metadata tracking (last import timestamp + filename)
- All project repos cloned to both Mac and Windows PC
- PROJECT_STATUS.md files initialized in all projects
- init_project_status.py, update_repos.py, sync_history.py CLI tools

### What's Not Working
- Daily PDF report automation (LaunchAgent plist created but not tested)
- No overarching "what's next" view across all projects
- No AI verification of project categorization

### Blockers
- None currently

---

## Progress Log

### 2026-02-11 (Claude Code — Dashboard v5 Features)
**What was built:**
- Loading overlay with spinner for Load & Refresh and Generate PDF (prevents double-clicks)
- AI chat analysis: bulk enrichment checkbox in upload modal, shared _call_ai() helper
- Model dropdown (Haiku 4.5 default, Sonnet 4.5, Opus 4.6) with sensible defaults
- Clickable stat cards linking to 4 drill-down list views
- /view/projects with Archive/Unarchive buttons (Active + Archived sections)
- /view/events with all timeline events, newest first, typed tags (Commit/Chat/Log)
- /view/threads with Resolve buttons
- /view/blockers filtered to blockers only
- Import metadata persistence (timestamp + filename shown in upload modal)
- Fixed Jinja2 auto-escaping bug that showed raw HTML on list view pages
- Deleted stale PRODUCT_SPEC_2026-02-03_023152.md backup
- Rewrote PRODUCT_SPEC.md from v1 (CLI-only) to v5 (full web dashboard)

**What was figured out:**
- Jinja2 auto-escapes {{ content }} by default — need |safe filter for pre-built HTML
- Archived projects should be separate from Ignored (archive = user choice, ignore = EOL dismissal)

**Next time:**
- Overarching "what's next" view across all projects
- AI verification of project categorization/placement
- Reassign/ignore actions on individual items

### 2026-02-04 (Claude.ai Chat — Sacramental Records Integration)
**Source:** Claude.ai project chat, current session
- Integrated full Sacramental Records Product Spec v1.0 into PROJECT_STATUS_SacramentalRecords.md on Mac via MCP
- Spec built from parish secretary interview at [Parish Name] Catholic Church ([City], [State]) + physical register page analysis
- Also integrated Google Drive strategy docs (blockchain/Vaticoin vision for v3-v5)
- Upgraded sacramental records status from "Planning 10%" to "Spec Complete — Ready for Development 25%"
- Confirmed all 13 projects have substantive PROJECT_STATUS.md files on Mac (Claude Code had already created them)
- Identified gap: Claude.ai chat histories from separate projects not yet flowing into status files
- Decision: Need to go into each separate Claude.ai project to extract chat forensics — this project's chats only cover claudesync2 infrastructure

### 2026-02-04 (Claude.ai Chat — PC MCP Health Check)
**Source:** Claude.ai project chat "Configuring MCP settings on PC"
- User moved to PC to verify MCP still functional
- Provided health check steps: verify config, confirm repo exists, git pull from GitHub
- PC MCP confirmed working from prior session

### 2026-02-04 (Claude.ai Chat — Project Scan & Initialization via Claude Desktop)
**Source:** Claude.ai project chat "Setting up claudesync2 project initialization"
- MCP confirmed working on Mac — Claude Desktop could see all 12 project directories
- Scanned every project directory, cataloged files in each
- Fixed 3 corrupted Repository fields in PROJECT_STATUS.md (ministrylife, desmond, catholicevents had shell commands instead of repo names)
- Created missing PROJECT_STATUS.md files for claudesync2 and imessage-dashboard-v6
- Discovered sacramentalrecords project exists but has no repo cloned to Mac and no MCP access — needs to be added to filesystem config
- User mentioned sacramental records has blockchain component for later, wanted to start with basics

### 2026-02-04 (Claude.ai Chat — Spec v6 + GLOBAL_CLAUDE.md + Sync Guide)
**Source:** Claude.ai project chat "Updating PDF spec with MCP federation changes"
- Updated product spec from v5 → v6 (PDF generated)
- Two new sections added: Section 5 (MCP Federation Layer) and Section 13 (Operational Workflow)
- Architecture upgraded from 2-tier to 3-tier: Local Filesystem → MCP Federation → Git Sync
- Environment capability matrix updated: Claude Desktop on both Mac and PC now shows full read/write via MCP
- Created GLOBAL_CLAUDE.md — global instructions file that Claude Code reads automatically via ~/.claude/CLAUDE.md symlink
- Created comprehensive Sync Setup & Workflow Guide (Part 1: first-time sync, Part 2: daily workflow)
- Key decisions: Option B chosen (single file with appended entries, not timestamped filenames), Mac pushes first then PC pulls
- Resolved open design question: all project directories confirmed in MCP config
- Added new open questions: auto-prompting, merge conflicts, master dashboard, watcher scripts

### 2026-02-04 (Claude.ai Chat — MCP Setup Mac + PC)
**Source:** Claude.ai project chat "Auto-populating status updates from Claude chats"
- User's original request: Claude.ai chat status updates should auto-populate the same files Claude Code writes to
- Three options proposed: (1) copy-paste terminal commands, (2) file download + watcher script, (3) MCP filesystem server
- Chose Option 3: MCP filesystem server as long-term play
- Mac setup: Created claude_desktop_config.json at ~/Library/Application Support/Claude/, pointed at local claudesync2 directory
- Mac troubleshooting: No hammer icon visible, no MCP logs initially, but server was actually running (confirmed via MCP log files)
- Switched to PC: Installed Node.js v24.13.0 (user initially got Docker instructions instead of Windows installer), created MCP config at %APPDATA%\Claude\claude_desktop_config.json
- PC troubleshooting: No hammer icon but server confirmed running in Developer settings (green "running" status)
- Cloned all 11 repos to PC
- PC MCP config expanded to include all 11 project directories
- Key insight: Hammer icon doesn't appear in current Claude Desktop version, but MCP tools work anyway — just ask Claude Desktop to list files
- Environment capability confirmed: Claude Code ✅, Claude Desktop PC ✅, Claude Desktop Mac ✅, Claude.ai browser ❌ (download/paste only)

### 2026-02-04 (Claude Code)
Set up MCP filesystem server on Mac. Claude Desktop can now read/write to all 12 project directories. Scanned all projects, fixed 3 corrupted Repository fields (ministrylife, desmond, catholicevents had shell commands instead of repo names). Created missing PROJECT_STATUS.md files for claudesync2 and imessage-dashboard-v6. Next: test daily PDF generation, start filling in real progress log entries for each project.

### 2026-02-03 (Claude Code)
Set up MCP filesystem server on Windows PC, cloned all GitHub repos to PC, connected Claude Desktop to local claudesync2 repo via MCP. Generated first status_report PDF. Created init_project_status.py and ran it across all projects.

### 2026-02-02 (Claude Code)
Initial PROJECT_STATUS.md files created across all project repos from Windows PC.

---

## Reusable Assets

| Asset | Description | Tags |
|-------|-------------|------|
| init_project_status.py | Script to initialize PROJECT_STATUS.md in any project | automation, setup |
| generate_status_pdf.py | Generates daily PDF status report across all projects | automation, reporting |
| update_repos.py | Pulls latest code from GitHub for all repos | automation, git |
| daily_status_report.sh | Shell script to run daily report | automation |
| com.ctreada.dailystatusreport.plist | macOS LaunchAgent for auto-running daily report | automation, macos |

---

## Notes

This is the backbone infrastructure project — it tracks everything else. The goal is to have Claude (Desktop, Code, or claude.ai) always know current project status by reading these files.

---

*Last updated: 2026-02-11*
