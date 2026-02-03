# Claude Code Global Instructions

This file provides global instructions for Claude Code sessions. Place it at `~/.claude/CLAUDE.md`.

---

## Project Sync Protocol

At the **end of every session**, update the project's `PROJECT_STATUS.md` file with:

1. **What was built** - Concrete deliverables from this session
2. **What was figured out** - Decisions made, problems solved
3. **Still stuck on** - Remaining challenges
4. **Next time** - What to work on next session

### Update Format

```markdown
### [Today's Date]

**What was built:**
- [List items]

**What was figured out:**
- [List items]

**Still stuck on:**
- [List items]

**Next time:**
- [List items]
```

---

## Reusable Asset Detection

When creating new components that could be reused, flag them in the project's `PROJECT_STATUS.md` under the "Reusable Assets" section:

| Asset | Description | Tags |
|-------|-------------|------|
| `path/to/file.js` | Brief description | tag1, tag2 |

Common reusable patterns to watch for:
- Authentication flows
- Notification systems
- UI component libraries
- API integration patterns
- Database utilities

---

## Progress Tracking

Update the **Progress** percentage in the metadata section when significant milestones are reached:
- 0-25%: Planning/Setup
- 25-50%: Core development
- 50-75%: Feature complete, testing
- 75-90%: Bug fixes, polish
- 90-100%: Shipping/Shipped

---

## Sync Reminders

- The user syncs between Claude Code and Claude.ai via PDF upload or copy/paste
- Keep status updates concise but complete
- Write in natural language, not jargon
- Include enough context that Claude.ai can understand without access to the codebase

---

## Quick Commands

```bash
# Generate PDF dashboard
python ~/claude-project-sync/generate_status_pdf.py

# Initialize new project status
python ~/claude-project-sync/init_project_status.py /path/to/project --name "Name" --category Category

# Copy status to clipboard (Mac)
cat PROJECT_STATUS.md | pbcopy

# Rebuild asset registry
python ~/claude-project-sync/sync_history.py --assets
```

---

*Claude Project Sync - github.com/christreadaway/claudesync2*
