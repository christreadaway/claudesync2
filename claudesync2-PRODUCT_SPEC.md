# Claude Sync 2 - Product Specification

**Repository:** `claudesync2`  
**Filename:** `claudesync2-PRODUCT_SPEC.md`  
**Last Updated:** 2026-02-16 at 15:10 UTC

---

## What This Is

**Claude Sync 2** - Sync project status between Claude Code and Claude Chat

## Who It's For

**Primary Users:** Developers using Claude

## Tech Stack

Node.js, TypeScript, CLI tool

---

## Core Features

The following features have been implemented based on development sessions:

1. "Read these transcript files and find every time I added personal rules or instructions to ~/.claude/CLAUDE.md: [paste the file list]"
2. - Added "Saved!" confirmation for API key
3. - Added Central Time timezone support using zoneinfo.ZoneInfo('America/Chicago')
4. - Added get_recent_commits_with_dates() to get real git commit dates
5. - Added loading overlay blocking UI during processing
6. - Added threading.Lock() to _project_cache
7. - Built comprehensive chat history processing pipeline for Claude.ai exports
8. - Created _get_projects() helper for thread-safe reads
9. - Daily activity summaries in natural language (e.g., "Added 3 features: X, Y, Z. Fixed 1 bug.")
10. - Implemented Ignore and Prioritize buttons across all thread views
11. - Priority-sorted: Blockers > Next Steps > Open Questions > Not Yet Built
12. 1. **parse_export()** - Opens .dms/.zip files, finds conversations.json, extracts each conversation with created_at/updated_at timestamps
13. Added the Project Sync snippet to a new CLAUDE.md file. This will remind Claude to output a session summary block at the end of each conversation that you can paste into your Project Status doc.
14. Added the Project Sync snippet to global Claude config (~/.claude/CLAUDE.md). Removed the duplicate project-level file so the instruction lives in one place and applies everywhere.
15. Added the Project Sync snippet to the global Claude config at ~/.claude/CLAUDE.md. This instruction will now apply across all projects, prompting a session summary at the end of each conversation.
16. Built complete production-ready MCP server in TypeScript. Five tools: list_events, search_events, list_work_orders, get_room_availability, list_locations. JWT authentication implemented.
17. CHAT HISTORY PROCESSING PIPELINE - IMPLEMENTED:
18. Claude: No - the chat history ZIP processing is NOT implemented yet. The UI has all the plumbing but load_projects() accepts chat_history_path and does nothing with it.
19. Claude: The issue is that the claude-project-sync tool needs to be run on the grantfinder repository first to generate its CLAUDE.md. The tool we built is currently only in this repository.
20. Claude: You're right. According to the v5 spec we just rebuilt from:
21. Created /home/user/claudesync2/CLAUDE.md with the 6 PII prevention rules
22. Created PORTFOLIO_INDEX.md with structure for all 12 projects
23. Created StatusLine class with updating cyan line showing real-time progress:
24. Created requirements.txt with Python dependencies for project
25. Current state: Built, ready to push to GitHub

---

## Technical Implementation

Key technical details from implementation:

- - Bonuses for conversation title matches and descriptive language
- - Fixed conversation date attribution (now uses real dates from chat exports and git commits)

---

## Architecture & Design Decisions

Key decisions made during development:

- Tuesday deadline. Template approach, NW Austin SEO focus.
- Set up WordPress on SiteGround. Chose SiteGround for balance of performance and SEO capabilities. Real estate agent site for wife.
- The repo was reset. Let me rebuild everything with the correct architecture - CLAUDE.md for instructions only, status in PROJECT_STATUS files and PDF only.
- Claude: [Asked clarification about password-based security approach - OS keychain vs encrypted file vs simple file permissions]
- - Refactored architecture to store all state in repo data/ directory
- User: I have introduced files from Claude AI to remedy issues found with the claude-project-sync repository. I just decided to start anew. Please make this work.
- Claude: You're right. The current approach dumps everything into one CLAUDE.md, but for persistent specs/progress tracking, separate files make more sense.


---

## Development History

Full session-by-session development history is maintained in `SESSION_NOTES.md`.

This specification is automatically updated alongside session notes to reflect:
- New features implemented
- Technical decisions made
- Architecture changes
- Integration updates

---

## Updating This Spec

At the end of each Claude Code session, this spec is updated automatically when you say:
> "Append session notes to SESSION_NOTES.md"

Claude will:
1. Update `SESSION_NOTES.md` with detailed session history
2. Update `claudesync2-PRODUCT_SPEC.md` with new features/decisions
3. Commit both files together

**Never manually edit this file** - it's maintained automatically from session notes.

