# Plan: Centralize Data in the Deployment

## Problem
All runtime data lives in local files (`~/.claudesync_*.json`, in-memory caches, scattered `PROJECT_STATUS.md` files). Switching machines means losing state.

## Solution
Make the repo the single source of truth. All data lives in `data/` within the repo and syncs via git.

### Changes

1. **Create `data/` directory in the repo** as the centralized data store:
   - `data/config.json` - non-secret config (custom dev states, scan preferences)
   - `data/projects.json` - all project metadata (replaces scanning for PROJECT_STATUS.md files)
   - `data/ignored.json` - ignored project names
   - `data/archived.json` - archived project names
   - `data/resolved.json` - resolved thread keys
   - `data/prioritized.json` - prioritized thread keys
   - `data/item_actions.json` - what's-next item reassignments/ignores
   - `data/import_meta.json` - last import timestamp + filename
   - `data/conversations/` - stored conversation data (matched snippets + metadata, not full exports)

2. **Update `web_app.py`** to read/write from `data/` instead of `~/.claudesync_*`:
   - Change all file path references from home dir to repo `data/` dir
   - On save, auto-commit + push changes to keep repo in sync
   - On startup, pull latest data from repo

3. **Update `.gitignore`** to NOT ignore the `data/` directory (but still ignore secrets):
   - `data/secrets.json` stays gitignored (API keys)
   - Everything else in `data/` is tracked

4. **Secrets handling**:
   - API keys stay in `~/.claudesync/config.json` (local, never committed)
   - Or use environment variables
   - `data/config.json` only has non-secret configuration

5. **Conversation persistence**:
   - After chat history upload + matching, save matched results to `data/conversations/`
   - On next startup, load from `data/conversations/` instead of requiring re-upload
   - This is the key win: conversation context survives across machines
