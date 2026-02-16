# Claude Code Instructions - ClaudeSync2

## About This Project
Infrastructure tool for syncing project status across all of Chris's repositories. Includes PDF status report generator, project status initialization scripts, portfolio index, and CLI for managing project context across Claude Code sessions. Central hub for tracking all projects.

## About Me (Chris Treadaway)
Product builder, not a coder. I bring requirements and vision — you handle implementation.

**Working with me:**
- Bias toward action — just do it, don't argue
- Make terminal commands dummy-proof (always start with `cd ~/claudesync2`)
- Minimize questions — make judgment calls and tell me what you chose
- I get interrupted frequently — always end sessions with clear handoff

## Tech Stack
- **Language:** TypeScript (CLI), Python (PDF generator, status scripts)
- **PDF Generation:** reportlab, matplotlib
- **CLI:** Node.js
- **Category:** Infrastructure

## File Paths
- **Always use:** `~/claudesync2/`
- **Never use:** `/Users/christreadaway/...`
- **Always start commands with:** `cd ~/claudesync2`

## PII Rules
❌ NEVER include: real names, email addresses, API keys, tokens, file paths with /Users/christreadaway → use ~/
✅ ALWAYS use placeholders

## Key Files
- `generate_status_pdf.py` — Generates portfolio PDF with charts from PROJECT_STATUS files
- `init_project_status.py` — Initializes PROJECT_STATUS.md for new projects
- `sync_all_status.py` — Scans all project dirs and updates status files
- `PORTFOLIO_INDEX.md` — Master index of all projects

## All Projects Tracked (15 repos)
**Infrastructure:** claudesync2, desmond, repodoctor, repodoctor2, claudecodearchiver
**Church:** catholicevents, ministryfair, sacramentalrecords
**School:** grantfinder, parentpoint, parentpointedu
**Product:** audioscribe, polygraph, vibecoach
**Personal:** personalcrm

## Git Branch Strategy
- Claude Code creates new branch per session
- Merge to main when stable
- Delete merged branches immediately
- NOTE: Has multiple unmerged feature branches — check before creating new ones

## Session End Routine

At the end of EVERY session — or when I say "end session" — do ALL of the following:

### A. Update SESSION_NOTES.md
Append a detailed entry at the TOP of SESSION_NOTES.md (most recent first) with: What We Built, Technical Details, Current Status (✅/❌/🚧), Branch Info, Decisions Made, Next Steps, Questions/Blockers.

### B. Update PROJECT_STATUS.md
Overwrite PROJECT_STATUS.md with the CURRENT state of the project — progress %, what's working, what's broken, what's in progress, next steps, last session date/summary. This is a snapshot, not a log.

### C. Commit Both Files
```
git add SESSION_NOTES.md PROJECT_STATUS.md
git commit -m "Session end: [brief description of what was done]"
git push
```

### D. Tell the User
- What branch you're on
- Whether it's ready to merge to main (and if not, why)
- Top 3 next steps for the next session

---
Last Updated: February 16, 2026
