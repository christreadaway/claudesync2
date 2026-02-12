#!/usr/bin/env python3
"""
Claude Project Sync - Dashboard & PDF Generator

Localhost-only web dashboard that visualizes project activity over time
and lets you drill down into individual project decision timelines.

Features:
- Activity chart (day/week/month) across all projects
- Project cards with progress, last active, open thread count
- Drill-down to full decision timeline per project
- EOL/abandoned project detection with ignore/hide
- Dark mode toggle (persisted in localStorage)
- Chat history zip upload
- One-click PDF generation + download

Usage:
    python3 web_app.py
    # Then open http://localhost:5111 in your browser
"""

import json
import os
import re
import tempfile
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta

from flask import (Flask, request, send_file, render_template_string,
                   flash, redirect, url_for, jsonify, Response)

from generate_status_pdf import load_projects, create_pdf

app = Flask(__name__)
app.secret_key = os.urandom(24)

UPLOAD_DIR = tempfile.mkdtemp(prefix='claudesync_')
IGNORED_FILE = os.path.expanduser('~/.claudesync_ignored.json')
RESOLVED_FILE = os.path.expanduser('~/.claudesync_resolved.json')
AI_CONFIG_FILE = os.path.expanduser('~/.claudesync_ai.json')
ARCHIVED_FILE = os.path.expanduser('~/.claudesync_archived.json')
IMPORT_META_FILE = os.path.expanduser('~/.claudesync_import_meta.json')
ITEM_ACTIONS_FILE = os.path.expanduser('~/.claudesync_item_actions.json')

# Cache loaded projects so dashboard + drill-down share data
_project_cache = {
    'projects': [],
    'scan_paths': '~',
    'chat_history_path': None,
    'lock': threading.Lock(),
}

# Background task state — shared between threads
_bg_task = {
    'running': False,
    'step': '',       # Current step name
    'detail': '',     # Human-readable detail message
    'error': None,
    'result_msg': None,
    'lock': threading.Lock(),
}


def _get_projects():
    """Thread-safe read of the cached projects list."""
    with _project_cache['lock']:
        return list(_project_cache.get('projects', []))


def _bg_progress(step, detail=''):
    """Update the shared progress state (called from background thread)."""
    with _bg_task['lock']:
        _bg_task['step'] = step
        _bg_task['detail'] = detail


def _bg_classify_unmatched(unmatched_chats, projects):
    """Classify unmatched chat conversations using AI. Returns count classified."""
    project_names = [p.get('name', '') for p in projects if p.get('name')]
    all_results = []
    batch_size = 15

    for batch_start in range(0, len(unmatched_chats), batch_size):
        batch = unmatched_chats[batch_start:batch_start + batch_size]
        _bg_progress('ai_classify', f'Classifying batch {batch_start // batch_size + 1}/{(len(unmatched_chats) + batch_size - 1) // batch_size}...')

        lines = []
        for i, chat in enumerate(batch):
            idx = batch_start + i
            excerpt = chat.get('excerpt', '')[:200].replace('\n', ' ')
            lines.append(f"[{idx}] file: {chat['filename']} | date: {chat.get('date', '?')} | excerpt: {excerpt}")

        prompt = f"""These chat conversations were not automatically matched to any existing project initiative.

Existing initiatives: {', '.join(project_names)}

For each conversation below, determine:
1. If it clearly belongs to an existing initiative: [idx] MATCH initiative_name
2. If it doesn't match any existing initiative, suggest a new name: [idx] NEW suggested_initiative_name
3. If it's too vague or just small talk/greetings: [idx] SKIP

Rules:
- Initiative names should be descriptive (2-5 words)
- Group related conversations under the same new initiative name
- Be specific, not generic.

Conversations:
{chr(10).join(lines)}"""

        result = _call_ai(prompt, max_tokens=800)
        if not result:
            _bg_progress('ai_classify', 'AI call failed — check API key and connection')
            break

        for line in result.strip().split('\n'):
            line = line.strip()
            if not line or not line.startswith('['):
                continue
            try:
                idx_str = line[1:line.index(']')]
                idx = int(idx_str)
                rest = line[line.index(']') + 1:].strip()
                if idx < 0 or idx >= len(unmatched_chats):
                    continue
                chat_info = unmatched_chats[idx]
                entry = {'idx': idx, 'filename': chat_info['filename'],
                         'date': chat_info.get('date', '?'),
                         'excerpt': chat_info.get('excerpt', '')[:150]}
                if rest.startswith('MATCH'):
                    entry['action'] = 'match'
                    entry['initiative'] = rest[5:].strip()
                elif rest.startswith('NEW'):
                    entry['action'] = 'new'
                    entry['initiative'] = rest[3:].strip()
                elif rest.startswith('SKIP'):
                    entry['action'] = 'skip'
                    entry['initiative'] = ''
                else:
                    continue
                all_results.append(entry)
            except (ValueError, IndexError):
                continue

    # Save results
    if all_results:
        initiatives = _load_initiatives()
        initiatives['last_classified'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        initiatives['results'] = all_results
        initiatives['total_unmatched'] = len(unmatched_chats)
        _save_initiatives(initiatives)

    return len(all_results)


def _bg_run_load(scan_paths_str, chat_history_path, ai_analyze):
    """Background worker: load projects, optionally enrich with AI."""
    try:
        with _bg_task['lock']:
            _bg_task['running'] = True
            _bg_task['error'] = None
            _bg_task['result_msg'] = None

        # Load projects with progress callback
        if scan_paths_str:
            scan_paths = [os.path.expanduser(p.strip()) for p in scan_paths_str.split()]
        else:
            scan_paths_str = _project_cache.get('scan_paths', '~')
            scan_paths = [os.path.expanduser(p.strip()) for p in scan_paths_str.split()]

        chp = chat_history_path or _project_cache.get('chat_history_path')

        projects = load_projects(
            scan_paths=scan_paths,
            chat_history_path=chp,
            verbose=False,
            progress_callback=_bg_progress,
        )

        with _project_cache['lock']:
            _project_cache['projects'] = projects
            _project_cache['scan_paths'] = scan_paths_str
            _project_cache['chat_history_path'] = chp

        # Chat stats
        chat_stats = getattr(load_projects, '_last_chat_stats', {})
        total = len(projects)
        msg = f'Loaded {total} projects'
        if chat_stats.get('total_files'):
            msg += f' — {chat_stats["total_files"]} chat files processed'
            msg += f', {chat_stats["total_conversations"]} conversations matched'
            if chat_stats.get('unmatched_files'):
                msg += f', {chat_stats["unmatched_files"]} unmatched'

        # AI enrichment + classification (automatic when key is present)
        enriched = 0
        classified = 0
        ai_warnings = []
        if ai_analyze:
            _bg_progress('ai_enrichment', 'Enriching project descriptions with AI...')
            try:
                enriched = _ai_enrich_all_projects()
                if enriched:
                    msg += f'. AI enriched {enriched} projects'
            except Exception as e:
                ai_warnings.append(f'AI enrichment failed: {e}')
                _bg_progress('ai_enrichment', f'AI enrichment failed: {e}')

            # Auto-classify unmatched conversations
            unmatched = chat_stats.get('unmatched_chats', [])
            if unmatched:
                _bg_progress('ai_classify', f'Classifying {len(unmatched)} unmatched conversations...')
                try:
                    classified = _bg_classify_unmatched(unmatched, projects)
                    if classified:
                        msg += f', classified {classified} conversations'
                    elif unmatched:
                        ai_warnings.append('AI classified 0 conversations — API may have failed')
                except Exception as e:
                    ai_warnings.append(f'AI classification failed: {e}')
                    _bg_progress('ai_classify', f'AI classification failed: {e}')

            if enriched or classified:
                msg += '.'
            if ai_warnings:
                msg += ' Warnings: ' + '; '.join(ai_warnings)

        with _bg_task['lock']:
            _bg_task['result_msg'] = msg

    except Exception as e:
        with _bg_task['lock']:
            _bg_task['error'] = str(e)
    finally:
        with _bg_task['lock']:
            _bg_task['running'] = False
            _bg_task['step'] = 'done'
            _bg_task['detail'] = ''


# =============================================================================
# IGNORED PROJECTS PERSISTENCE
# =============================================================================

def _load_ignored():
    """Load ignored project names from disk."""
    if os.path.exists(IGNORED_FILE):
        try:
            with open(IGNORED_FILE, 'r') as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def _save_ignored(names):
    """Save ignored project names to disk."""
    with open(IGNORED_FILE, 'w') as f:
        json.dump(sorted(names), f, indent=2)


# =============================================================================
# RESOLVED THREADS PERSISTENCE
# =============================================================================

def _load_resolved():
    """Load resolved thread keys from disk.

    Keys are 'project_name::thread_text' to uniquely identify threads.
    """
    if os.path.exists(RESOLVED_FILE):
        try:
            with open(RESOLVED_FILE, 'r') as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def _save_resolved(keys):
    """Save resolved thread keys to disk."""
    with open(RESOLVED_FILE, 'w') as f:
        json.dump(sorted(keys), f, indent=2)


def _thread_key(project_name, thread_text):
    """Build a unique key for a thread."""
    return f'{project_name}::{thread_text[:100]}'


# =============================================================================
# AI CONFIG PERSISTENCE
# =============================================================================

def _load_ai_config():
    """Load AI API configuration."""
    if os.path.exists(AI_CONFIG_FILE):
        try:
            with open(AI_CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {'api_url': 'https://api.anthropic.com/v1/messages', 'api_key': '', 'model': 'claude-haiku-4-5-20251001'}


def _save_ai_config(config):
    """Save AI API configuration."""
    with open(AI_CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


# =============================================================================
# ARCHIVED PROJECTS PERSISTENCE
# =============================================================================

def _load_archived():
    if os.path.exists(ARCHIVED_FILE):
        try:
            with open(ARCHIVED_FILE, 'r') as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def _save_archived(names):
    with open(ARCHIVED_FILE, 'w') as f:
        json.dump(sorted(names), f, indent=2)


# =============================================================================
# IMPORT METADATA
# =============================================================================

def _load_import_meta():
    if os.path.exists(IMPORT_META_FILE):
        try:
            with open(IMPORT_META_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_import_meta(meta):
    with open(IMPORT_META_FILE, 'w') as f:
        json.dump(meta, f, indent=2)


# =============================================================================
# ITEM ACTIONS PERSISTENCE (reassign / ignore on what's-next items)
# =============================================================================
# Format: { "item_key": {"action": "ignored"|"reassigned", "target_project": "..."} }

def _load_item_actions():
    if os.path.exists(ITEM_ACTIONS_FILE):
        try:
            with open(ITEM_ACTIONS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_item_actions(actions):
    with open(ITEM_ACTIONS_FILE, 'w') as f:
        json.dump(actions, f, indent=2)


def _item_key(project_name, item_type, item_text):
    """Stable key for an item across sessions."""
    return f"{project_name}::{item_type}::{item_text[:80]}"


# =============================================================================
# DATA LOADING + EOL DETECTION
# =============================================================================

def _load_cached_projects(scan_paths_str=None, chat_history_path=None):
    """Load projects, caching the result for the session."""
    if scan_paths_str:
        scan_paths = [os.path.expanduser(p.strip()) for p in scan_paths_str.split()]
    else:
        scan_paths_str = _project_cache.get('scan_paths', '~')
        scan_paths = [os.path.expanduser(p.strip()) for p in scan_paths_str.split()]

    chp = chat_history_path or _project_cache.get('chat_history_path')

    projects = load_projects(scan_paths=scan_paths, chat_history_path=chp, verbose=False)

    with _project_cache['lock']:
        _project_cache['projects'] = projects
        _project_cache['scan_paths'] = scan_paths_str
        _project_cache['chat_history_path'] = chp

    return projects


def _detect_eol(project):
    """Detect if a project looks abandoned/EOL. Returns reason string or None."""
    status = project.get('status', '').lower()
    eol_statuses = ['abandoned', 'archived', 'deprecated', 'eol', 'end of life',
                    'merged', 'completed', 'sunset', 'dead']
    for s in eol_statuses:
        if s in status:
            return f'Status: {project.get("status")}'

    # Had a repo reference but it's marked as not having one
    repo_str = project.get('repo', '').lower()
    has_repo = project.get('has_github_repo', False)
    if repo_str and not has_repo and 'not' in repo_str:
        pass  # This is "not yet created", not EOL

    # No activity in 90+ days
    timeline = project.get('timeline', [])
    if timeline:
        dates = []
        for e in timeline:
            try:
                dates.append(datetime.strptime(e.get('date', ''), '%Y-%m-%d'))
            except (ValueError, TypeError):
                continue
        if dates:
            latest = max(dates)
            days_ago = (datetime.now() - latest).days
            if days_ago > 90:
                return f'No activity in {days_ago} days'

    # 0% progress with no timeline at all
    if project.get('progress', 0) == 0 and len(timeline) == 0:
        return 'No progress and no activity recorded'

    return None


def _aggregate_activity(projects, mode='day'):
    """Aggregate activity events across all projects into time buckets."""
    events = []
    for p in projects:
        name = p.get('name', 'Unknown')
        for entry in p.get('timeline', []):
            date_str = entry.get('date', '')
            source = entry.get('source', 'Unknown')
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d')
            except (ValueError, TypeError):
                continue

            src_lower = source.lower()
            if 'commit' in src_lower or 'git' in src_lower:
                category = 'Commits'
            elif 'chat' in src_lower or 'claude.ai' in src_lower:
                category = 'Chat Activity'
            else:
                category = 'Progress Log'

            events.append({'date': dt, 'category': category, 'project': name})

    if not events:
        return {'labels': [], 'datasets': []}

    buckets = defaultdict(lambda: defaultdict(int))

    for e in events:
        dt = e['date']
        if mode == 'day':
            key = dt.strftime('%Y-%m-%d')
        elif mode == 'week':
            monday = dt - timedelta(days=dt.weekday())
            key = monday.strftime('%Y-%m-%d')
        elif mode == 'month':
            key = dt.strftime('%Y-%m')
        else:
            key = dt.strftime('%Y-%m-%d')
        buckets[key][e['category']] += 1

    labels = sorted(buckets.keys())

    display_labels = []
    for label in labels:
        try:
            if mode == 'month':
                dt = datetime.strptime(label, '%Y-%m')
                display_labels.append(dt.strftime('%b %Y'))
            else:
                dt = datetime.strptime(label, '%Y-%m-%d')
                if mode == 'week':
                    display_labels.append(f"Week of {dt.strftime('%b %d')}")
                else:
                    display_labels.append(dt.strftime('%b %d'))
        except ValueError:
            display_labels.append(label)

    categories = ['Commits', 'Chat Activity', 'Progress Log']
    cat_colors = {
        'Commits': '#3498DB',
        'Chat Activity': '#9B59B6',
        'Progress Log': '#2ECC71',
    }

    datasets = []
    for cat in categories:
        data = [buckets[label].get(cat, 0) for label in labels]
        if sum(data) > 0:
            datasets.append({
                'label': cat,
                'data': data,
                'backgroundColor': cat_colors.get(cat, '#95A5A6'),
            })

    return {'labels': display_labels, 'datasets': datasets}


def _project_activity_breakdown(projects):
    """Per-project activity counts for the project cards."""
    resolved = _load_resolved()
    breakdown = []
    for p in projects:
        name = p.get('name', 'Unknown')
        timeline = p.get('timeline', [])
        commits = sum(1 for e in timeline if 'commit' in e.get('source', '').lower())
        chats = sum(1 for e in timeline if 'chat' in e.get('source', '').lower())
        logs = len(timeline) - commits - chats

        # Recent decisions (last 3 timeline entries)
        recent = timeline[:3] if timeline else []

        # Open threads, excluding resolved ones
        all_threads = p.get('open_threads', [])
        active_threads = [(t, txt) for t, txt in all_threads
                          if _thread_key(name, txt) not in resolved]

        breakdown.append({
            'name': name,
            'progress': p.get('progress', 0),
            'status': p.get('status', ''),
            'category': p.get('category_group', ''),
            'last_worked': p.get('last_worked', ''),
            'dev_state': p.get('dev_state', ''),
            'total_events': len(timeline),
            'commits': commits,
            'chats': p.get('chat_conversations', 0) or chats,
            'logs': logs,
            'open_threads': len(active_threads),
            'all_threads': len(all_threads),
            'blockers': sum(1 for t, _ in active_threads if t == 'Blocker'),
            'recent_decisions': recent,
            'loose_ends': active_threads[:3],
            'eol_reason': _detect_eol(p),
        })

    return breakdown


# =============================================================================
# SHARED CSS (dark mode via CSS custom properties)
# =============================================================================

THEME_CSS = """
:root {
    --bg: #f5f6f8; --bg-card: #fff; --bg-card-hover: #fff;
    --text: #1a1a1a; --text-secondary: #888; --text-muted: #aaa;
    --heading: #2C3E50; --border: #e0e0e0; --border-light: #f0f0f0;
    --input-bg: #fff; --input-border: #ddd;
    --bar-bg: #2C3E50; --bar-text: #fff;
    --stat-bg: #f8f9fa; --progress-bg: #eee;
    --shadow: rgba(0,0,0,0.06); --shadow-hover: rgba(0,0,0,0.12);
    --flash-success-bg: #d4edda; --flash-success-text: #155724;
    --flash-error-bg: #f8d7da; --flash-error-text: #721c24;
    --modal-bg: rgba(0,0,0,0.4);
    --drop-bg: #fafbfc; --drop-border: #ccd; --drop-hover-bg: #f0f7ff;
    --toggle-bg: #fff; --toggle-border: #ddd; --toggle-text: #666;
    --eol-bg: #fff8e1; --eol-border: #ffe082; --eol-text: #8d6e00;
}
[data-theme="dark"] {
    --bg: #1a1b1e; --bg-card: #25262b; --bg-card-hover: #2c2e33;
    --text: #c9ccd1; --text-secondary: #909296; --text-muted: #5c5f66;
    --heading: #e4e5e7; --border: #373a40; --border-light: #2c2e33;
    --input-bg: #2c2e33; --input-border: #373a40;
    --bar-bg: #141517; --bar-text: #c9ccd1;
    --stat-bg: #2c2e33; --progress-bg: #373a40;
    --shadow: rgba(0,0,0,0.2); --shadow-hover: rgba(0,0,0,0.4);
    --flash-success-bg: #1b3d2a; --flash-success-text: #69db7c;
    --flash-error-bg: #3d1b1b; --flash-error-text: #ff8787;
    --modal-bg: rgba(0,0,0,0.7);
    --drop-bg: #2c2e33; --drop-border: #373a40; --drop-hover-bg: #1c3a5c;
    --toggle-bg: #2c2e33; --toggle-border: #373a40; --toggle-text: #909296;
    --eol-bg: #332b00; --eol-border: #665500; --eol-text: #ffd54f;
}
"""

# =============================================================================
# DASHBOARD HTML
# =============================================================================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Project Portfolio Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
    <style>
        """ + THEME_CSS + """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); transition: background 0.3s, color 0.3s; }
        .top-bar { background: var(--bar-bg); color: var(--bar-text); padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; }
        .top-bar h1 { font-size: 18px; font-weight: 600; }
        .top-bar .actions { display: flex; gap: 10px; align-items: center; }
        .top-bar .btn { padding: 8px 16px; border-radius: 5px; font-size: 12px; font-weight: 600; cursor: pointer; border: none; text-decoration: none; color: white; }
        .btn-upload { background: #3498DB; }
        .btn-upload:hover { background: #2980B9; }
        .btn-pdf { background: #2ECC71; }
        .btn-pdf:hover { background: #27AE60; }
        .btn-theme { background: transparent; border: 1px solid rgba(255,255,255,0.3) !important; color: var(--bar-text); font-size: 14px; padding: 6px 12px; }
        .btn-theme:hover { background: rgba(255,255,255,0.1); }
        .container { max-width: 1100px; margin: 0 auto; padding: 24px 20px; }

        /* Filter bar */
        .filter-bar { display: flex; gap: 10px; align-items: center; margin-bottom: 18px; font-size: 12px; }
        .filter-bar label { color: var(--text-secondary); font-weight: 500; }
        .filter-toggle { padding: 4px 12px; border: 1px solid var(--toggle-border); background: var(--toggle-bg); border-radius: 4px; font-size: 11px; cursor: pointer; color: var(--toggle-text); }
        .filter-toggle.active { background: var(--heading); color: white; border-color: var(--heading); }

        .stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 24px; }
        .stat-card { background: var(--bg-card); border-radius: 8px; padding: 18px; box-shadow: 0 1px 3px var(--shadow); cursor: pointer; transition: box-shadow 0.2s; text-decoration: none; display: block; color: inherit; }
        .stat-card:hover { box-shadow: 0 4px 12px var(--shadow-hover); }
        .stat-card .number { font-size: 28px; font-weight: 700; color: var(--heading); }
        .stat-card .label { font-size: 11px; color: var(--text-secondary); margin-top: 2px; text-transform: uppercase; letter-spacing: 0.5px; }
        .chart-card { background: var(--bg-card); border-radius: 8px; padding: 20px; margin-bottom: 24px; box-shadow: 0 1px 3px var(--shadow); }
        .chart-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
        .chart-header h2 { font-size: 15px; color: var(--heading); }
        .toggle-group { display: flex; gap: 4px; }
        .toggle-btn { padding: 5px 14px; border: 1px solid var(--toggle-border); background: var(--toggle-bg); border-radius: 4px; font-size: 12px; cursor: pointer; color: var(--toggle-text); }
        .toggle-btn.active { background: var(--heading); color: white; border-color: var(--heading); }
        .projects-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
        .project-card { background: var(--bg-card); border-radius: 8px; padding: 18px; box-shadow: 0 1px 3px var(--shadow); cursor: pointer; transition: box-shadow 0.2s, background 0.2s; text-decoration: none; color: inherit; display: block; position: relative; }
        .project-card:hover { box-shadow: 0 4px 12px var(--shadow-hover); background: var(--bg-card-hover); }
        .project-card.eol { border-left: 3px solid var(--eol-border); opacity: 0.75; }
        .project-card.hidden { display: none; }
        .project-card .name { font-size: 14px; font-weight: 600; color: var(--heading); margin-bottom: 2px; }
        .project-card .meta { font-size: 11px; color: var(--text-secondary); margin-bottom: 10px; }
        .progress-bar { height: 6px; background: var(--progress-bg); border-radius: 3px; overflow: hidden; margin-bottom: 10px; }
        .progress-fill { height: 100%; border-radius: 3px; transition: width 0.3s; }
        .project-card .counts { display: flex; gap: 12px; font-size: 11px; color: var(--text-secondary); flex-wrap: wrap; }
        .project-card .counts span { display: flex; align-items: center; gap: 3px; }
        .dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
        .dot-commit { background: #3498DB; }
        .dot-chat { background: #9B59B6; }
        .dot-log { background: #2ECC71; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 600; }
        .badge-blocker { background: #fce4ec; color: #c62828; }
        .badge-eol { background: var(--eol-bg); color: var(--eol-text); border: 1px solid var(--eol-border); }
        .badge-dev-state { font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 10px; margin-left: 6px; }
        .badge-dev-test { background: #FDF2E9; color: #E67E22; border: 1px solid #E67E22; }
        .badge-dev-refine { background: #EBF5FB; color: #3498DB; border: 1px solid #3498DB; }
        .badge-dev-continue { background: #FDEDEC; color: #E74C3C; border: 1px solid #E74C3C; }
        [data-theme="dark"] .badge-dev-test { background: #3d2e00; color: #F5B041; border-color: #E67E22; }
        [data-theme="dark"] .badge-dev-refine { background: #0d2137; color: #5DADE2; border-color: #3498DB; }
        [data-theme="dark"] .badge-dev-continue { background: #3d0d0d; color: #F1948A; border-color: #E74C3C; }
        .project-card.dev-test { border-left: 3px solid #E67E22; }
        .project-card.dev-refine { border-left: 3px solid #3498DB; }
        .project-card.dev-continue { border-left: 3px solid #E74C3C; }

        /* Recent decisions + loose ends on cards */
        .card-section { margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--border-light); }
        .card-section-title { font-size: 10px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
        .mini-entry { font-size: 11px; color: var(--text-secondary); line-height: 1.4; padding: 2px 0; }
        .mini-date { font-size: 10px; color: var(--text-muted); margin-right: 4px; }
        .mini-thread { font-size: 11px; color: var(--text-secondary); line-height: 1.4; padding: 2px 0; }
        .mini-tag { font-size: 9px; font-weight: 600; padding: 1px 5px; border-radius: 3px; margin-right: 4px; }
        .mini-tag-blocker { background: #fce4ec; color: #c62828; }
        .mini-tag-openquestion { background: #fff3e0; color: #e65100; }
        .mini-tag-nextstep { background: #e3f2fd; color: #1565c0; }
        .mini-tag-notbuiltyet { background: var(--stat-bg); color: var(--text-secondary); }

        /* EOL bar inside project card */
        .eol-bar { display: flex; align-items: center; justify-content: space-between; background: var(--eol-bg); border: 1px solid var(--eol-border); border-radius: 5px; padding: 6px 10px; margin-top: 10px; font-size: 11px; color: var(--eol-text); }
        .eol-bar .reason { flex: 1; }
        .eol-bar .btn-ignore { background: none; border: 1px solid var(--eol-border); color: var(--eol-text); padding: 2px 10px; border-radius: 3px; font-size: 10px; font-weight: 600; cursor: pointer; margin-left: 8px; }
        .eol-bar .btn-ignore:hover { background: var(--eol-border); color: #333; }

        footer { text-align: center; font-size: 11px; color: var(--text-muted); margin-top: 40px; padding-bottom: 20px; }
        .flash { padding: 10px 16px; border-radius: 6px; margin-bottom: 16px; font-size: 13px; }
        .flash-success { background: var(--flash-success-bg); color: var(--flash-success-text); }
        .flash-error { background: var(--flash-error-bg); color: var(--flash-error-text); }

        /* Upload modal */
        .modal-overlay { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: var(--modal-bg); z-index: 100; justify-content: center; align-items: center; }
        .modal-overlay.show { display: flex; }
        .modal { background: var(--bg-card); border-radius: 10px; padding: 28px; max-width: 500px; width: 90%; }
        .modal h2 { font-size: 16px; color: var(--heading); margin-bottom: 16px; }
        .drop-zone { border: 2px dashed var(--drop-border); border-radius: 8px; padding: 28px; text-align: center; cursor: pointer; transition: all 0.2s; background: var(--drop-bg); }
        .drop-zone:hover, .drop-zone.dragover { border-color: #3498DB; background: var(--drop-hover-bg); }
        .drop-zone p { font-size: 13px; color: var(--text-secondary); }
        .drop-zone input[type="file"] { display: none; }
        .drop-zone .filename { margin-top: 8px; font-size: 13px; color: #2ECC71; font-weight: 600; }
        .modal label { display: block; font-size: 13px; color: var(--text-secondary); margin: 14px 0 6px; font-weight: 500; }
        .modal input[type="text"] { width: 100%; padding: 9px 12px; border: 1px solid var(--input-border); border-radius: 5px; font-size: 13px; background: var(--input-bg); color: var(--text); }
        .modal .btn-row { display: flex; gap: 10px; margin-top: 18px; }
        .modal .btn { padding: 10px 22px; font-size: 13px; }
        .btn-cancel { background: var(--stat-bg); color: var(--text-secondary); }
        .btn-cancel:hover { background: var(--progress-bg); }
        /* Non-blocking progress banner */
        .progress-banner { display: none; background: var(--bar-bg); border-bottom: 1px solid rgba(52,152,219,0.3); padding: 8px 24px 4px; position: sticky; top: 0; z-index: 90; }
        .progress-banner.show { display: block; }
        .progress-banner-inner { display: flex; align-items: center; gap: 10px; }
        .progress-spinner { width: 14px; height: 14px; border: 2px solid rgba(255,255,255,0.2); border-top-color: #3498DB; border-radius: 50%; animation: spin 0.8s linear infinite; flex-shrink: 0; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .progress-step { font-size: 12px; font-weight: 600; color: #3498DB; text-transform: uppercase; letter-spacing: 0.5px; }
        .progress-detail { font-size: 12px; color: var(--bar-text); opacity: 0.8; }
        .progress-track { height: 2px; background: rgba(255,255,255,0.1); margin-top: 6px; border-radius: 1px; overflow: hidden; }
        .progress-track-fill { height: 100%; background: #3498DB; border-radius: 1px; transition: width 0.3s; width: 0%; }
        .progress-banner.done .progress-spinner { animation: none; border-color: #2ECC71; border-top-color: #2ECC71; }
        .progress-banner.done .progress-step { color: #2ECC71; }
        .progress-banner.error .progress-spinner { animation: none; border-color: #E74C3C; border-top-color: #E74C3C; }
        .progress-banner.error .progress-step { color: #E74C3C; }
        .modal select { width: 100%; padding: 9px 12px; border: 1px solid var(--input-border); border-radius: 5px; font-size: 13px; background: var(--input-bg); color: var(--text); }
    </style>
    <script>
        // Apply theme before paint to prevent flash
        (function() {
            var t = localStorage.getItem('theme') || 'light';
            document.documentElement.setAttribute('data-theme', t);
        })();
    </script>
</head>
<body>
    <div class="top-bar">
        <h1>Project Portfolio Dashboard</h1>
        <div class="actions">
            <button class="btn btn-theme" onclick="toggleTheme()" id="themeBtn" title="Toggle dark mode">
                <span id="themeIcon"></span>
            </button>
            <a href="/view/whats-next" class="btn" style="background:#e67e22;">What's Next</a>
            <button class="btn btn-upload" onclick="document.getElementById('uploadModal').classList.add('show')">Upload Chat History</button>
            <button class="btn" style="background:#8e44ad;" onclick="document.getElementById('aiModal').classList.add('show')">AI Settings</button>
            <a href="/generate-pdf" class="btn btn-pdf">Generate PDF</a>
        </div>
    </div>

    <!-- Progress Banner (sticky, right below top bar) -->
    <div class="progress-banner" id="progressBanner">
        <div class="progress-banner-inner">
            <div class="progress-spinner"></div>
            <span class="progress-step" id="progressStep"></span>
            <span class="progress-detail" id="progressDetail"></span>
        </div>
        <div class="progress-track"><div class="progress-track-fill" id="progressFill"></div></div>
    </div>

    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
            {% for category, message in messages %}
            <div class="flash flash-{{ category }}">{{ message }}</div>
            {% endfor %}
        {% endif %}
        {% endwith %}

        <!-- Stats Row -->
        <div class="stats-row">
            <a href="/view/projects" class="stat-card">
                <div class="number">{{ total_projects }}</div>
                <div class="label">Projects</div>
            </a>
            <a href="/view/events" class="stat-card">
                <div class="number">{{ total_events }}</div>
                <div class="label">Total Events</div>
            </a>
            <a href="/view/threads" class="stat-card">
                <div class="number">{{ total_threads }}</div>
                <div class="label">Open Threads</div>
            </a>
            <a href="/view/blockers" class="stat-card">
                <div class="number">{{ total_blockers }}</div>
                <div class="label">Blockers</div>
            </a>
            {% if unmatched_count > 0 %}
            <a href="/view/unmatched" class="stat-card" style="border-color:#e67e22;">
                <div class="number" style="color:#e67e22;">{{ unmatched_count }}</div>
                <div class="label">Unmatched Chats</div>
            </a>
            {% endif %}
        </div>

        <!-- Activity Chart -->
        <div class="chart-card">
            <div class="chart-header">
                <h2>Activity Across All Projects</h2>
                <div class="toggle-group">
                    <button class="toggle-btn active" data-mode="day" onclick="switchMode('day', this)">Day</button>
                    <button class="toggle-btn" data-mode="week" onclick="switchMode('week', this)">Week</button>
                    <button class="toggle-btn" data-mode="month" onclick="switchMode('month', this)">Month</button>
                </div>
            </div>
            <canvas id="activityChart" height="80"></canvas>
        </div>

        <!-- Filter bar -->
        <div class="filter-bar">
            <label>Show:</label>
            <button class="filter-toggle active" onclick="toggleFilter('active', this)">Active</button>
            <button class="filter-toggle" onclick="toggleFilter('eol', this)">Possibly EOL</button>
            <button class="filter-toggle" onclick="toggleFilter('ignored', this)">Ignored</button>
        </div>

        <!-- Project Cards -->
        <div class="projects-grid" id="projectsGrid">
            {% for p in project_cards %}
            <div class="project-card {% if p.eol_reason %}eol{% endif %} {% if p.name in ignored_names %}hidden{% endif %} {% if p.dev_state %}dev-{{ p.dev_state|lower }}{% endif %}"
                 data-name="{{ p.name }}" data-eol="{{ 'yes' if p.eol_reason else 'no' }}" data-ignored="{{ 'yes' if p.name in ignored_names else 'no' }}" data-devstate="{{ p.dev_state|lower }}"
                 onclick="if (!event.target.closest('.btn-ignore, .btn-restore')) window.location='/project/{{ loop.index0 }}'">
                <div class="name">
                    {{ p.name }}
                    {% if p.dev_state %}<span class="badge badge-dev-state badge-dev-{{ p.dev_state|lower }}">{{ p.dev_state }}</span>{% endif %}
                    {% if p.eol_reason %}<span class="badge badge-eol">Possibly EOL</span>{% endif %}
                </div>
                <div class="meta">{{ p.category }} &middot; {{ p.status }}{% if p.last_worked %} &middot; Last: {{ p.last_worked }}{% endif %}</div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {{ p.progress }}%; background: {{ '#2ECC71' if p.progress > 75 else '#3498DB' if p.progress >= 50 else '#F1C40F' if p.progress >= 25 else '#E74C3C' }};"></div>
                </div>
                <div class="counts">
                    <span><span class="dot dot-commit"></span> {{ p.commits }} commits</span>
                    <span><span class="dot dot-chat"></span> {{ p.chats }} chats</span>
                    <span><span class="dot dot-log"></span> {{ p.logs }} log entries</span>
                    {% if p.blockers > 0 %}
                    <span class="badge badge-blocker">{{ p.blockers }} blocker{{ 's' if p.blockers != 1 }}</span>
                    {% endif %}
                </div>
                {% if p.recent_decisions %}
                <div class="card-section">
                    <div class="card-section-title">Recent decisions</div>
                    {% for d in p.recent_decisions %}
                    <div class="mini-entry"><span class="mini-date">{{ d.date }}</span> {{ d.text[:80] }}{% if d.text|length > 80 %}...{% endif %}</div>
                    {% endfor %}
                </div>
                {% endif %}
                {% if p.loose_ends %}
                <div class="card-section">
                    <div class="card-section-title">Open loose ends</div>
                    {% for t_type, t_text in p.loose_ends %}
                    <div class="mini-thread">
                        <span class="mini-tag mini-tag-{{ t_type|lower|replace(' ', '') }}">{{ t_type }}</span>
                        {{ t_text[:70] }}{% if t_text|length > 70 %}...{% endif %}
                    </div>
                    {% endfor %}
                </div>
                {% endif %}
                {% if p.eol_reason and p.name not in ignored_names %}
                <div class="eol-bar">
                    <span class="reason">{{ p.eol_reason }}</span>
                    <button class="btn-ignore" onclick="ignoreProject('{{ p.name }}')">Ignore</button>
                </div>
                {% endif %}
                {% if p.name in ignored_names %}
                <div class="eol-bar">
                    <span class="reason">This project is hidden</span>
                    <button class="btn-ignore btn-restore" onclick="restoreProject('{{ p.name }}')">Restore</button>
                </div>
                {% endif %}
            </div>
            {% endfor %}
        </div>

        <footer>
            claudesync2 dashboard &mdash; localhost only, nothing leaves this machine<br>
            If this tool saves you time: Venmo @ctreada
        </footer>
    </div>

    <!-- Upload Modal -->
    <div class="modal-overlay" id="uploadModal">
        <div class="modal">
            <h2>Upload Chat History & Configure</h2>
            {% if import_meta.last_import %}
            <p style="font-size:11px; color:var(--text-secondary); margin-bottom:12px; padding:8px; background:var(--stat-bg); border-radius:4px;">
                Last import: <strong>{{ import_meta.last_import }}</strong> ({{ import_meta.last_file }})<br>
                <span style="color:var(--text-muted);">You can upload just your recent chats to append new data.</span>
            </p>
            {% endif %}
            <form method="POST" action="/upload" enctype="multipart/form-data">
                <div class="drop-zone" id="dropZone">
                    <p>Drag & drop a chat export zip, or click to browse</p>
                    <p class="filename" id="fileName"></p>
                    <input type="file" name="chat_history" id="fileInput" accept=".zip,.md,.txt">
                </div>
                <label for="scan_paths">Scan Paths</label>
                <input type="text" name="scan_paths" id="scanPaths" value="{{ scan_paths }}" placeholder="~ ~/projects">
                <input type="hidden" name="ai_analyze" id="aiAnalyzeHidden" value="{{ '1' if ai_config.api_key else '0' }}">
                <div class="btn-row">
                    <button type="submit" class="btn btn-upload" id="uploadBtn">Load & Refresh</button>
                    <button type="button" class="btn btn-cancel" onclick="document.getElementById('uploadModal').classList.remove('show')">Cancel</button>
                </div>
            </form>
        </div>
    </div>

    <!-- AI Settings Modal -->
    <div class="modal-overlay" id="aiModal">
        <div class="modal">
            <h2>AI Description Enrichment</h2>
            <p style="font-size:12px; color:var(--text-secondary); margin-bottom:14px;">
                Configure an Anthropic API endpoint so the dashboard can generate richer project descriptions.
                Your key is stored locally in ~/.claudesync_ai.json.
            </p>
            <label for="ai_url">API URL</label>
            <input type="text" id="ai_url" placeholder="https://api.anthropic.com/v1/messages" value="{{ ai_config.api_url }}">
            <label for="ai_key">API Key</label>
            <input type="text" id="ai_key" placeholder="sk-ant-..." value="">
            <p style="font-size:10px; color:var(--text-muted); margin-top:2px;">
                {% if ai_config.api_key %}Currently set ({{ ai_config.api_key[:8] }}...){% else %}Not configured{% endif %}
            </p>
            <label for="ai_model">Model</label>
            <select id="ai_model">
                <option value="claude-haiku-4-5-20251001" {{ 'selected' if ai_config.model == 'claude-haiku-4-5-20251001' }}>Haiku 4.5 (fastest, cheapest)</option>
                <option value="claude-sonnet-4-5-20250929" {{ 'selected' if ai_config.model == 'claude-sonnet-4-5-20250929' }}>Sonnet 4.5 (balanced)</option>
                <option value="claude-opus-4-6" {{ 'selected' if ai_config.model == 'claude-opus-4-6' }}>Opus 4.6 (most capable)</option>
            </select>
            <div class="btn-row">
                <button class="btn" style="background:#8e44ad;" onclick="saveAiConfig()">Save</button>
                <button type="button" class="btn btn-cancel" onclick="document.getElementById('aiModal').classList.remove('show')">Cancel</button>
            </div>
        </div>
    </div>

    <!-- AI Key Prompt (shown when no key exists and user clicks Load) -->
    <div class="modal-overlay" id="aiPromptModal">
        <div class="modal">
            <h2>Enable AI-Enhanced Results?</h2>
            <p style="font-size:13px; color:var(--text-secondary); margin-bottom:14px; line-height:1.5;">
                With an Anthropic API key, the dashboard will automatically:<br>
                &bull; Enrich project descriptions with AI-generated summaries<br>
                &bull; Classify unmatched chat conversations into initiatives<br>
                &bull; Verify project categorization
            </p>
            <label for="ai_prompt_key">API Key</label>
            <input type="text" id="ai_prompt_key" placeholder="sk-ant-..." style="font-family:monospace;">
            <p style="font-size:10px; color:var(--text-muted); margin-top:4px;">Stored locally in ~/.claudesync_ai.json. Never leaves this machine.</p>
            <div class="btn-row">
                <button class="btn" style="background:#8e44ad;" id="aiPromptOk" onclick="aiPromptAccept()">OK</button>
                <button type="button" class="btn btn-cancel" id="aiPromptSkip" onclick="aiPromptDecline()">Skip</button>
            </div>
        </div>
    </div>

    <script>
        // Track whether we're waiting on the AI prompt before submitting
        var _pendingFormData = null;

        function aiPromptAccept() {
            var key = document.getElementById('ai_prompt_key').value.trim();
            if (!key) { document.getElementById('ai_prompt_key').style.borderColor = '#E74C3C'; return; }
            var okBtn = document.getElementById('aiPromptOk');
            okBtn.textContent = 'Saving key...';
            okBtn.disabled = true;
            // Save the key
            fetch('/api/ai-config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ api_key: key, api_url: 'https://api.anthropic.com/v1/messages', model: 'claude-haiku-4-5-20251001' })
            })
            .then(function(r) { return r.json(); })
            .then(function() {
                okBtn.textContent = 'Key saved!';
                okBtn.style.background = '#2ECC71';
                setTimeout(function() {
                    document.getElementById('aiPromptModal').classList.remove('show');
                    if (_pendingFormData) {
                        _pendingFormData.set('ai_analyze', '1');
                        submitUpload(_pendingFormData);
                        _pendingFormData = null;
                    }
                }, 800);
            })
            .catch(function() {
                okBtn.textContent = 'Failed — try again';
                okBtn.style.background = '#E74C3C';
                okBtn.disabled = false;
            });
        }

        function aiPromptDecline() {
            document.getElementById('aiPromptModal').classList.remove('show');
            if (_pendingFormData) {
                _pendingFormData.set('ai_analyze', '0');
                submitUpload(_pendingFormData);
                _pendingFormData = null;
            }
        }

        function submitUpload(formData) {
            startProgressPolling();
            fetch('/upload', { method: 'POST', body: formData })
            .then(function(r) { return r.json(); })
            .then(function() { document.getElementById('uploadBtn').disabled = false; })
            .catch(function() { document.getElementById('uploadBtn').disabled = false; });
        }

        function saveAiConfig() {
            var body = {
                api_url: document.getElementById('ai_url').value,
                model: document.getElementById('ai_model').value,
            };
            var key = document.getElementById('ai_key').value;
            if (key) body.api_key = key;
            var saveBtn = document.querySelector('#aiModal .btn[style*="8e44ad"]');
            saveBtn.textContent = 'Saving...';
            saveBtn.disabled = true;
            fetch('/api/ai-config', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) })
            .then(r => r.json())
            .then(function() {
                saveBtn.textContent = 'Saved!';
                saveBtn.style.background = '#2ECC71';
                saveBtn.style.borderColor = '#2ECC71';
                saveBtn.style.color = 'white';
                setTimeout(function() {
                    document.getElementById('aiModal').classList.remove('show');
                    location.reload();
                }, 1200);
            })
            .catch(function() {
                saveBtn.textContent = 'Failed — try again';
                saveBtn.style.background = '#E74C3C';
                saveBtn.disabled = false;
            });
        }

        // ---- Dark mode ----
        function toggleTheme() {
            var cur = document.documentElement.getAttribute('data-theme');
            var next = cur === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            localStorage.setItem('theme', next);
            updateThemeIcon();
            updateChartColors();
        }
        function updateThemeIcon() {
            var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            document.getElementById('themeIcon').textContent = isDark ? 'Light' : 'Dark';
        }
        updateThemeIcon();

        function updateChartColors() {
            var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            var textColor = isDark ? '#909296' : '#666';
            var gridColor = isDark ? '#373a40' : '#e0e0e0';
            chart.options.scales.x.ticks.color = textColor;
            chart.options.scales.y.ticks.color = textColor;
            chart.options.scales.y.grid = { color: gridColor };
            chart.options.plugins.legend.labels.color = textColor;
            chart.update();
        }

        // ---- Chart.js ----
        const chartData = {{ chart_data | tojson }};
        const ctx = document.getElementById('activityChart').getContext('2d');
        let chart = new Chart(ctx, {
            type: 'bar',
            data: { labels: chartData.labels, datasets: chartData.datasets },
            options: {
                responsive: true,
                plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } } },
                scales: {
                    x: { stacked: true, grid: { display: false }, ticks: { font: { size: 10 } } },
                    y: { stacked: true, beginAtZero: true, ticks: { stepSize: 1, font: { size: 10 } } }
                }
            }
        });
        updateChartColors();

        function switchMode(mode, btn) {
            document.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            fetch('/api/chart-data?mode=' + mode)
                .then(r => r.json())
                .then(data => {
                    chart.data.labels = data.labels;
                    chart.data.datasets = data.datasets;
                    chart.update();
                    updateChartColors();
                });
        }

        // ---- Filter: active / eol / ignored ----
        var activeFilters = new Set(['active']);

        function toggleFilter(filter, btn) {
            if (activeFilters.has(filter)) {
                activeFilters.delete(filter);
                btn.classList.remove('active');
            } else {
                activeFilters.add(filter);
                btn.classList.add('active');
            }
            applyFilters();
        }

        function applyFilters() {
            document.querySelectorAll('.project-card').forEach(function(card) {
                var isEol = card.dataset.eol === 'yes';
                var isIgnored = card.dataset.ignored === 'yes';
                var isActive = !isEol && !isIgnored;
                var show = false;
                if (activeFilters.has('active') && isActive) show = true;
                if (activeFilters.has('eol') && isEol && !isIgnored) show = true;
                if (activeFilters.has('ignored') && isIgnored) show = true;
                card.classList.toggle('hidden', !show);
            });
        }
        applyFilters();

        // ---- Ignore/restore ----
        function ignoreProject(name) {
            fetch('/api/ignore', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name: name}) })
                .then(r => r.json())
                .then(() => location.reload());
        }
        function restoreProject(name) {
            fetch('/api/restore', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name: name}) })
                .then(r => r.json())
                .then(() => location.reload());
        }

        // ---- Non-blocking progress banner ----
        var _progressPoll = null;
        var STEP_LABELS = {
            'scanning': 'Scanning',
            'parsing': 'Parsing',
            'reading_chat': 'Reading Chat',
            'matching_chat': 'Matching Chat',
            'ai_enrichment': 'AI Enrichment',
            'ai_classify': 'AI Classifying',
            'building': 'Building',
            'generating_pdf': 'Generating PDF',
            'done': 'Done',
        };
        var STEP_PROGRESS = {
            'scanning': 10, 'parsing': 25, 'reading_chat': 40,
            'matching_chat': 60, 'ai_enrichment': 75, 'ai_classify': 80,
            'building': 90, 'generating_pdf': 50, 'done': 100,
        };

        function startProgressPolling() {
            // Clear any existing poll interval to prevent duplicates on reload
            if (_progressPoll) {
                clearInterval(_progressPoll);
                _progressPoll = null;
            }
            var banner = document.getElementById('progressBanner');
            banner.className = 'progress-banner show';
            _progressPoll = setInterval(function() {
                fetch('/api/progress').then(function(r) { return r.json(); }).then(function(data) {
                    var stepEl = document.getElementById('progressStep');
                    var detailEl = document.getElementById('progressDetail');
                    var fillEl = document.getElementById('progressFill');
                    stepEl.textContent = STEP_LABELS[data.step] || data.step || 'Starting...';
                    detailEl.textContent = data.detail || '';
                    fillEl.style.width = (STEP_PROGRESS[data.step] || 5) + '%';

                    if (!data.running) {
                        clearInterval(_progressPoll);
                        _progressPoll = null;
                        if (data.error) {
                            banner.className = 'progress-banner show error';
                            stepEl.textContent = 'Error';
                            detailEl.textContent = data.error;
                            // Don't auto-reload on error — let user read it
                        } else {
                            banner.className = 'progress-banner show done';
                            stepEl.textContent = 'Complete';
                            detailEl.textContent = data.result_msg || 'Done';
                            fillEl.style.width = '100%';
                            // Check for warnings in result message
                            var hasWarnings = data.result_msg && data.result_msg.indexOf('Warning') !== -1;
                            var delay = hasWarnings ? 5000 : 2500;
                            setTimeout(function() { location.reload(); }, delay);
                        }
                    }
                });
            }, 500);
        }

        // Intercept upload form — check for AI key, then submit via AJAX
        document.querySelector('#uploadModal form').addEventListener('submit', function(e) {
            e.preventDefault();
            var form = e.target;
            var formData = new FormData(form);
            document.getElementById('uploadModal').classList.remove('show');
            document.getElementById('uploadBtn').disabled = true;

            var hasKey = document.getElementById('aiAnalyzeHidden').value === '1';
            if (hasKey) {
                // Key already configured — auto-enable AI and submit
                formData.set('ai_analyze', '1');
                submitUpload(formData);
            } else {
                // No key — ask the user
                _pendingFormData = formData;
                document.getElementById('aiPromptModal').classList.add('show');
            }
        });

        // Check on page load if a background task is already running
        fetch('/api/progress').then(function(r) { return r.json(); }).then(function(data) {
            if (data.running) { startProgressPolling(); }
        });

        // ---- Drag and drop ----
        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');
        const fileName = document.getElementById('fileName');
        dropZone.addEventListener('click', () => fileInput.click());
        dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
        dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault(); dropZone.classList.remove('dragover');
            if (e.dataTransfer.files.length) { fileInput.files = e.dataTransfer.files; fileName.textContent = e.dataTransfer.files[0].name; }
        });
        fileInput.addEventListener('change', () => { if (fileInput.files.length) fileName.textContent = fileInput.files[0].name; });
    </script>
</body>
</html>
"""

# =============================================================================
# PROJECT DETAIL HTML
# =============================================================================

PROJECT_DETAIL_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ project.name }} -- Decision Timeline</title>
    <style>
        """ + THEME_CSS + """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); transition: background 0.3s, color 0.3s; }
        .top-bar { background: var(--bar-bg); color: var(--bar-text); padding: 16px 24px; display: flex; align-items: center; gap: 16px; }
        .top-bar a { color: #8cc4e8; text-decoration: none; font-size: 13px; }
        .top-bar a:hover { color: white; }
        .top-bar h1 { font-size: 18px; font-weight: 600; flex: 1; }
        .btn-theme { background: transparent; border: 1px solid rgba(255,255,255,0.3); color: var(--bar-text); font-size: 12px; padding: 5px 10px; border-radius: 4px; cursor: pointer; }
        .btn-theme:hover { background: rgba(255,255,255,0.1); }
        .container { max-width: 800px; margin: 0 auto; padding: 24px 20px; }
        .header-card { background: var(--bg-card); border-radius: 8px; padding: 22px; margin-bottom: 20px; box-shadow: 0 1px 3px var(--shadow); }
        .header-card .name { font-size: 20px; font-weight: 700; color: var(--heading); }
        .header-card .meta { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
        .progress-bar { height: 8px; background: var(--progress-bg); border-radius: 4px; overflow: hidden; margin: 12px 0; max-width: 300px; }
        .progress-fill { height: 100%; border-radius: 4px; }
        .summary { font-size: 13px; color: var(--text); line-height: 1.6; margin-top: 12px; }
        .section-title { font-size: 14px; font-weight: 600; color: var(--heading); margin: 24px 0 12px; }
        .timeline { position: relative; padding-left: 24px; }
        .timeline::before { content: ''; position: absolute; left: 7px; top: 4px; bottom: 4px; width: 2px; background: var(--border); }
        .timeline-entry { position: relative; margin-bottom: 16px; }
        .timeline-entry::before { content: ''; position: absolute; left: -20px; top: 6px; width: 10px; height: 10px; border-radius: 50%; border: 2px solid var(--bg); }
        .timeline-entry.commit::before { background: #3498DB; }
        .timeline-entry.chat::before { background: #9B59B6; }
        .timeline-entry.log::before { background: #2ECC71; }
        .timeline-entry .date { font-size: 11px; font-weight: 600; color: var(--text-secondary); }
        .timeline-entry .source { font-size: 10px; color: var(--text-muted); margin-left: 4px; }
        .timeline-entry .text { font-size: 13px; color: var(--text); margin-top: 2px; line-height: 1.5; }
        .thread-list { list-style: none; }
        .thread-list li { padding: 10px 0; border-bottom: 1px solid var(--border-light); font-size: 13px; color: var(--text); display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
        .thread-list li:last-child { border-bottom: none; }
        .thread-content { flex: 1; }
        .thread-meta { font-size: 10px; color: var(--text-muted); margin-top: 2px; }
        .tag { display: inline-block; padding: 1px 7px; border-radius: 3px; font-size: 10px; font-weight: 600; margin-right: 6px; }
        .tag-blocker { background: #fce4ec; color: #c62828; }
        .tag-question { background: #fff3e0; color: #e65100; }
        .tag-next { background: #e3f2fd; color: #1565c0; }
        .tag-notbuilt { background: var(--stat-bg); color: var(--text-secondary); }
        .btn-resolve { padding: 3px 10px; border: 1px solid var(--border); border-radius: 4px; font-size: 10px; font-weight: 600; cursor: pointer; background: var(--bg); color: var(--text-secondary); white-space: nowrap; }
        .btn-resolve:hover { background: #d4edda; color: #155724; border-color: #c3e6cb; }
        .resolved-count { font-size: 11px; color: var(--text-muted); margin-top: 8px; }
        .card { background: var(--bg-card); border-radius: 8px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 3px var(--shadow); }
        .btn-ai { display: inline-block; padding: 6px 14px; border: 1px solid #9B59B6; background: transparent; color: #9B59B6; border-radius: 5px; font-size: 11px; font-weight: 600; cursor: pointer; margin-top: 10px; }
        .btn-ai:hover { background: #9B59B6; color: white; }
        .btn-ai.loading { opacity: 0.5; pointer-events: none; }
        .ai-result { margin-top: 10px; padding: 12px; background: var(--stat-bg); border-radius: 6px; font-size: 13px; line-height: 1.6; color: var(--text); white-space: pre-wrap; }
        footer { text-align: center; font-size: 11px; color: var(--text-muted); margin-top: 40px; padding-bottom: 20px; }
        footer a { color: var(--text-muted); text-decoration: none; }
        footer a:hover { color: var(--text-secondary); }
    </style>
    <script>
        (function() {
            var t = localStorage.getItem('theme') || 'light';
            document.documentElement.setAttribute('data-theme', t);
        })();
    </script>
</head>
<body>
    <div class="top-bar">
        <a href="/">&larr; Dashboard</a>
        <h1>{{ project.name }}</h1>
        <button class="btn-theme" onclick="toggleTheme()" id="themeBtn"><span id="themeIcon"></span></button>
    </div>
    <div class="container">
        <!-- Project Header -->
        <div class="header-card">
            <div class="name">
                {{ project.name }}
                {% if project.dev_state %}<span class="badge badge-dev-state badge-dev-{{ project.dev_state|lower }}">{{ project.dev_state }}</span>{% endif %}
            </div>
            <div class="meta">
                {{ project.category_group }}
                &middot; {{ project.status }}
                {% if project.last_worked %}&middot; Last active: {{ project.last_worked }}{% endif %}
                {% if project.last_synced %}&middot; Synced to Claude.ai: {{ project.last_synced }}{% endif %}
            </div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: {{ project.progress }}%; background: {{ '#2ECC71' if project.progress > 75 else '#3498DB' if project.progress >= 50 else '#F1C40F' if project.progress >= 25 else '#E74C3C' }};"></div>
            </div>
            <div class="meta">{{ project.progress }}% complete</div>
            <div style="margin-top:10px; display:flex; align-items:center; gap:10px;">
                <label style="font-size:12px; font-weight:600; color:var(--text-secondary); margin:0;">Dev State:</label>
                <select id="devStateSelect" onchange="setDevState(this.value)" style="padding:4px 8px; border-radius:5px; border:1px solid var(--input-border); background:var(--input-bg); color:var(--text); font-size:12px;">
                    <option value="" {{ 'selected' if not project.dev_state }}>-- none --</option>
                    <option value="test" {{ 'selected' if project.dev_state == 'test' }}>test</option>
                    <option value="refine" {{ 'selected' if project.dev_state == 'refine' }}>refine</option>
                    <option value="continue" {{ 'selected' if project.dev_state == 'continue' }}>continue</option>
                </select>
                {% if ai_configured %}
                <button class="btn-ai" style="font-size:11px; padding:4px 10px;" onclick="aiAssessState()">AI Assess</button>
                {% endif %}
                <span id="devStateStatus" style="font-size:11px; color:var(--text-muted);"></span>
            </div>
            {% if project.narrative %}
            <div class="summary" id="projectDescription">{{ project.narrative }}</div>
            {% endif %}
            {% if ai_configured %}
            <button class="btn-ai" id="aiEnrichBtn" onclick="enrichDescription()">Enrich description with AI</button>
            <div class="ai-result" id="aiResult" style="display:none;"></div>
            {% endif %}
        </div>

        <!-- Decision Timeline -->
        <div class="card">
            <div class="section-title">Decision Timeline ({{ project.timeline | length }} events)</div>
            <div class="timeline">
                {% for entry in project.timeline %}
                {% set src = entry.source|lower %}
                <div class="timeline-entry {{ 'commit' if 'commit' in src or 'git' in src else 'chat' if 'chat' in src else 'log' }}">
                    <div>
                        <span class="date">{{ entry.date }}</span>
                        <span class="source">{{ entry.source }}</span>
                    </div>
                    <div class="text">{{ entry.text }}</div>
                </div>
                {% endfor %}
                {% if not project.timeline %}
                <p style="font-size:13px; color: var(--text-muted); padding: 12px 0;">No timeline entries yet.</p>
                {% endif %}
            </div>
        </div>

        <!-- Open Threads -->
        {% if active_threads or resolved_count > 0 %}
        <div class="card">
            <div class="section-title">Open Threads ({{ active_threads | length }})</div>
            <ul class="thread-list" id="threadList">
                {% for thread_type, thread_text in active_threads %}
                <li id="thread-{{ loop.index0 }}">
                    <div class="thread-content">
                        {% if thread_type == 'Blocker' %}<span class="tag tag-blocker">Blocker</span>
                        {% elif thread_type == 'Open Question' %}<span class="tag tag-question">Question</span>
                        {% elif thread_type == 'Next Step' %}<span class="tag tag-next">Next</span>
                        {% else %}<span class="tag tag-notbuilt">{{ thread_type }}</span>{% endif %}
                        {{ thread_text }}
                        <div class="thread-meta">{{ project.name }}</div>
                    </div>
                    <button class="btn-resolve" onclick="resolveThread('{{ project.name }}', '{{ thread_text[:100]|e }}', this)">Resolve</button>
                </li>
                {% endfor %}
            </ul>
            {% if resolved_count > 0 %}
            <div class="resolved-count">{{ resolved_count }} thread{{ 's' if resolved_count != 1 }} previously resolved</div>
            {% endif %}
        </div>
        {% endif %}

        <footer>
            <a href="/">&larr; Back to Dashboard</a>
        </footer>
    </div>
    <script>
        function toggleTheme() {
            var cur = document.documentElement.getAttribute('data-theme');
            var next = cur === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            localStorage.setItem('theme', next);
            document.getElementById('themeIcon').textContent = next === 'dark' ? 'Light' : 'Dark';
        }
        document.getElementById('themeIcon').textContent =
            document.documentElement.getAttribute('data-theme') === 'dark' ? 'Light' : 'Dark';

        function resolveThread(projectName, threadText, btn) {
            btn.textContent = 'Resolving...';
            btn.disabled = true;
            fetch('/api/resolve-thread', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({project: projectName, text: threadText})
            })
            .then(r => r.json())
            .then(function() {
                var li = btn.closest('li');
                li.style.opacity = '0.3';
                li.style.textDecoration = 'line-through';
                btn.textContent = 'Resolved';
            });
        }

        function enrichDescription() {
            var btn = document.getElementById('aiEnrichBtn');
            var result = document.getElementById('aiResult');
            btn.classList.add('loading');
            btn.textContent = 'Thinking...';
            result.style.display = 'none';

            fetch('/api/enrich/{{ project_idx }}', { method: 'POST' })
            .then(r => r.json())
            .then(function(data) {
                btn.classList.remove('loading');
                btn.textContent = 'Enrich description with AI';
                if (data.description) {
                    result.textContent = data.description;
                    result.style.display = 'block';
                } else if (data.error) {
                    result.textContent = 'Error: ' + data.error;
                    result.style.display = 'block';
                }
            })
            .catch(function() {
                btn.classList.remove('loading');
                btn.textContent = 'Enrich description with AI';
                result.textContent = 'Failed to connect to AI API';
                result.style.display = 'block';
            });
        }

        function setDevState(state) {
            var status = document.getElementById('devStateStatus');
            status.textContent = 'Saving...';
            fetch('/api/dev-state/{{ project_idx }}', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({dev_state: state})
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.ok) {
                    status.textContent = 'Saved';
                    setTimeout(function() { status.textContent = ''; }, 2000);
                } else {
                    status.textContent = 'Error: ' + (data.error || 'unknown');
                }
            })
            .catch(function() { status.textContent = 'Failed to save'; });
        }

        function aiAssessState() {
            var status = document.getElementById('devStateStatus');
            status.textContent = 'AI assessing...';
            fetch('/api/ai-assess-state/{{ project_idx }}', { method: 'POST' })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.dev_state) {
                    document.getElementById('devStateSelect').value = data.dev_state;
                    status.textContent = 'AI suggests: ' + data.dev_state + (data.reason ? ' — ' + data.reason : '');
                } else if (data.error) {
                    status.textContent = 'Error: ' + data.error;
                }
            })
            .catch(function() { status.textContent = 'AI assessment failed'; });
        }
    </script>
</body>
</html>
"""


# =============================================================================
# AI HELPERS
# =============================================================================

def _call_ai(prompt, max_tokens=300):
    """Call the configured AI API. Returns text or None on failure."""
    import urllib.request
    import urllib.error

    ai_config = _load_ai_config()
    api_url = ai_config.get('api_url', '')
    api_key = ai_config.get('api_key', '')
    model = ai_config.get('model', 'claude-haiku-4-5-20251001')

    if not api_url or not api_key:
        return None

    req_body = json.dumps({
        'model': model,
        'max_tokens': max_tokens,
        'messages': [{'role': 'user', 'content': prompt}],
    }).encode('utf-8')

    req = urllib.request.Request(api_url, data=req_body)
    req.add_header('Content-Type', 'application/json')
    req.add_header('x-api-key', api_key)
    req.add_header('anthropic-version', '2023-06-01')

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            return result.get('content', [{}])[0].get('text', '')
    except Exception as e:
        print(f"AI call failed: {e}")
        return None


def _ai_enrich_all_projects():
    """Use AI to generate richer descriptions for all projects.

    Sends each project's context (timeline, features, chat snippets,
    threads) to the AI and updates the narrative in the cache.
    Returns count of enriched projects.
    """
    projects = _get_projects()
    enriched = 0

    for project in projects:
        timeline = project.get('timeline', [])
        if not timeline and not project.get('features'):
            continue  # nothing to analyze

        timeline_text = '\n'.join(
            f"- {e.get('date', '?')}: [{e.get('source', '')}] {e.get('text', '')}"
            for e in timeline[:15]
        )
        threads_text = '\n'.join(
            f"- [{t}] {txt}" for t, txt in project.get('open_threads', [])
        )
        features_text = '\n'.join(f"- {f}" for f in project.get('features', []))
        not_working = '\n'.join(f"- {f}" for f in project.get('not_working', []))

        prompt = f"""Summarize this project in 3-5 clear sentences. Include what it does, current state, and what's actively happening.

Project: {project.get('name', '')}
Status: {project.get('status', 'Unknown')} ({project.get('progress', 0)}% complete)
Category: {project.get('category_group', '')}

What's working:
{features_text or 'None listed'}

What's not working yet:
{not_working or 'None listed'}

Recent activity:
{timeline_text or 'No recent activity'}

Open threads:
{threads_text or 'None'}

Be specific and factual. No filler language."""

        result = _call_ai(prompt, max_tokens=250)
        if result:
            project['narrative'] = result
            enriched += 1
            print(f"  AI enriched: {project.get('name', '')}")

    return enriched


# =============================================================================
# ROUTES
# =============================================================================

@app.route('/')
def dashboard():
    projects = _get_projects()
    if not projects:
        # If no background task running, kick one off (non-blocking)
        with _bg_task['lock']:
            already_running = _bg_task['running']
        if not already_running:
            t = threading.Thread(
                target=_bg_run_load,
                args=(_project_cache.get('scan_paths', '~'), None, False),
                daemon=True,
            )
            t.start()

    ignored_names = _load_ignored()
    archived_names = _load_archived()

    # Only count non-ignored, non-archived projects in stats
    visible = [p for p in projects
                if p.get('name', '') not in ignored_names
                and p.get('name', '') not in archived_names]

    chart_data = _aggregate_activity(visible, mode='day')
    project_cards = _project_activity_breakdown(projects)  # all projects, for filtering

    total_events = sum(c['total_events'] for c in project_cards if c['name'] not in ignored_names)
    total_threads = sum(c['open_threads'] for c in project_cards if c['name'] not in ignored_names)
    total_blockers = sum(c['blockers'] for c in project_cards if c['name'] not in ignored_names)

    ai_config = _load_ai_config()
    import_meta = _load_import_meta()

    # Count unmatched chats
    chat_stats = getattr(load_projects, '_last_chat_stats', {})
    unmatched_count = len(chat_stats.get('unmatched_chats', []))

    return render_template_string(
        DASHBOARD_HTML,
        total_projects=len(visible),
        total_events=total_events,
        total_threads=total_threads,
        total_blockers=total_blockers,
        unmatched_count=unmatched_count,
        chart_data=chart_data,
        project_cards=project_cards,
        ignored_names=ignored_names,
        scan_paths=_project_cache.get('scan_paths', '~'),
        ai_config=ai_config,
        import_meta=import_meta,
    )


@app.route('/api/progress')
def api_progress():
    """Return current background task progress."""
    with _bg_task['lock']:
        return jsonify({
            'running': _bg_task['running'],
            'step': _bg_task['step'],
            'detail': _bg_task['detail'],
            'error': _bg_task['error'],
            'result_msg': _bg_task['result_msg'],
        })


@app.route('/api/chart-data')
def api_chart_data():
    mode = request.args.get('mode', 'day')
    ignored_names = _load_ignored()
    projects = [p for p in _get_projects()
                if p.get('name', '') not in ignored_names]
    data = _aggregate_activity(projects, mode=mode)
    return jsonify(data)


@app.route('/api/ignore', methods=['POST'])
def api_ignore():
    """Add a project to the ignored list."""
    data = request.get_json(force=True)
    name = data.get('name', '')
    if name:
        ignored = _load_ignored()
        ignored.add(name)
        _save_ignored(ignored)
    return jsonify({'ok': True, 'ignored': sorted(_load_ignored())})


@app.route('/api/restore', methods=['POST'])
def api_restore():
    """Remove a project from the ignored list."""
    data = request.get_json(force=True)
    name = data.get('name', '')
    if name:
        ignored = _load_ignored()
        ignored.discard(name)
        _save_ignored(ignored)
    return jsonify({'ok': True, 'ignored': sorted(_load_ignored())})


@app.route('/project/<int:idx>')
def project_detail(idx):
    projects = _get_projects()
    if idx < 0 or idx >= len(projects):
        flash('Project not found.', 'error')
        return redirect(url_for('dashboard'))

    project = projects[idx]
    resolved = _load_resolved()
    name = project.get('name', '')

    all_threads = project.get('open_threads', [])
    active_threads = [(t, txt) for t, txt in all_threads
                      if _thread_key(name, txt) not in resolved]
    resolved_count = len(all_threads) - len(active_threads)

    ai_config = _load_ai_config()
    ai_configured = bool(ai_config.get('api_url') and ai_config.get('api_key'))

    return render_template_string(
        PROJECT_DETAIL_HTML,
        project=project,
        project_idx=idx,
        active_threads=active_threads,
        resolved_count=resolved_count,
        ai_configured=ai_configured,
    )


@app.route('/api/resolve-thread', methods=['POST'])
def api_resolve_thread():
    """Mark a thread as resolved."""
    data = request.get_json(force=True)
    project_name = data.get('project', '')
    thread_text = data.get('text', '')
    if project_name and thread_text:
        resolved = _load_resolved()
        resolved.add(_thread_key(project_name, thread_text))
        _save_resolved(resolved)
    return jsonify({'ok': True})


@app.route('/api/enrich/<int:idx>', methods=['POST'])
def api_enrich(idx):
    """Use AI to generate a richer project description."""
    projects = _get_projects()
    if idx < 0 or idx >= len(projects):
        return jsonify({'error': 'Project not found'}), 404

    project = projects[idx]

    timeline_text = '\n'.join(
        f"- {e.get('date', '?')}: [{e.get('source', '')}] {e.get('text', '')}"
        for e in project.get('timeline', [])[:15]
    )
    threads_text = '\n'.join(
        f"- [{t}] {txt}" for t, txt in project.get('open_threads', [])
    )
    features_text = '\n'.join(f"- {f}" for f in project.get('features', []))
    not_working = '\n'.join(f"- {f}" for f in project.get('not_working', []))

    prompt = f"""Summarize this project in 3-5 clear sentences. Include what it does, current state, and what's actively happening.

Project: {project.get('name', '')}
Status: {project.get('status', 'Unknown')} ({project.get('progress', 0)}% complete)
Category: {project.get('category_group', '')}
Current description: {project.get('summary', 'None')}

What's working:
{features_text or 'None listed'}

What's not working yet:
{not_working or 'None listed'}

Recent activity:
{timeline_text or 'No recent activity'}

Open threads:
{threads_text or 'None'}

Be specific and factual. No filler language."""

    result = _call_ai(prompt, max_tokens=250)
    if result:
        project['narrative'] = result
        return jsonify({'description': result})
    else:
        return jsonify({'error': 'AI not configured or call failed. Check AI Settings.'})


@app.route('/api/ai-config', methods=['GET', 'POST'])
def api_ai_config():
    """Get or set AI API configuration."""
    if request.method == 'GET':
        config = _load_ai_config()
        # Mask the key for display
        if config.get('api_key'):
            config['api_key_masked'] = config['api_key'][:8] + '...'
        return jsonify(config)

    data = request.get_json(force=True)
    config = _load_ai_config()
    if 'api_url' in data:
        config['api_url'] = data['api_url']
    if 'api_key' in data:
        config['api_key'] = data['api_key']
    if 'model' in data:
        config['model'] = data['model']
    _save_ai_config(config)
    return jsonify({'ok': True})


@app.route('/api/dev-state/<int:idx>', methods=['POST'])
def api_set_dev_state(idx):
    """Set the dev state for a project and persist it to PROJECT_STATUS.md."""
    projects = _get_projects()
    if idx < 0 or idx >= len(projects):
        return jsonify({'error': 'Project not found'}), 404

    data = request.get_json(force=True)
    new_state = data.get('dev_state', '').strip().lower()
    if new_state and new_state not in ('test', 'refine', 'continue'):
        return jsonify({'error': f'Invalid dev_state: must be test, refine, continue, or empty'}), 400
    project = projects[idx]
    project['dev_state'] = new_state

    # Also persist to the PROJECT_STATUS.md file if we have it
    status_file = project.get('file_path', '')
    if status_file and os.path.isfile(status_file):
        try:
            with open(status_file, 'r') as f:
                content = f.read()
            # Try to update existing Dev State line
            updated = re.sub(
                r'(\*\*Dev State\*\*\s*\|\s*)(.+)',
                r'\g<1>' + (new_state or '[test/refine/continue]'),
                content
            )
            if updated == content and new_state:
                # No existing Dev State line — insert after Status line
                updated = re.sub(
                    r'(\| \*\*Status\*\* \|[^\n]+\n)',
                    r'\1| **Dev State** | ' + new_state + ' |\n',
                    content
                )
            if updated != content:
                with open(status_file, 'w') as f:
                    f.write(updated)
        except Exception as e:
            print(f"Warning: could not persist dev_state to {status_file}: {e}")

    return jsonify({'ok': True, 'dev_state': new_state})


@app.route('/api/ai-assess-state/<int:idx>', methods=['POST'])
def api_ai_assess_state(idx):
    """Use AI to assess which dev state a project should be in."""
    projects = _get_projects()
    if idx < 0 or idx >= len(projects):
        return jsonify({'error': 'Project not found'}), 404

    project = projects[idx]

    timeline_text = '\n'.join(
        f"- {e.get('date', '?')}: [{e.get('source', '')}] {e.get('text', '')}"
        for e in project.get('timeline', [])[:20]
    )
    threads_text = '\n'.join(
        f"- [{t}] {txt}" for t, txt in project.get('open_threads', [])
    )

    prompt = f"""Classify this project into exactly ONE development state. The three states are:

- test: Code was pushed with no evidence of testing. Needs testing before proceeding.
- refine: The user seems satisfied or is riffing/exploring. Chat was abandoned in a good state. Refinement work.
- continue: Active testing is ongoing but not resolved. Work in progress that needs continuation.

Project: {project.get('name', '')}
Status: {project.get('status', 'Unknown')} ({project.get('progress', 0)}% complete)

Recent activity:
{timeline_text or 'No recent activity'}

Open threads:
{threads_text or 'None'}

Reply with ONLY a JSON object like: {{"state": "test", "reason": "brief reason"}}
No other text."""

    result = _call_ai(prompt, max_tokens=100)
    if result:
        try:
            parsed = json.loads(result.strip())
            state = parsed.get('state', '').lower()
            reason = parsed.get('reason', '')
            if state in ('test', 'refine', 'continue'):
                project['dev_state'] = state
                return jsonify({'dev_state': state, 'reason': reason})
        except (json.JSONDecodeError, AttributeError):
            # Try to extract state from freeform response
            result_lower = result.lower()
            for s in ('test', 'refine', 'continue'):
                if s in result_lower:
                    project['dev_state'] = s
                    return jsonify({'dev_state': s, 'reason': result.strip()})
        return jsonify({'error': 'AI returned unexpected format: ' + result[:200]})
    return jsonify({'error': 'AI not configured or call failed. Check AI Settings.'})


@app.route('/upload', methods=['POST'])
def upload():
    """Accept upload, kick off background processing, return immediately."""
    # Check if already running
    with _bg_task['lock']:
        if _bg_task['running']:
            return jsonify({'error': 'A task is already running'}), 409

    chat_history_path = None
    chat_file = request.files.get('chat_history')
    if chat_file and chat_file.filename:
        save_path = os.path.join(UPLOAD_DIR, chat_file.filename)
        chat_file.save(save_path)
        chat_history_path = save_path
        print(f"Chat history uploaded: {save_path}")

        meta = _load_import_meta()
        meta['last_import'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        meta['last_file'] = chat_file.filename
        _save_import_meta(meta)

    scan_paths_str = request.form.get('scan_paths', '~').strip() or '~'
    ai_analyze = request.form.get('ai_analyze') == '1'

    # Launch background thread
    t = threading.Thread(
        target=_bg_run_load,
        args=(scan_paths_str, chat_history_path, ai_analyze),
        daemon=True,
    )
    t.start()

    return jsonify({'ok': True, 'message': 'Processing started'})


@app.route('/generate-pdf')
def generate_pdf():
    projects = _get_projects()

    if not projects:
        flash('No projects found. Upload data first.', 'error')
        return redirect(url_for('dashboard'))

    today = datetime.now().strftime('%Y-%m-%d')
    output_path = os.path.join(UPLOAD_DIR, f'Project_Portfolio_Status_{today}.pdf')

    try:
        create_pdf(output_path, projects)
    except Exception as e:
        flash(f'Error generating PDF: {e}', 'error')
        return redirect(url_for('dashboard'))

    return send_file(
        output_path,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'Project_Portfolio_Status_{today}.pdf'
    )


# =============================================================================
# LIST VIEW TEMPLATE (shared by /view/projects, /events, /threads, /blockers)
# =============================================================================

LIST_VIEW_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} -- Dashboard</title>
    <style>
        """ + THEME_CSS + """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); }
        .top-bar { background: var(--bar-bg); color: var(--bar-text); padding: 16px 24px; display: flex; align-items: center; gap: 16px; }
        .top-bar a { color: #8cc4e8; text-decoration: none; font-size: 13px; }
        .top-bar a:hover { color: white; }
        .top-bar h1 { font-size: 18px; font-weight: 600; flex: 1; }
        .btn-theme { background: transparent; border: 1px solid rgba(255,255,255,0.3); color: var(--bar-text); font-size: 12px; padding: 5px 10px; border-radius: 4px; cursor: pointer; }
        .container { max-width: 900px; margin: 0 auto; padding: 24px 20px; }
        .list-card { background: var(--bg-card); border-radius: 8px; margin-bottom: 10px; box-shadow: 0 1px 3px var(--shadow); overflow: hidden; }
        .list-item { padding: 14px 18px; display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; border-bottom: 1px solid var(--border-light); }
        .list-item:last-child { border-bottom: none; }
        .list-item .main { flex: 1; }
        .list-item .title { font-size: 13px; font-weight: 600; color: var(--heading); }
        .list-item .subtitle { font-size: 11px; color: var(--text-secondary); margin-top: 2px; }
        .list-item .detail { font-size: 12px; color: var(--text); margin-top: 4px; line-height: 1.5; }
        .list-item .actions { display: flex; gap: 6px; align-items: center; flex-shrink: 0; }
        .btn-sm { padding: 4px 12px; border: 1px solid var(--border); border-radius: 4px; font-size: 10px; font-weight: 600; cursor: pointer; background: var(--bg); color: var(--text-secondary); }
        .btn-sm:hover { background: var(--stat-bg); }
        .btn-sm.btn-archive { border-color: #e67e22; color: #e67e22; }
        .btn-sm.btn-archive:hover { background: #e67e22; color: white; }
        .btn-sm.btn-unarchive { border-color: #2ECC71; color: #2ECC71; }
        .btn-sm.btn-unarchive:hover { background: #2ECC71; color: white; }
        .btn-sm.btn-resolve { border-color: #2ECC71; color: #2ECC71; }
        .btn-sm.btn-resolve:hover { background: #d4edda; color: #155724; }
        .tag { display: inline-block; padding: 1px 7px; border-radius: 3px; font-size: 10px; font-weight: 600; margin-right: 4px; }
        .tag-blocker { background: #fce4ec; color: #c62828; }
        .tag-question { background: #fff3e0; color: #e65100; }
        .tag-next { background: #e3f2fd; color: #1565c0; }
        .tag-notbuilt { background: var(--stat-bg); color: var(--text-secondary); }
        .tag-archived { background: #fff3e0; color: #e67e22; }
        .tag-commit { background: #e3f2fd; color: #1565c0; }
        .tag-chat { background: #f3e5f5; color: #7b1fa2; }
        .tag-log { background: #e8f5e9; color: #2e7d32; }
        .section-header { font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; padding: 20px 0 8px; }
        .section-header .badge { display: inline-block; background: var(--heading); color: white; font-size: 10px; padding: 1px 8px; border-radius: 10px; margin-left: 6px; vertical-align: middle; }
        .empty { font-size: 13px; color: var(--text-muted); padding: 20px; text-align: center; }
        .progress-bar { height: 5px; background: var(--progress-bg); border-radius: 3px; overflow: hidden; width: 80px; display: inline-block; vertical-align: middle; margin-left: 8px; }
        .progress-fill { height: 100%; border-radius: 3px; }
        .btn-sm.btn-ignore { border-color: #95a5a6; color: #95a5a6; }
        .btn-sm.btn-ignore:hover { background: #95a5a6; color: white; }
        .btn-sm.btn-reassign { border-color: #8e44ad; color: #8e44ad; }
        .btn-sm.btn-reassign:hover { background: #8e44ad; color: white; }
        .btn-sm.btn-undo { border-color: #3498db; color: #3498db; }
        .btn-sm.btn-undo:hover { background: #3498db; color: white; }
        .btn-sm.btn-verify { border-color: #e67e22; color: #e67e22; }
        .btn-sm.btn-verify:hover { background: #e67e22; color: white; }
        .reassign-dropdown { display: none; position: absolute; right: 0; top: 100%; background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; box-shadow: 0 4px 12px var(--shadow-hover); z-index: 50; min-width: 200px; max-height: 250px; overflow-y: auto; }
        .reassign-dropdown.show { display: block; }
        .reassign-dropdown a { display: block; padding: 8px 14px; font-size: 12px; color: var(--text); text-decoration: none; border-bottom: 1px solid var(--border-light); }
        .reassign-dropdown a:hover { background: var(--stat-bg); }
        .reassign-dropdown a:last-child { border-bottom: none; }
        .actions { position: relative; }
        .item-ignored { opacity: 0.4; }
        .item-reassigned { border-left: 3px solid #8e44ad; }
        .confidence-bar { display: inline-block; width: 50px; height: 4px; background: var(--progress-bg); border-radius: 2px; vertical-align: middle; margin-left: 6px; }
        .confidence-fill { height: 100%; border-radius: 2px; }
        .flag { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 9px; font-weight: 700; margin-left: 4px; }
        .flag-low { background: #fce4ec; color: #c62828; }
        .flag-ok { background: #e8f5e9; color: #2e7d32; }
        footer { text-align: center; font-size: 11px; color: var(--text-muted); margin-top: 30px; }
        footer a { color: var(--text-muted); text-decoration: none; }
    </style>
    <script>
        (function() {
            var t = localStorage.getItem('theme') || 'light';
            document.documentElement.setAttribute('data-theme', t);
        })();
    </script>
</head>
<body>
    <div class="top-bar">
        <a href="/">&larr; Dashboard</a>
        <h1>{{ title }}</h1>
        <button class="btn-theme" onclick="toggleTheme()"><span id="themeIcon"></span></button>
    </div>
    <div class="container">
        {{ content|safe }}
        <footer><a href="/">&larr; Back to Dashboard</a></footer>
    </div>
    <script>
        function toggleTheme() {
            var cur = document.documentElement.getAttribute('data-theme');
            var next = cur === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            localStorage.setItem('theme', next);
            document.getElementById('themeIcon').textContent = next === 'dark' ? 'Light' : 'Dark';
        }
        document.getElementById('themeIcon').textContent =
            document.documentElement.getAttribute('data-theme') === 'dark' ? 'Light' : 'Dark';

        function apiAction(url, body, el) {
            el.disabled = true;
            el.textContent = '...';
            fetch(url, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) })
            .then(r => r.json())
            .then(function() { location.reload(); });
        }

        function toggleDropdown(id) {
            var el = document.getElementById(id);
            // Close all other dropdowns first
            document.querySelectorAll('.reassign-dropdown.show').forEach(function(d) {
                if (d.id !== id) d.classList.remove('show');
            });
            el.classList.toggle('show');
        }

        function reassignItem(key, targetProject) {
            apiAction('/api/item-action', {key: key, action: 'reassigned', target_project: targetProject}, document.createElement('button'));
        }

        // Close dropdowns when clicking outside
        document.addEventListener('click', function(e) {
            if (!e.target.closest('.actions')) {
                document.querySelectorAll('.reassign-dropdown.show').forEach(function(d) { d.classList.remove('show'); });
            }
        });
    </script>
</body>
</html>
"""


@app.route('/view/projects')
def view_projects():
    projects = _get_projects()
    archived = _load_archived()
    ignored = _load_ignored()

    active_html = ''
    archived_html = ''

    for i, p in enumerate(projects):
        name = p.get('name', 'Unknown')
        progress = p.get('progress', 0)
        color = '#2ECC71' if progress > 75 else '#3498DB' if progress >= 50 else '#F1C40F' if progress >= 25 else '#E74C3C'
        is_archived = name in archived

        item = f'''<div class="list-item">
            <div class="main">
                <div class="title"><a href="/project/{i}" style="color:inherit; text-decoration:none;">{name}</a>
                    <div class="progress-bar"><div class="progress-fill" style="width:{progress}%; background:{color};"></div></div>
                    {' <span class="tag tag-archived">Archived</span>' if is_archived else ''}
                </div>
                <div class="subtitle">{p.get("category_group", "")} &middot; {p.get("status", "")} &middot; {p.get("last_worked", "")}</div>
            </div>
            <div class="actions">'''

        if is_archived:
            item += f'<button class="btn-sm btn-unarchive" onclick="apiAction(\'/api/unarchive\', {{name:\'{name}\'}}, this)">Unarchive</button>'
        else:
            item += f'<button class="btn-sm btn-archive" onclick="apiAction(\'/api/archive\', {{name:\'{name}\'}}, this)">Archive</button>'

        item += '</div></div>'

        if is_archived:
            archived_html += item
        else:
            active_html += item

    content = '<div class="section-header">Active Projects</div>'
    content += f'<div class="list-card">{active_html}</div>' if active_html else '<div class="empty">No active projects</div>'
    if archived_html:
        content += '<div class="section-header">Archived</div>'
        content += f'<div class="list-card">{archived_html}</div>'

    return render_template_string(LIST_VIEW_HTML, title=f'All Projects ({len(projects)})', content=content)


@app.route('/view/events')
def view_events():
    projects = _get_projects()
    ignored = _load_ignored()

    all_events = []
    for i, p in enumerate(projects):
        if p.get('name', '') in ignored:
            continue
        for e in p.get('timeline', []):
            src = e.get('source', '').lower()
            if 'commit' in src:
                tag = '<span class="tag tag-commit">Commit</span>'
            elif 'chat' in src:
                tag = '<span class="tag tag-chat">Chat</span>'
            else:
                tag = '<span class="tag tag-log">Log</span>'
            all_events.append({
                'date': e.get('date', ''),
                'text': e.get('text', ''),
                'source': e.get('source', ''),
                'project': p.get('name', ''),
                'project_idx': i,
                'tag': tag,
            })

    all_events.sort(key=lambda x: x['date'], reverse=True)

    items = ''
    for ev in all_events:
        items += f'''<div class="list-item">
            <div class="main">
                <div class="title">{ev['tag']} {ev['text'][:120]}</div>
                <div class="subtitle">{ev['date']} &middot; <a href="/project/{ev['project_idx']}" style="color:inherit;">{ev['project']}</a> &middot; {ev['source']}</div>
            </div>
        </div>'''

    content = f'<div class="list-card">{items}</div>' if items else '<div class="empty">No events</div>'
    return render_template_string(LIST_VIEW_HTML, title=f'All Events ({len(all_events)})', content=content)


@app.route('/view/threads')
def view_threads():
    projects = _get_projects()
    resolved = _load_resolved()
    ignored = _load_ignored()

    items = ''
    count = 0
    for i, p in enumerate(projects):
        name = p.get('name', '')
        if name in ignored:
            continue
        for t_type, t_text in p.get('open_threads', []):
            key = _thread_key(name, t_text)
            if key in resolved:
                continue
            count += 1
            tag_class = {'Blocker': 'tag-blocker', 'Open Question': 'tag-question',
                         'Next Step': 'tag-next'}.get(t_type, 'tag-notbuilt')
            items += f'''<div class="list-item">
                <div class="main">
                    <div class="title"><span class="tag {tag_class}">{t_type}</span> {t_text}</div>
                    <div class="subtitle"><a href="/project/{i}" style="color:inherit;">{name}</a></div>
                </div>
                <div class="actions">
                    <button class="btn-sm btn-resolve" onclick="apiAction('/api/resolve-thread', {{project:'{name}', text:'{t_text[:100].replace(chr(39), "&#39;")}'}}, this)">Resolve</button>
                </div>
            </div>'''

    content = f'<div class="list-card">{items}</div>' if items else '<div class="empty">No open threads</div>'
    return render_template_string(LIST_VIEW_HTML, title=f'Open Threads ({count})', content=content)


@app.route('/view/blockers')
def view_blockers():
    projects = _get_projects()
    resolved = _load_resolved()
    ignored = _load_ignored()

    items = ''
    count = 0
    for i, p in enumerate(projects):
        name = p.get('name', '')
        if name in ignored:
            continue
        for t_type, t_text in p.get('open_threads', []):
            if t_type != 'Blocker':
                continue
            key = _thread_key(name, t_text)
            if key in resolved:
                continue
            count += 1
            items += f'''<div class="list-item">
                <div class="main">
                    <div class="title"><span class="tag tag-blocker">Blocker</span> {t_text}</div>
                    <div class="subtitle"><a href="/project/{i}" style="color:inherit;">{name}</a></div>
                </div>
                <div class="actions">
                    <button class="btn-sm btn-resolve" onclick="apiAction('/api/resolve-thread', {{project:'{name}', text:'{t_text[:100].replace(chr(39), "&#39;")}'}}, this)">Resolve</button>
                </div>
            </div>'''

    content = f'<div class="list-card">{items}</div>' if items else '<div class="empty">No blockers</div>'
    return render_template_string(LIST_VIEW_HTML, title=f'Blockers ({count})', content=content)


@app.route('/api/archive', methods=['POST'])
def api_archive():
    data = request.get_json(force=True)
    name = data.get('name', '')
    if name:
        archived = _load_archived()
        archived.add(name)
        _save_archived(archived)
    return jsonify({'ok': True})


@app.route('/api/unarchive', methods=['POST'])
def api_unarchive():
    data = request.get_json(force=True)
    name = data.get('name', '')
    if name:
        archived = _load_archived()
        archived.discard(name)
        _save_archived(archived)
    return jsonify({'ok': True})


@app.route('/view/whats-next')
def view_whats_next():
    """Cross-project view: what needs to happen next for every project."""
    projects = _get_projects()
    if not projects:
        with _bg_task['lock']:
            already_running = _bg_task['running']
        if not already_running:
            t = threading.Thread(
                target=_bg_run_load,
                args=(_project_cache.get('scan_paths', '~'), None, False),
                daemon=True,
            )
            t.start()

    ignored = _load_ignored()
    archived = _load_archived()
    resolved = _load_resolved()
    item_actions = _load_item_actions()
    ai_config = _load_ai_config()
    has_ai = bool(ai_config.get('api_key'))

    # Collect project names for reassign dropdown
    project_names = [p.get('name', '') for p in projects
                     if p.get('name', '') not in ignored and p.get('name', '') not in archived]

    # Build sections
    next_items = []      # Active items per project
    flagged_items = []   # Items that have been reassigned (show in target project)
    ignored_items = []   # Dismissed items

    dropdown_counter = 0

    for i, p in enumerate(projects):
        name = p.get('name', '')
        if name in ignored or name in archived:
            continue

        category = p.get('category_group', 'Uncategorized')
        progress = p.get('progress', 0)
        status = p.get('status', 'Unknown')

        # Gather all actionable items for this project
        project_items = []

        # Next Steps (highest priority)
        for step in p.get('next_steps', []):
            key = _item_key(name, 'Next Step', step)
            project_items.append({
                'key': key, 'type': 'Next Step', 'text': step,
                'project': name, 'project_idx': i,
                'tag_class': 'tag-next', 'priority': 1,
            })

        # Blockers
        for b in p.get('blockers', []):
            key = _item_key(name, 'Blocker', b)
            tkey = _thread_key(name, b)
            if tkey in resolved:
                continue
            project_items.append({
                'key': key, 'type': 'Blocker', 'text': b,
                'project': name, 'project_idx': i,
                'tag_class': 'tag-blocker', 'priority': 0,
            })

        # Open Questions
        for q in p.get('open_questions', []):
            key = _item_key(name, 'Open Question', q)
            tkey = _thread_key(name, q)
            if tkey in resolved:
                continue
            project_items.append({
                'key': key, 'type': 'Open Question', 'text': q,
                'project': name, 'project_idx': i,
                'tag_class': 'tag-question', 'priority': 2,
            })

        # Not Yet Built
        for nw in p.get('not_working', []):
            key = _item_key(name, 'Not Yet Built', nw)
            project_items.append({
                'key': key, 'type': 'Not Yet Built', 'text': nw,
                'project': name, 'project_idx': i,
                'tag_class': 'tag-notbuilt', 'priority': 3,
            })

        # Sort by priority (blockers first, then next steps, questions, not built)
        project_items.sort(key=lambda x: x['priority'])

        for item in project_items:
            action = item_actions.get(item['key'])
            if action and action.get('action') == 'ignored':
                ignored_items.append(item)
            elif action and action.get('action') == 'reassigned':
                item['reassigned_to'] = action.get('target_project', '')
                flagged_items.append(item)
            else:
                next_items.append(item)

    # Group next_items by project
    from collections import OrderedDict
    by_project = OrderedDict()
    for item in next_items:
        proj = item['project']
        if proj not in by_project:
            # Find the project data
            pidx = item['project_idx']
            p = projects[pidx]
            by_project[proj] = {
                'items': [],
                'idx': pidx,
                'category': p.get('category_group', ''),
                'progress': p.get('progress', 0),
                'status': p.get('status', ''),
            }
        by_project[proj]['items'].append(item)

    # Build HTML
    content = ''

    # Verify all categories button
    if has_ai:
        content += '<div style="margin-bottom:16px; text-align:right;"><button class="btn-sm btn-verify" onclick="verifyAllCategories(this)" style="padding:6px 14px; font-size:11px;">Verify All Categories with AI</button></div>'

    # Active items grouped by project
    active_count = len(next_items)
    content += f'<div class="section-header">Action Items <span class="badge">{active_count}</span></div>'

    if by_project:
        for proj_name, proj_data in by_project.items():
            progress = proj_data['progress']
            color = '#2ECC71' if progress > 75 else '#3498DB' if progress >= 50 else '#F1C40F' if progress >= 25 else '#E74C3C'
            cat = proj_data['category']

            content += f'''<div class="list-card" style="margin-bottom:14px;">
                <div class="list-item" style="background:var(--stat-bg); padding:10px 18px;">
                    <div class="main">
                        <div class="title" style="font-size:14px;">
                            <a href="/project/{proj_data['idx']}" style="color:inherit; text-decoration:none;">{proj_name}</a>
                            <div class="progress-bar"><div class="progress-fill" style="width:{progress}%; background:{color};"></div></div>
                            <span id="cat-flag-{proj_data['idx']}"></span>
                        </div>
                        <div class="subtitle">{cat} &middot; {proj_data['status']}</div>
                    </div>
                </div>'''

            for item in proj_data['items']:
                dropdown_counter += 1
                dd_id = f'dd-{dropdown_counter}'
                safe_key = item['key'].replace("'", "&#39;").replace('"', '&quot;')
                safe_text = item['text'].replace("'", "&#39;").replace('"', '&quot;')

                content += f'''<div class="list-item">
                    <div class="main">
                        <div class="title"><span class="tag {item['tag_class']}">{item['type']}</span> {item['text']}</div>
                    </div>
                    <div class="actions">
                        <button class="btn-sm btn-resolve" onclick="apiAction('/api/resolve-thread', {{project:'{item['project'].replace(chr(39), "&#39;")}', text:'{safe_text[:100]}'}}, this)">Resolve</button>
                        <button class="btn-sm btn-ignore" onclick="apiAction('/api/item-action', {{key:'{safe_key}', action:'ignored'}}, this)">Ignore</button>
                        <button class="btn-sm btn-reassign" onclick="toggleDropdown('{dd_id}')">Reassign</button>
                        <div class="reassign-dropdown" id="{dd_id}">'''

                for pn in project_names:
                    if pn != item['project']:
                        safe_pn = pn.replace("'", "&#39;")
                        content += f'<a href="#" onclick="event.preventDefault(); reassignItem(\'{safe_key}\', \'{safe_pn}\')">{pn}</a>'

                content += '</div></div></div>'

            content += '</div>'
    else:
        content += '<div class="empty">No action items across any project</div>'

    # Reassigned items
    if flagged_items:
        content += f'<div class="section-header">Reassigned <span class="badge">{len(flagged_items)}</span></div>'
        content += '<div class="list-card">'
        for item in flagged_items:
            safe_key = item['key'].replace("'", "&#39;").replace('"', '&quot;')
            content += f'''<div class="list-item item-reassigned">
                <div class="main">
                    <div class="title"><span class="tag {item['tag_class']}">{item['type']}</span> {item['text']}</div>
                    <div class="subtitle">From <strong>{item['project']}</strong> &rarr; <strong>{item.get('reassigned_to', '?')}</strong></div>
                </div>
                <div class="actions">
                    <button class="btn-sm btn-undo" onclick="apiAction('/api/item-action', {{key:'{safe_key}', action:'undo'}}, this)">Undo</button>
                </div>
            </div>'''
        content += '</div>'

    # Ignored items (collapsed by default)
    if ignored_items:
        content += f'<div class="section-header">Ignored <span class="badge">{len(ignored_items)}</span></div>'
        content += '<div class="list-card">'
        for item in ignored_items:
            safe_key = item['key'].replace("'", "&#39;").replace('"', '&quot;')
            content += f'''<div class="list-item item-ignored">
                <div class="main">
                    <div class="title"><span class="tag {item['tag_class']}">{item['type']}</span> {item['text']}</div>
                    <div class="subtitle">{item['project']}</div>
                </div>
                <div class="actions">
                    <button class="btn-sm btn-undo" onclick="apiAction('/api/item-action', {{key:'{safe_key}', action:'undo'}}, this)">Restore</button>
                </div>
            </div>'''
        content += '</div>'

    # Add verify script
    content += '''
    <script>
    function verifyAllCategories(btn) {
        btn.disabled = true;
        btn.textContent = 'Verifying...';
        fetch('/api/verify-categories', { method: 'POST' })
        .then(r => r.json())
        .then(function(data) {
            btn.textContent = 'Done';
            if (data.results) {
                data.results.forEach(function(r) {
                    var el = document.getElementById('cat-flag-' + r.idx);
                    if (el) {
                        if (r.confidence === 'low') {
                            el.innerHTML = '<span class="flag flag-low">AI: should be ' + r.suggested + '</span>';
                        } else {
                            el.innerHTML = '<span class="flag flag-ok">OK</span>';
                        }
                    }
                });
            } else if (data.error) {
                btn.textContent = data.error;
            }
        });
    }
    </script>'''

    return render_template_string(LIST_VIEW_HTML, title=f"What's Next ({active_count} items)", content=content)


@app.route('/api/item-action', methods=['POST'])
def api_item_action():
    """Ignore, reassign, or undo an action on a what's-next item."""
    data = request.get_json(force=True)
    key = data.get('key', '')
    action = data.get('action', '')

    if not key:
        return jsonify({'error': 'Missing key'}), 400

    actions = _load_item_actions()

    if action == 'undo':
        actions.pop(key, None)
    elif action == 'ignored':
        actions[key] = {'action': 'ignored'}
    elif action == 'reassigned':
        target = data.get('target_project', '')
        actions[key] = {'action': 'reassigned', 'target_project': target}
    else:
        return jsonify({'error': 'Unknown action'}), 400

    _save_item_actions(actions)
    return jsonify({'ok': True})


@app.route('/api/verify-categories', methods=['POST'])
def api_verify_categories():
    """Use AI to verify each project is in the right category."""
    projects = _get_projects()
    ignored = _load_ignored()
    archived = _load_archived()

    active = [(i, p) for i, p in enumerate(projects)
              if p.get('name', '') not in ignored and p.get('name', '') not in archived]

    if not active:
        return jsonify({'results': []})

    # Build a single prompt with all projects for efficiency
    lines = []
    for i, p in active:
        name = p.get('name', '')
        cat = p.get('category_group', 'Uncategorized')
        features = ', '.join(p.get('features', [])[:5]) or 'none listed'
        summary = p.get('summary', '')[:150] or 'no description'
        lines.append(f"- [{i}] \"{name}\" -> current: {cat} | features: {features} | summary: {summary}")

    project_list = '\n'.join(lines)

    prompt = f"""Review these project categorizations. Valid categories: Church, School, Product, Infrastructure, Personal, Research.

For each project, respond with one line in this exact format:
[idx] OK
or
[idx] LOW suggested_category

Only output LOW if the project clearly belongs in a different category. Be conservative — if unsure, say OK.

Projects:
{project_list}"""

    result = _call_ai(prompt, max_tokens=500)
    if not result:
        return jsonify({'error': 'AI not configured or call failed'})

    # Parse response
    results = []
    for line in result.strip().split('\n'):
        line = line.strip()
        if not line or not line.startswith('['):
            continue
        try:
            idx_str = line[1:line.index(']')]
            idx = int(idx_str)
            rest = line[line.index(']')+1:].strip()
            if rest.startswith('OK'):
                results.append({'idx': idx, 'confidence': 'ok', 'suggested': ''})
            elif rest.startswith('LOW'):
                suggested = rest[3:].strip()
                results.append({'idx': idx, 'confidence': 'low', 'suggested': suggested})
        except (ValueError, IndexError):
            continue

    return jsonify({'results': results})


INITIATIVE_FILE = os.path.expanduser('~/.claudesync_initiatives.json')


def _load_initiatives():
    if os.path.exists(INITIATIVE_FILE):
        try:
            with open(INITIATIVE_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_initiatives(data):
    with open(INITIATIVE_FILE, 'w') as f:
        json.dump(data, f, indent=2)


@app.route('/api/classify-unmatched', methods=['POST'])
def api_classify_unmatched():
    """Use AI to classify unmatched chat conversations into initiatives."""
    chat_stats = getattr(load_projects, '_last_chat_stats', {})
    unmatched = chat_stats.get('unmatched_chats', [])

    if not unmatched:
        return jsonify({'error': 'No unmatched conversations found. Upload chat history first.'})

    projects = _get_projects()
    project_names = [p.get('name', '') for p in projects if p.get('name')]

    # Process in batches of 15 for token efficiency
    all_results = []
    batch_size = 15
    for batch_start in range(0, len(unmatched), batch_size):
        batch = unmatched[batch_start:batch_start + batch_size]

        _bg_progress('ai_classify', f'Classifying batch {batch_start // batch_size + 1}...')

        lines = []
        for i, chat in enumerate(batch):
            idx = batch_start + i
            excerpt = chat['excerpt'][:200].replace('\n', ' ')
            lines.append(f"[{idx}] file: {chat['filename']} | date: {chat['date']} | excerpt: {excerpt}")

        chat_list = '\n'.join(lines)

        prompt = f"""These chat conversations were not automatically matched to any existing project initiative.

Existing initiatives: {', '.join(project_names)}

For each conversation below, determine:
1. If it clearly belongs to an existing initiative, output: [idx] MATCH initiative_name
2. If it doesn't match any existing initiative, suggest a new initiative name: [idx] NEW suggested_initiative_name
3. If it's too vague or is just small talk/greetings: [idx] SKIP

Rules:
- Initiative names should be descriptive (2-5 words), like "Parish Database Migration" or "School Grade Calculator"
- Group related conversations under the same new initiative name
- Be specific, not generic. "Code Review" is too vague. "React Dashboard Refactor" is better.

Conversations:
{chat_list}"""

        result = _call_ai(prompt, max_tokens=800)
        if not result:
            return jsonify({'error': 'AI not configured or call failed'})

        for line in result.strip().split('\n'):
            line = line.strip()
            if not line or not line.startswith('['):
                continue
            try:
                idx_str = line[1:line.index(']')]
                idx = int(idx_str)
                rest = line[line.index(']') + 1:].strip()
                if idx < 0 or idx >= len(unmatched):
                    continue

                chat_info = unmatched[idx]
                entry = {
                    'idx': idx,
                    'filename': chat_info['filename'],
                    'date': chat_info['date'],
                    'excerpt': chat_info['excerpt'][:150],
                }

                if rest.startswith('MATCH'):
                    initiative = rest[5:].strip()
                    entry['action'] = 'match'
                    entry['initiative'] = initiative
                elif rest.startswith('NEW'):
                    initiative = rest[3:].strip()
                    entry['action'] = 'new'
                    entry['initiative'] = initiative
                elif rest.startswith('SKIP'):
                    entry['action'] = 'skip'
                    entry['initiative'] = ''
                else:
                    continue

                all_results.append(entry)
            except (ValueError, IndexError):
                continue

    # Save results for the UI
    initiatives = _load_initiatives()
    initiatives['last_classified'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    initiatives['results'] = all_results
    initiatives['total_unmatched'] = len(unmatched)
    _save_initiatives(initiatives)

    return jsonify({
        'ok': True,
        'total': len(unmatched),
        'classified': len(all_results),
        'results': all_results,
    })


@app.route('/view/unmatched')
def view_unmatched():
    """Show unmatched chat conversations and AI classification results."""
    chat_stats = getattr(load_projects, '_last_chat_stats', {})
    unmatched = chat_stats.get('unmatched_chats', [])
    initiatives = _load_initiatives()
    ai_results = initiatives.get('results', [])
    ai_config = _load_ai_config()
    has_ai = bool(ai_config.get('api_key'))

    # Build lookup from AI results
    classified = {}
    for r in ai_results:
        classified[r.get('idx', -1)] = r

    # Group by suggested initiative
    by_initiative = defaultdict(list)
    unclassified = []
    skipped = []
    matched_to_existing = []

    for i, chat in enumerate(unmatched):
        c = classified.get(i)
        if c:
            if c['action'] == 'match':
                matched_to_existing.append({**chat, 'initiative': c['initiative'], 'idx': i})
            elif c['action'] == 'new':
                by_initiative[c['initiative']].append({**chat, 'idx': i})
            elif c['action'] == 'skip':
                skipped.append({**chat, 'idx': i})
        else:
            unclassified.append({**chat, 'idx': i})

    content = ''

    # Stats bar
    total = len(unmatched)
    classified_count = len(ai_results)
    new_initiatives = len(by_initiative)
    content += f'''<div style="display:flex; gap:16px; margin-bottom:20px; flex-wrap:wrap;">
        <div style="background:var(--stat-bg); padding:12px 20px; border-radius:8px; flex:1; min-width:120px; text-align:center;">
            <div style="font-size:24px; font-weight:700; color:var(--heading);">{total}</div>
            <div style="font-size:11px; color:var(--text-muted);">Unmatched Conversations</div>
        </div>
        <div style="background:var(--stat-bg); padding:12px 20px; border-radius:8px; flex:1; min-width:120px; text-align:center;">
            <div style="font-size:24px; font-weight:700; color:var(--heading);">{new_initiatives}</div>
            <div style="font-size:11px; color:var(--text-muted);">New Initiatives Suggested</div>
        </div>
        <div style="background:var(--stat-bg); padding:12px 20px; border-radius:8px; flex:1; min-width:120px; text-align:center;">
            <div style="font-size:24px; font-weight:700; color:var(--heading);">{len(matched_to_existing)}</div>
            <div style="font-size:11px; color:var(--text-muted);">Matched to Existing</div>
        </div>
        <div style="background:var(--stat-bg); padding:12px 20px; border-radius:8px; flex:1; min-width:120px; text-align:center;">
            <div style="font-size:24px; font-weight:700; color:var(--heading);">{len(skipped)}</div>
            <div style="font-size:11px; color:var(--text-muted);">Skipped (small talk)</div>
        </div>
    </div>'''

    # Classify button
    if has_ai and total > 0:
        if classified_count == 0:
            content += '<div style="margin-bottom:16px;"><button class="btn-sm btn-verify" onclick="classifyUnmatched(this)" style="padding:8px 18px; font-size:12px;">Classify with AI</button></div>'
        else:
            content += f'<div style="margin-bottom:16px; font-size:11px; color:var(--text-muted);">Last classified: {initiatives.get("last_classified", "never")} &mdash; <button class="btn-sm btn-verify" onclick="classifyUnmatched(this)" style="padding:4px 10px; font-size:10px;">Re-classify</button></div>'
    elif total == 0:
        content += '<div class="empty">No unmatched conversations. Upload chat history first, or all conversations were matched to projects.</div>'
    elif not has_ai:
        content += '<div style="margin-bottom:16px; font-size:12px; color:var(--text-muted);">Configure an API key in AI Settings to classify these conversations.</div>'

    # New initiatives suggested by AI
    if by_initiative:
        content += f'<div class="section-header">Suggested New Initiatives <span class="badge">{new_initiatives}</span></div>'
        for init_name, chats in sorted(by_initiative.items()):
            content += f'''<div class="list-card" style="margin-bottom:12px;">
                <div class="list-item" style="background:var(--stat-bg); padding:10px 18px;">
                    <div class="main">
                        <div class="title" style="font-size:14px; color:#e67e22;">{init_name}</div>
                        <div class="subtitle">{len(chats)} conversation{"s" if len(chats) != 1 else ""}</div>
                    </div>
                </div>'''
            for chat in chats[:10]:  # Show first 10
                content += f'''<div class="list-item">
                    <div class="main">
                        <div class="title" style="font-size:12px;">{chat["filename"]}</div>
                        <div class="subtitle">{chat["date"]}</div>
                        <div class="detail">{chat.get("excerpt", "")[:120]}</div>
                    </div>
                </div>'''
            if len(chats) > 10:
                content += f'<div class="list-item"><div class="main"><div class="subtitle">...and {len(chats) - 10} more</div></div></div>'
            content += '</div>'

    # Matched to existing projects
    if matched_to_existing:
        content += f'<div class="section-header">Matched to Existing Initiatives <span class="badge">{len(matched_to_existing)}</span></div>'
        # Group by initiative
        by_existing = defaultdict(list)
        for item in matched_to_existing:
            by_existing[item['initiative']].append(item)
        content += '<div class="list-card">'
        for init_name, items in sorted(by_existing.items()):
            content += f'''<div class="list-item" style="background:var(--stat-bg);">
                <div class="main">
                    <div class="title" style="font-size:13px;">{init_name}</div>
                    <div class="subtitle">{len(items)} conversation{"s" if len(items) != 1 else ""}</div>
                </div>
            </div>'''
        content += '</div>'

    # Unclassified (not yet sent to AI)
    if unclassified:
        content += f'<div class="section-header">Not Yet Classified <span class="badge">{len(unclassified)}</span></div>'
        content += '<div class="list-card">'
        for chat in unclassified[:20]:
            content += f'''<div class="list-item">
                <div class="main">
                    <div class="title" style="font-size:12px;">{chat["filename"]}</div>
                    <div class="subtitle">{chat["date"]}</div>
                    <div class="detail">{chat.get("excerpt", "")[:120]}</div>
                </div>
            </div>'''
        if len(unclassified) > 20:
            content += f'<div class="list-item"><div class="main"><div class="subtitle">...and {len(unclassified) - 20} more</div></div></div>'
        content += '</div>'

    # Skipped
    if skipped:
        content += f'<div class="section-header">Skipped (Small Talk / Greetings) <span class="badge">{len(skipped)}</span></div>'
        content += '<div class="list-card">'
        for chat in skipped[:10]:
            content += f'''<div class="list-item item-ignored">
                <div class="main">
                    <div class="title" style="font-size:12px;">{chat["filename"]}</div>
                    <div class="subtitle">{chat["date"]}</div>
                </div>
            </div>'''
        if len(skipped) > 10:
            content += f'<div class="list-item"><div class="main"><div class="subtitle">...and {len(skipped) - 10} more</div></div></div>'
        content += '</div>'

    # JS for classify button
    content += '''
    <script>
    function classifyUnmatched(btn) {
        btn.disabled = true;
        btn.textContent = 'Classifying...';
        fetch('/api/classify-unmatched', { method: 'POST' })
        .then(r => r.json())
        .then(function(data) {
            if (data.error) {
                btn.textContent = data.error;
            } else {
                location.reload();
            }
        })
        .catch(function() { btn.textContent = 'Failed'; });
    }
    </script>'''

    return render_template_string(LIST_VIEW_HTML,
                                  title=f'Unmatched Conversations ({total})',
                                  content=content)


if __name__ == '__main__':
    print("\n" + "="*60)
    print("  Project Portfolio Dashboard")
    print("  Open http://localhost:5111 in your browser")
    print("  Press Ctrl+C to stop")
    print("="*60 + "\n")

    # Kick off initial project load in background so server starts immediately
    print("Loading projects in background...")
    t = threading.Thread(
        target=_bg_run_load,
        args=('~', None, False),
        daemon=True,
    )
    t.start()

    app.run(host='127.0.0.1', port=5111, debug=False)
