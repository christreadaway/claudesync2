# Product Spec: Claude Project Sync

## Product Overview

**Product Name:** Claude Project Sync

**Problem Statement:** Developers using Claude Code (CLI) work across multiple projects, but Claude.ai (web interface) has no visibility into project status, progress, or recent work. Each new Claude.ai conversation starts from zero context. There's no bridge between the two environments.

**Solution:** A local-first system that:
1. Maintains per-project status files (`PROJECT_STATUS.md`)
2. Generates a visual PDF dashboard from real project data
3. Allows uploading the PDF to Claude.ai for instant context

---

## User Story

**Who:** A developer managing 5-15+ projects, using Claude Code for development work and Claude.ai for planning, research, or conversation.

**What they're trying to accomplish:**
- Keep Claude.ai informed about what's been built across all projects
- Quickly share project status without manual summarization
- Track progress across multiple repositories
- Maintain continuity between Claude Code sessions and Claude.ai conversations

**Workflow:**
1. Developer works in Claude Code on various projects (commits happen on `claude/*` branches)
2. At any time, developer runs `python3 generate_status_pdf.py`
3. PDF is generated with all project statuses and recent commits
4. Developer uploads PDF to Claude.ai conversation
5. Claude.ai now has full context on all projects

---

## Core Functionality

### 1. Project Status Files (`PROJECT_STATUS.md`)

Each project directory contains a `PROJECT_STATUS.md` file with:
- Project metadata (name, repo, category, progress %, status)
- "What's Working" section for documenting features
- Progress log for session-by-session updates

**Critical Design Decision:** `CLAUDE.md` contains ONLY behavioral instructions for Claude Code. Status data belongs ONLY in `PROJECT_STATUS.md` and PDF reports. These must never be mixed.

### 2. PDF Dashboard Generator (`generate_status_pdf.py`)

Generates a 2-page PDF report:

**Page 1: Dashboard**
- Project progress bar chart (all projects, sorted by progress)
- Pie chart showing GitHub repo status
- Bar chart showing projects by category
- Tables listing projects with/without repos

**Page 2: Recent Work (2-column layout)**
- Each project shows name and progress percentage
- Last 5 meaningful commits from git history
- Scans ALL branches (including `claude/*` feature branches)
- Filters out garbage commits

### 3. Project Initializer (`init_project_status.py`)

CLI tool to create `PROJECT_STATUS.md` in a project:
```bash
python3 init_project_status.py ~/myproject --name "My Project" --category School
```

Options:
- `--name` (required): Project display name
- `--category`: Infrastructure, School, Church, Product, Research, Personal
- `--repo`: GitHub repository (user/repo format)
- `--progress`: Initial progress percentage (0-100)
- `--status`: Initial status string

### 4. Repository Updater (`update_repos.py`)

Auto-detects GitHub repos from local git directories:
```bash
python3 update_repos.py          # Auto-detect all
python3 update_repos.py --list   # Show current status
python3 update_repos.py --project "Name" --repo "user/repo"  # Manual update
```

Reads `git remote get-url origin` from each project directory and updates the `PROJECT_STATUS.md` files automatically.

---

## Inputs and Outputs

### Inputs

| Input | Source | Description |
|-------|--------|-------------|
| `PROJECT_STATUS.md` files | Each project directory | Metadata and status |
| Git commit history | Local git repos | Recent work (all branches) |
| Git remote URLs | Local git repos | Repository identification |

### Outputs

| Output | Format | Description |
|--------|--------|-------------|
| PDF Dashboard | `~/claude-project-sync/status_report_YYYY-MM-DD.pdf` | Visual report for Claude.ai |
| Console output | Text | Progress and debug info |

### What the User Sees

1. **On generation:** Console shows projects found, commits extracted
2. **In PDF Page 1:** Charts and tables summarizing all projects
3. **In PDF Page 2:** 2-column layout with project names and last 5 commits each
4. **In Claude.ai:** Full context after uploading PDF

---

## Business Rules and Logic

### Commit Filtering

**Skip these patterns** (case-insensitive):
- `add files via upload`
- `initial commit`, `first commit`, `init commit`
- `create readme`, `update readme`
- `delete `, `remove `
- `merge branch`, `merge pull request`
- `wip`, `fix typo`, `minor fix`, `small fix`, `quick fix`
- `bump version`, `update dependencies`, `update package`
- `lint fix`, `format code`, `cleanup`, `refactor`

**Additional filters:**
- Skip commits shorter than 15 characters
- Scan ALL branches (`git log --all`)
- Return first 5 meaningful commits found

### Project Discovery

**Scan locations:**
- Home directory (`~`)
- Max depth: 2 levels

**Skip directories:**
- `node_modules`, `.git`, `__pycache__`, `venv`, `.venv`
- `dist`, `build`, `.next`, `coverage`
- `Library`, `.Trash`, `Applications`
- `Pictures`, `Music`, `Movies`, `Documents`

### Repository Detection

A project "has a repo" if:
- `Has GitHub Repo` field is "Yes" AND
- `Repository` field is not empty AND
- `Repository` field does not contain "not yet" or similar placeholder text

### Progress Color Coding

| Progress | Color |
|----------|-------|
| > 75% | Green (#2ECC71) |
| 50-75% | Blue (#3498DB) |
| 25-49% | Yellow (#F1C40F) |
| < 25% | Red (#E74C3C) |

---

## Data Requirements

### PROJECT_STATUS.md Schema

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

## Current State

### What's Working
- [Feature 1]
- [Feature 2]

### What's Not Working
- [Issue 1]

### Blockers
- [Blocker 1]

## Progress Log

### [YYYY-MM-DD]
**What was built:**
- [Deliverable]

**What was figured out:**
- [Learning]

**Still stuck on:**
- [Challenge]

**Next time:**
- [Next step]
```

### Parsed Data Structure

```python
project = {
    'name': str,
    'file_path': str,
    'project_path': str,
    'repo': str,
    'category': str,
    'progress': int,
    'status': str,
    'has_repo': str,
    'has_github_repo': bool,
    'features': list[str],      # From "What's Working"
    'recent_commits': list[str] # From git log --all
}
```

---

## Integrations and Dependencies

### Python Dependencies

```
reportlab>=4.0.0
matplotlib>=3.7.0
numpy>=1.24.0
```

### System Dependencies

- Python 3.8+
- Git (for commit history and remote detection)
- macOS or Linux (Windows untested)

### External Integrations

| System | Integration Type | Purpose |
|--------|-----------------|---------|
| Git | Local CLI | Read commit history, detect remotes |
| GitHub | URL parsing only | Extract user/repo from remote URLs |
| Claude.ai | Manual PDF upload | Provide context to conversations |

**No API keys or authentication required.**

---

## Out of Scope (For Now)

1. **Automatic Claude.ai upload** - User must manually upload PDF
2. **Real-time sync** - PDF is point-in-time snapshot
3. **Claude Code hooks** - No automatic triggering on session end
4. **Progress auto-calculation** - User must manually set progress %
5. **Multi-user support** - Single developer use case only
6. **Cloud storage** - All data is local
7. **Windows support** - Untested, may work
8. **Automatic PROJECT_STATUS.md updates** - Claude Code doesn't auto-update status files yet

---

## Open Design Questions

1. **Auto-update trigger:** Should there be a Claude Code hook that auto-updates PROJECT_STATUS.md at session end?

2. **Progress calculation:** Can progress % be auto-calculated from commits, test coverage, or other metrics?

3. **Scheduled generation:** Should PDF auto-generate daily via launchd/cron?

4. **Deep project scanning:** Should we scan deeper than 2 levels for monorepos?

5. **Commit deduplication:** Same commit message across branches shows once or multiple times?

6. **Feature extraction:** "What's Working" section is often empty - better source for features?

---

## Success Criteria

### Functional Success

- [ ] `init_project_status.py` creates valid PROJECT_STATUS.md files
- [ ] `update_repos.py` correctly detects git remotes for all projects
- [ ] `generate_status_pdf.py` finds all PROJECT_STATUS.md files (max depth 2)
- [ ] PDF shows commits from ALL branches, not just main
- [ ] Garbage commits are filtered out
- [ ] PDF renders correctly in Preview and Claude.ai

### User Experience Success

- [ ] New project setup takes < 30 seconds
- [ ] PDF generation takes < 10 seconds for 15 projects
- [ ] PDF upload to Claude.ai provides useful context
- [ ] 2-column layout fits 10+ projects on page 2

### Data Quality Success

- [ ] At least 3-5 meaningful commits shown per active project
- [ ] No "Add files via upload" or "Initial commit" garbage
- [ ] Projects with no meaningful commits show "No recent work logged"

---

## File Structure

```
~/claude-project-sync/
├── generate_status_pdf.py    # Main PDF generator
├── init_project_status.py    # Project initializer
├── update_repos.py           # Batch repo updater
├── requirements.txt          # Python dependencies
├── .gitignore               # Ignore __pycache__, PDFs
├── templates/
│   ├── CLAUDE.md            # Instructions-only template
│   └── PROJECT_STATUS.md    # Status file template
├── PRODUCT_SPEC.md          # This document
└── status_report_*.pdf      # Generated reports (gitignored)
```

---

## Quick Start for Developers

```bash
# Clone and setup
git clone https://github.com/christreadaway/claudesync2.git ~/claude-project-sync
cd ~/claude-project-sync
pip3 install -r requirements.txt

# Initialize a project
python3 init_project_status.py ~/myproject --name "My Project" --category Personal

# Auto-detect repos for all projects
python3 update_repos.py

# Generate PDF
python3 generate_status_pdf.py

# View PDF
open ~/claude-project-sync/status_report_$(date +%Y-%m-%d).pdf
```

---

*Last updated: 2026-02-03*
*Version: 1.0*
