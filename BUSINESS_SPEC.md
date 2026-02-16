# ClaudeSync2 — Business Product Spec
**Version:** 2.0 | **Date:** 2026-02-16 | **Repo:** github.com/christreadaway/claudesync2

---

## 1. Problem Statement
Developers using Claude Code across multiple repositories lose significant time (6+ hours/week) to context resets at the start of each session. Claude Code doesn't remember what happened in previous sessions, what decisions were made, what's broken, or what the next logical step is. There's also no centralized view of project status across a portfolio of repositories — each project exists in isolation with no cross-project awareness.

## 2. Solution
A CLI tool and portfolio management system that maintains persistent context across Claude Code sessions. CLAUDE.md instruction files in each repository give Claude Code instant project awareness. SESSION_NOTES.md files capture end-of-session state. A central PORTFOLIO_INDEX.md tracks all projects with status, progress, and category metadata. A PDF generator creates portfolio status reports.

## 3. Target Users
- **Solo Developers** — Managing multiple repos, especially vibe coders who use Claude Code as primary development tool
- **Non-Technical Product Builders** — People who bring vision and requirements while AI handles implementation
- **Portfolio Managers** — Anyone tracking progress across multiple software projects

## 4. Core Features

### CLI Tool
- **`add`** — Register a project directory with the global registry
- **`global`** — Scan all registered projects, generate combined ~/.claude/CLAUDE.md with cross-project context
- **`status`** — Show current status of all registered projects

### Per-Repository Context Files
- **CLAUDE.md** — Project-specific instructions, tech stack, file path conventions, PII handling rules, session end routines, git branch strategies
- **SESSION_NOTES.md** — Append-only session log with technical details, decisions made, next steps, questions/blockers
- **PROJECT_STATUS.md** — Current state, progress percentage, category, key milestones

### Portfolio Management
- **PORTFOLIO_INDEX.md** — Single source of truth for all projects with: name, repo URL, category, progress %, status, tech stack
- **Categories:** Infrastructure, Church, School, Product, Personal
- **PDF Generator** — `generate_status_pdf.py` creates portfolio status reports from PROJECT_STATUS files

### PII Prevention
- Documented rules for handling sensitive data (church records, school enrollment, parish staff)
- Automated scanning for PII in committed files
- Category-based rules: public identity (OK), local file paths (remove), organizational references (generalize), personal contact info (remove)

## 5. Tech Stack
- **CLI:** TypeScript, compiled to dist/cli.js
- **PDF Generation:** Python (generate_status_pdf.py)
- **Template:** Markdown templates for PROJECT_STATUS.md
- **Distribution:** npm global install or direct node execution

## 6. Data & Privacy
- All data stored locally in project repositories and ~/.claude/
- No cloud sync or external data transmission
- PII prevention rules enforced across all managed projects
- Git history audited for PII leaks

## 7. Current Status
- **Deployed:** CLAUDE.md files committed to 15 repositories (ministryfair, catholicevents, claudesync2, parentpoint, parentpointedu, audioscribe, desmond, polygraph, personalcrm, grantfinder, sacramentalrecords, vibecoach, repodoctor, repodoctor2, claudecodearchiver)
- **Working:** CLI tool (add, global, status commands)
- **Working:** PDF generator for portfolio reports
- **Working:** PORTFOLIO_INDEX.md with 14 projects tracked
- **Cleaned:** PII removed from PROJECT_STATUS files (St. Theresa references generalized)

## 8. Business Model
- **Open Source** — Free tool for the Claude Code community
- **Part of Workflow** — Enables the broader product portfolio to move faster

## 9. Success Metrics
- Context reset time reduced from 10-20 minutes to <1 minute per session
- Weekly time savings: 6+ hours recovered
- Number of repositories with active CLAUDE.md files
- SESSION_NOTES.md adoption rate across projects

## 10. Open Questions / Next Steps
- Automated SESSION_NOTES.md generation (currently manual "append session notes" prompt)
- Dashboard web UI for portfolio visualization
- Integration with claude-code-archiver for automatic transcript ingestion
- Cross-project dependency tracking
- Automated CLAUDE.md updates based on codebase changes
