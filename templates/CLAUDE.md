# Claude Code Global Instructions

> **IMPORTANT:** This file contains INSTRUCTIONS for Claude Code behavior.
> It does NOT contain project status, progress, or history.
> Status data belongs in PROJECT_STATUS.md files and PDF reports.

---

## Commit Message Guidelines

Write meaningful commit messages that describe WHAT was built, not mechanical changes. The PDF dashboard extracts these to show recent work.

**Good commits (will appear in PDF):**
- "Add user authentication with Google OAuth"
- "Fix notification timing - now triggers on schedule change"
- "Implement 2-column dashboard layout for project status"

**Bad commits (filtered out):**
- "Add files via upload"
- "Initial commit"
- "Fix typo"
- "WIP"
- "Update README"

---

## End-of-Session Protocol

When the user says "done", "wrap up", "sync", or ends the session:

1. **Update PROJECT_STATUS.md** in the current project directory:
   - Update "What's Working" with new features built
   - Add a progress log entry with today's work
   - Update progress percentage if appropriate

2. **Commit with meaningful message** describing what was built

3. **Remind the user** to regenerate the PDF:
   ```
   To update your dashboard:
   python3 ~/claude-project-sync/generate_status_pdf.py
   open ~/claude-project-sync/status_report_*.pdf
   ```

---

## Updating PROJECT_STATUS.md

### What's Working Section (IMPORTANT)

Keep this section current - it's the primary source for features in the PDF:

```markdown
### What's Working
- User authentication with Google OAuth
- Event calendar with recurring events
- Push notifications for schedule changes
- Admin dashboard for managing users
```

### Progress Log Entry

Append a new entry for each session:

```markdown
### [YYYY-MM-DD]

**What was built:**
- [specific features in plain language]

**What was figured out:**
- [problems solved, decisions made]

**Still stuck on:**
- [blockers, unknowns]

**Next time:**
- [recommended next actions]
```

---

## Writing Style

Write like a project manager, not a changelog:

**Good:**
> Got notifications working. Parents now get alerts when teachers post. Debugged Android permissions - manifest was missing RECEIVE_BOOT_COMPLETED.

**Bad:**
> Implemented NotificationService.sendPush(). Fixed FCM config.

---

## Quick Commands

```bash
# Generate PDF dashboard (scans all projects, all branches)
python3 ~/claude-project-sync/generate_status_pdf.py

# Generate with debug output
python3 ~/claude-project-sync/generate_status_pdf.py --verbose

# Initialize new project status
python3 ~/claude-project-sync/init_project_status.py ~/path/to/project --name "Name" --category Personal

# Auto-detect repos for all projects
python3 ~/claude-project-sync/update_repos.py

# Open the PDF (Mac)
open ~/claude-project-sync/status_report_$(date +%Y-%m-%d).pdf
```

---

## Key Reminders

1. **Commits feed the PDF** - Write meaningful commit messages; garbage commits are filtered out
2. **"What's Working" matters** - Keep this section updated with actual features
3. **All branches are scanned** - Work on `claude/*` branches will appear in the PDF
4. **Status goes in PROJECT_STATUS.md** - Never put status data in this file

---

*Claude Project Sync - github.com/christreadaway/claudesync2*
*If this saves you time: Venmo @ctreada*
