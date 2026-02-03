# Claude Code Global Instructions

> **IMPORTANT:** This file contains INSTRUCTIONS for Claude Code behavior.
> It does NOT contain project status, progress, or history.
> Status data belongs in PROJECT_STATUS.md files and PDF reports.

---

## End-of-Session Protocol

When the user says "goodbye", "thanks", "done", "wrap up", or "sync":

1. **Update PROJECT_STATUS.md** in the current project directory with:
   - What was built
   - What was figured out
   - Still stuck on
   - Next time

2. **Remind the user** to sync with Claude.ai:
   ```
   To sync with Claude.ai:
   - Upload the PDF: ~/claude-project-sync/status_report_*.pdf
   - Or copy/paste: cat PROJECT_STATUS.md | pbcopy
   ```

---

## Status Update Format

When updating PROJECT_STATUS.md, append this format:

```markdown
### [YYYY-MM-DD]

**What was built:**
- [specific files, features in plain language]

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

## Reusable Asset Detection

When creating components that could be reused, note them in PROJECT_STATUS.md:

| Asset | Description | Tags |
|-------|-------------|------|
| `src/auth/oauth.js` | Google OAuth flow | auth, google |

---

## Quick Commands

```bash
# Generate PDF dashboard
python3 ~/claude-project-sync/generate_status_pdf.py

# Initialize new project status
python3 ~/claude-project-sync/init_project_status.py /path --name "Name" --category School

# Copy status to clipboard (Mac)
cat PROJECT_STATUS.md | pbcopy

# Build asset registry
python3 ~/claude-project-sync/sync_history.py --assets
```

---

## Key Reminders

1. **Claude.ai cannot write local files** - user must save manually
2. **Status goes in PROJECT_STATUS.md** - not in this file
3. **PDF is the visual dashboard** - upload to Claude.ai for context

---

*Claude Project Sync - github.com/christreadaway/claudesync2*
*If this saves you time: Venmo @ctreada*
