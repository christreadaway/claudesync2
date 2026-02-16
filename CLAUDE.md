# Claude Code Instructions - ClaudeSync2

## About This Project
Tool to sync Claude Code sessions and track progress across all my projects. Exports chat transcripts to PDF, generates PROJECT_STATUS.md files, and creates a portfolio overview. The irony: I built this tool to solve context loss... but haven't fully deployed it yet.

## About Me (Chris Treadaway)
Product builder, not a coder. I bring requirements and vision — you handle implementation.

**Working with me:**
- Bias toward action - just do it, don't argue
- Make terminal commands dummy-proof (always start with `cd ~/claudesync2`)
- Minimize questions - make judgment calls and tell me what you chose
- I get interrupted frequently - always end sessions with a handoff note
- Match my writing style: conversational, grounded in experience, uses em-dashes and numbered lists

## Tech Stack
- **Language:** TypeScript/Node.js
- **Key Libraries:** googleapis (Google Docs API), pdf-lib (PDF generation)
- **Data Flow:** Claude Code transcripts → JSON → Google Doc → PDF
- **Architecture:** CLI tool with commands: add, global, status, export

## File Paths
- **Always use:** `~/claudesync2/path/to/file`
- **Never use:** `/Users/christreadaway/...`
- **Always start commands with:** `cd ~/claudesync2`

## PII Rules (CRITICAL)
❌ NEVER include in any code output:
- Real institution names → use [Parish Name], [School Name]
- Staff/personal names → use [Staff Name]
- Email addresses → use user@example.com
- Phone numbers, addresses
- Local file paths with /Users/christreadaway → use ~/
- API keys, tokens, credentials

✅ ALWAYS use placeholders in square brackets

## My Other Repositories (Context for Portfolio)
This tool tracks 13 repos:
- **Infrastructure:** claudesync2, repodoctor, claude-project-sync
- **Church:** ministryfair, ministrylife, catholicevents, sacramentalrecords
- **School:** parentpoint, parentpointedu
- **Product:** polygraph, audioscribe, grantfinder, personalcrm, vibecoach, desmond

## Key Features
- Register projects with `add` command
- Run `global` to scan all projects and generate combined ~/.claude/CLAUDE.md
- Generate PROJECT_STATUS.md for each project
- Export to PDF with project summaries
- Track progress across all projects in one view

## CLI Commands
```bash
cd ~/claudesync2

# Register a project
node dist/cli.js add /path/to/project

# Generate global context file
node dist/cli.js global

# Export project status
node dist/cli.js status

# Generate PDF portfolio
node dist/cli.js export-pdf
```

## Known Issues
- **PII in transcripts:** Need automated PII scrubbing before PDF export
- **Conversation dates:** Fixed bug where dates weren't parsing correctly
- **Portfolio index:** Needs PORTFOLIO_INDEX.md creation feature
- **Project discovery:** Goes in circles asking "what repos exist?" (this is the problem this tool should solve!)

## Session End Routine
Before ending EVERY session, Claude will automatically create/update SESSION_NOTES.md:

```markdown
## [Date] [Time] - [Brief Description]

### What We Built
- [Feature 1]: [files modified]
- [Feature 2]: [what was implemented]

### Technical Details
Files changed:
- path/to/file.ext (what changed)
- path/to/file2.ext (what changed)

Code patterns used:
- [Pattern or approach used]
- [Libraries or techniques applied]

### Current Status
✅ Working: [what's tested and works]
❌ Broken: [known issues]
🚧 In Progress: [incomplete features]

### Branch Info
Branch: [branch-name]
Commits: [X files changed, Y insertions, Z deletions]
Ready to merge: [Yes/No - why or why not]

### Decisions Made
- [Decision 1 and rationale]
- [Decision 2 and rationale]

### Next Steps
1. [Priority 1 with specific action]
2. [Priority 2 with specific action]
3. [Priority 3 with specific action]

### Questions/Blockers
- [Open question or blocker]
- [Uncertainty that needs resolution]
```

**To execute:** Say "Append session notes to SESSION_NOTES.md" and Claude will:
1. Create/update SESSION_NOTES.md in repo root
2. Add new session at the TOP (most recent first)
3. Commit the file to current branch
4. Confirm completion

SESSION_NOTES.md is committed to the repo and tracks all session progress over time.

## Git Branch Strategy
- Claude Code browser creates a new branch every session
- At session end: Tell me if we should merge to main
- If merging:
  ```bash
  cd ~/claudesync2
  git checkout main
  git merge [feature-branch]
  git push origin main
  git branch -d [feature-branch]
  ```
- Delete merged branches immediately to keep repo clean

## Testing Approach
- Test incrementally with one repo first (use claudesync2 itself as test case)
- Verify PDF output doesn't contain PII
- Check that PROJECT_STATUS.md updates correctly
- Give me exact commands to run tests on my Mac

## Setup/Installation
When I need to set up on a new machine:
```bash
cd ~/claudesync2
npm install
npm run build
node dist/cli.js --help  # Verify it works
```

## The Meta-Problem This Solves
**Problem:** I lose context between Claude Code sessions
- I don't know what branches exist
- I forget what I built yesterday
- I re-explain my repos every session
- I waste 30-40% of my time on context resets

**Solution:** This tool should:
1. Auto-generate PROJECT_STATUS.md after each session
2. Export chat transcripts to searchable PDFs
3. Create a portfolio view of all my projects
4. Make it easy to pick up where I left off

**Irony:** I built this tool but haven't finished deploying it across all my projects yet.

## Project History
- Started Feb 1-2, 2025
- Active development through Feb 12
- Multiple iterations on PDF generation
- PII cleanup feature added Feb 5
- Dashboard and status prompt features added Feb 11
- Still needs: Full rollout to all 13 repos

## Product Vision
Phase 1 (current): CLI tool for local use
Phase 2 (future): Web dashboard to view all projects
Phase 3 (future): Integration with Claude.ai to auto-update from chat sessions

---
Last Updated: February 15, 2026
