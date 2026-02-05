# Global Claude Code Instructions

## Workflow Orchestration

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately - don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop
- After ANY correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes - don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests - then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management

1. **Plan First**: Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/todo.md`
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.

## User Profile

- **Non-developer**: I need clear, detailed guidance for technical tasks
- Provide step-by-step instructions for localhost setup - don't assume I know the basics
- Explain terminal commands before running them (what they do, what to expect)
- Streamline instructions into copy-paste blocks where possible - avoid line-by-line tedium
- When in doubt, over-explain rather than under-explain

## Local Development Preferences

- **Projects location**: Run all projects from the Downloads folder
- **Unique ports**: Each project must have its own unique localhost port (avoid conflicts)
- **Cleanup**: Proactively identify and remove out-of-date files to keep things sanitary
- **Self-contained repos**: Add all necessary files to each repo for it to execute - no missing dependencies

## File Naming Convention

All files must be uniquely named with:
- Project name
- Date-time stamp (format: `YYYY-MM-DD_HHMMSS`)
- Example: `projectname_featurename_2026-02-03_143022.ext`

This allows easy identification of what's current vs. what can be trashed.

## Security Requirements

- Ensure code has no major security flaws (OWASP top 10, injection vulnerabilities, etc.)
- Proactively identify and fix security issues before they can be exploited
- Never commit secrets, credentials, or API keys to repos

## Product Spec Template

When creating a Product Spec document from a conversation, include:

1. **Product/Feature Name** - and the problem it solves
2. **User Story** - who is this for and what are they trying to accomplish?
3. **Core Functionality** - what does it actually do? Be specific about the workflow or user experience discussed
4. **Inputs and Outputs** - what goes in, what comes out, what does the user see/get?
5. **Business Rules and Logic** - any "if this, then that" conditions, constraints, or edge cases
6. **Data Requirements** - what information needs to be stored, pulled, or connected?
7. **Integrations or Dependencies** - other systems, APIs, tools, or platforms involved
8. **Out of Scope** - what are we explicitly NOT building (for now)?
9. **Open Design Questions** - things not resolved or needing testing
10. **Success Criteria** - how do we know it's working?

Write specs so a developer (or Claude in a future session) could build from it without needing the original conversation.

## Project Completion

When user says a project is "done for now":
1. **Update status** - Mark all tasks complete in `tasks/todo.md`, note project as paused/complete
2. **Create revised spec** - Generate a final Product Spec PDF reflecting all changes made during the session
3. **Version the spec** - Use naming convention: `projectname_spec_vX.X_YYYY-MM-DD.pdf`
4. **Increment version** - Each revision bumps the version number (v1.0 → v1.1 for minor, v1.0 → v2.0 for major changes)
