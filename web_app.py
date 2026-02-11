#!/usr/bin/env python3
"""
Claude Project Sync - Dashboard & PDF Generator

Localhost-only web dashboard that visualizes project activity over time
and lets you drill down into individual project decision timelines.

Features:
- Activity chart (day/week/month) across all projects
- Project cards with progress, last active, open thread count
- Drill-down to full decision timeline per project
- Chat history zip upload
- One-click PDF generation + download

Usage:
    python3 web_app.py
    # Then open http://localhost:5111 in your browser
"""

import json
import os
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta

from flask import (Flask, request, send_file, render_template_string,
                   flash, redirect, url_for, jsonify)

from generate_status_pdf import load_projects, create_pdf

app = Flask(__name__)
app.secret_key = os.urandom(24)

UPLOAD_DIR = tempfile.mkdtemp(prefix='claudesync_')

# Cache loaded projects so dashboard + drill-down share data
_project_cache = {
    'projects': [],
    'scan_paths': '~',
    'chat_history_path': None,
}


def _load_cached_projects(scan_paths_str=None, chat_history_path=None):
    """Load projects, caching the result for the session."""
    if scan_paths_str:
        scan_paths = [os.path.expanduser(p.strip()) for p in scan_paths_str.split()]
    else:
        scan_paths_str = _project_cache.get('scan_paths', '~')
        scan_paths = [os.path.expanduser(p.strip()) for p in scan_paths_str.split()]

    chp = chat_history_path or _project_cache.get('chat_history_path')

    projects = load_projects(scan_paths=scan_paths, chat_history_path=chp, verbose=False)

    _project_cache['projects'] = projects
    _project_cache['scan_paths'] = scan_paths_str
    _project_cache['chat_history_path'] = chp

    return projects


def _aggregate_activity(projects, mode='day'):
    """Aggregate activity events across all projects into time buckets.

    mode: 'day', 'week', or 'month'
    Returns: {labels: [...], datasets: [{label, data, backgroundColor}]}
    """
    # Collect all events with dates and sources
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

            # Categorize source
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

    # Determine date range
    dates = [e['date'] for e in events]
    min_date = min(dates)
    max_date = max(dates)

    # Build time buckets
    buckets = defaultdict(lambda: defaultdict(int))

    for e in events:
        dt = e['date']
        if mode == 'day':
            key = dt.strftime('%Y-%m-%d')
        elif mode == 'week':
            # Monday of the week
            monday = dt - timedelta(days=dt.weekday())
            key = monday.strftime('%Y-%m-%d')
        elif mode == 'month':
            key = dt.strftime('%Y-%m')
        else:
            key = dt.strftime('%Y-%m-%d')

        buckets[key][e['category']] += 1

    # Sort labels chronologically
    labels = sorted(buckets.keys())

    # Format labels for display
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

    # Build datasets
    categories = ['Commits', 'Chat Activity', 'Progress Log']
    cat_colors = {
        'Commits': '#3498DB',
        'Chat Activity': '#9B59B6',
        'Progress Log': '#2ECC71',
    }

    datasets = []
    for cat in categories:
        data = [buckets[label].get(cat, 0) for label in labels]
        if sum(data) > 0:  # Only include categories that have data
            datasets.append({
                'label': cat,
                'data': data,
                'backgroundColor': cat_colors.get(cat, '#95A5A6'),
            })

    return {'labels': display_labels, 'datasets': datasets}


def _project_activity_breakdown(projects):
    """Per-project activity counts for the project cards."""
    breakdown = []
    for p in projects:
        timeline = p.get('timeline', [])
        commits = sum(1 for e in timeline if 'commit' in e.get('source', '').lower())
        chats = sum(1 for e in timeline if 'chat' in e.get('source', '').lower())
        logs = len(timeline) - commits - chats

        breakdown.append({
            'name': p.get('name', 'Unknown'),
            'progress': p.get('progress', 0),
            'status': p.get('status', ''),
            'category': p.get('category_group', ''),
            'last_worked': p.get('last_worked', ''),
            'total_events': len(timeline),
            'commits': commits,
            'chats': chats,
            'logs': logs,
            'open_threads': len(p.get('open_threads', [])),
            'blockers': sum(1 for t, _ in p.get('open_threads', []) if t == 'Blocker'),
        })

    return breakdown


# =============================================================================
# HTML TEMPLATES
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
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f6f8; color: #1a1a1a; }
        .top-bar { background: #2C3E50; color: white; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; }
        .top-bar h1 { font-size: 18px; font-weight: 600; }
        .top-bar .actions { display: flex; gap: 10px; align-items: center; }
        .top-bar .btn { padding: 8px 16px; border-radius: 5px; font-size: 12px; font-weight: 600; cursor: pointer; border: none; text-decoration: none; color: white; }
        .btn-upload { background: #3498DB; }
        .btn-upload:hover { background: #2980B9; }
        .btn-pdf { background: #2ECC71; }
        .btn-pdf:hover { background: #27AE60; }
        .container { max-width: 1100px; margin: 0 auto; padding: 24px 20px; }
        .stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 24px; }
        .stat-card { background: white; border-radius: 8px; padding: 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
        .stat-card .number { font-size: 28px; font-weight: 700; color: #2C3E50; }
        .stat-card .label { font-size: 11px; color: #888; margin-top: 2px; text-transform: uppercase; letter-spacing: 0.5px; }
        .chart-card { background: white; border-radius: 8px; padding: 20px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
        .chart-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
        .chart-header h2 { font-size: 15px; color: #2C3E50; }
        .toggle-group { display: flex; gap: 4px; }
        .toggle-btn { padding: 5px 14px; border: 1px solid #ddd; background: white; border-radius: 4px; font-size: 12px; cursor: pointer; color: #666; }
        .toggle-btn.active { background: #2C3E50; color: white; border-color: #2C3E50; }
        .projects-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
        .project-card { background: white; border-radius: 8px; padding: 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); cursor: pointer; transition: box-shadow 0.2s; text-decoration: none; color: inherit; display: block; }
        .project-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.12); }
        .project-card .name { font-size: 14px; font-weight: 600; color: #2C3E50; margin-bottom: 2px; }
        .project-card .meta { font-size: 11px; color: #888; margin-bottom: 10px; }
        .progress-bar { height: 6px; background: #eee; border-radius: 3px; overflow: hidden; margin-bottom: 10px; }
        .progress-fill { height: 100%; border-radius: 3px; transition: width 0.3s; }
        .project-card .counts { display: flex; gap: 12px; font-size: 11px; color: #666; }
        .project-card .counts span { display: flex; align-items: center; gap: 3px; }
        .dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
        .dot-commit { background: #3498DB; }
        .dot-chat { background: #9B59B6; }
        .dot-log { background: #2ECC71; }
        .dot-blocker { background: #E74C3C; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 600; }
        .badge-blocker { background: #fce4ec; color: #c62828; }
        footer { text-align: center; font-size: 11px; color: #aaa; margin-top: 40px; padding-bottom: 20px; }
        .flash { padding: 10px 16px; border-radius: 6px; margin-bottom: 16px; font-size: 13px; }
        .flash-success { background: #d4edda; color: #155724; }
        .flash-error { background: #f8d7da; color: #721c24; }
        /* Upload modal */
        .modal-overlay { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.4); z-index: 100; justify-content: center; align-items: center; }
        .modal-overlay.show { display: flex; }
        .modal { background: white; border-radius: 10px; padding: 28px; max-width: 500px; width: 90%; }
        .modal h2 { font-size: 16px; color: #2C3E50; margin-bottom: 16px; }
        .drop-zone { border: 2px dashed #ccd; border-radius: 8px; padding: 28px; text-align: center; cursor: pointer; transition: all 0.2s; background: #fafbfc; }
        .drop-zone:hover, .drop-zone.dragover { border-color: #3498DB; background: #f0f7ff; }
        .drop-zone p { font-size: 13px; color: #666; }
        .drop-zone input[type="file"] { display: none; }
        .drop-zone .filename { margin-top: 8px; font-size: 13px; color: #2ECC71; font-weight: 600; }
        .modal label { display: block; font-size: 13px; color: #555; margin: 14px 0 6px; font-weight: 500; }
        .modal input[type="text"] { width: 100%; padding: 9px 12px; border: 1px solid #ddd; border-radius: 5px; font-size: 13px; }
        .modal .btn-row { display: flex; gap: 10px; margin-top: 18px; }
        .modal .btn { padding: 10px 22px; font-size: 13px; }
        .btn-cancel { background: #eee; color: #555; }
        .btn-cancel:hover { background: #ddd; }
    </style>
</head>
<body>
    <div class="top-bar">
        <h1>Project Portfolio Dashboard</h1>
        <div class="actions">
            <button class="btn btn-upload" onclick="document.getElementById('uploadModal').classList.add('show')">Upload Chat History</button>
            <a href="/generate-pdf" class="btn btn-pdf">Generate PDF</a>
        </div>
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
            <div class="stat-card">
                <div class="number">{{ total_projects }}</div>
                <div class="label">Projects</div>
            </div>
            <div class="stat-card">
                <div class="number">{{ total_events }}</div>
                <div class="label">Total Events</div>
            </div>
            <div class="stat-card">
                <div class="number">{{ total_threads }}</div>
                <div class="label">Open Threads</div>
            </div>
            <div class="stat-card">
                <div class="number">{{ total_blockers }}</div>
                <div class="label">Blockers</div>
            </div>
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

        <!-- Project Cards -->
        <div class="projects-grid">
            {% for p in project_cards %}
            <a href="/project/{{ loop.index0 }}" class="project-card">
                <div class="name">{{ p.name }}</div>
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
            </a>
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
            <form method="POST" action="/upload" enctype="multipart/form-data">
                <div class="drop-zone" id="dropZone">
                    <p>Drag & drop a chat export zip, or click to browse</p>
                    <p class="filename" id="fileName"></p>
                    <input type="file" name="chat_history" id="fileInput" accept=".zip,.md,.txt">
                </div>
                <label for="scan_paths">Scan Paths</label>
                <input type="text" name="scan_paths" value="{{ scan_paths }}" placeholder="~ ~/projects">
                <div class="btn-row">
                    <button type="submit" class="btn btn-upload">Load & Refresh</button>
                    <button type="button" class="btn btn-cancel" onclick="document.getElementById('uploadModal').classList.remove('show')">Cancel</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        // Chart.js setup
        const chartData = {{ chart_data | tojson }};
        const ctx = document.getElementById('activityChart').getContext('2d');
        let chart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: chartData.labels,
                datasets: chartData.datasets
            },
            options: {
                responsive: true,
                plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } } },
                scales: {
                    x: { stacked: true, grid: { display: false }, ticks: { font: { size: 10 } } },
                    y: { stacked: true, beginAtZero: true, ticks: { stepSize: 1, font: { size: 10 } } }
                }
            }
        });

        function switchMode(mode, btn) {
            document.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            fetch('/api/chart-data?mode=' + mode)
                .then(r => r.json())
                .then(data => {
                    chart.data.labels = data.labels;
                    chart.data.datasets = data.datasets;
                    chart.update();
                });
        }

        // Drag and drop
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

PROJECT_DETAIL_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ project.name }} — Decision Timeline</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f6f8; color: #1a1a1a; }
        .top-bar { background: #2C3E50; color: white; padding: 16px 24px; display: flex; align-items: center; gap: 16px; }
        .top-bar a { color: #8cc4e8; text-decoration: none; font-size: 13px; }
        .top-bar a:hover { color: white; }
        .top-bar h1 { font-size: 18px; font-weight: 600; }
        .container { max-width: 800px; margin: 0 auto; padding: 24px 20px; }
        .header-card { background: white; border-radius: 8px; padding: 22px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
        .header-card .name { font-size: 20px; font-weight: 700; color: #2C3E50; }
        .header-card .meta { font-size: 12px; color: #888; margin-top: 4px; }
        .progress-bar { height: 8px; background: #eee; border-radius: 4px; overflow: hidden; margin: 12px 0; max-width: 300px; }
        .progress-fill { height: 100%; border-radius: 4px; }
        .summary { font-size: 13px; color: #444; line-height: 1.6; margin-top: 12px; }
        .section-title { font-size: 14px; font-weight: 600; color: #2C3E50; margin: 24px 0 12px; }
        .timeline { position: relative; padding-left: 24px; }
        .timeline::before { content: ''; position: absolute; left: 7px; top: 4px; bottom: 4px; width: 2px; background: #e0e0e0; }
        .timeline-entry { position: relative; margin-bottom: 16px; }
        .timeline-entry::before { content: ''; position: absolute; left: -20px; top: 6px; width: 10px; height: 10px; border-radius: 50%; border: 2px solid white; }
        .timeline-entry.commit::before { background: #3498DB; }
        .timeline-entry.chat::before { background: #9B59B6; }
        .timeline-entry.log::before { background: #2ECC71; }
        .timeline-entry .date { font-size: 11px; font-weight: 600; color: #888; }
        .timeline-entry .source { font-size: 10px; color: #aaa; margin-left: 4px; }
        .timeline-entry .text { font-size: 13px; color: #333; margin-top: 2px; line-height: 1.5; }
        .thread-list { list-style: none; }
        .thread-list li { padding: 8px 0; border-bottom: 1px solid #f0f0f0; font-size: 13px; color: #444; }
        .thread-list li:last-child { border-bottom: none; }
        .tag { display: inline-block; padding: 1px 7px; border-radius: 3px; font-size: 10px; font-weight: 600; margin-right: 6px; }
        .tag-blocker { background: #fce4ec; color: #c62828; }
        .tag-question { background: #fff3e0; color: #e65100; }
        .tag-next { background: #e3f2fd; color: #1565c0; }
        .tag-notbuilt { background: #f5f5f5; color: #616161; }
        .card { background: white; border-radius: 8px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
        footer { text-align: center; font-size: 11px; color: #aaa; margin-top: 40px; padding-bottom: 20px; }
    </style>
</head>
<body>
    <div class="top-bar">
        <a href="/">&larr; Dashboard</a>
        <h1>{{ project.name }}</h1>
    </div>
    <div class="container">
        <!-- Project Header -->
        <div class="header-card">
            <div class="name">{{ project.name }}</div>
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
            {% if project.narrative %}
            <div class="summary">{{ project.narrative }}</div>
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
                <p style="font-size:13px; color:#999; padding: 12px 0;">No timeline entries yet.</p>
                {% endif %}
            </div>
        </div>

        <!-- Open Threads -->
        {% if project.open_threads %}
        <div class="card">
            <div class="section-title">Open Threads ({{ project.open_threads | length }})</div>
            <ul class="thread-list">
                {% for thread_type, thread_text in project.open_threads %}
                <li>
                    {% if thread_type == 'Blocker' %}<span class="tag tag-blocker">Blocker</span>
                    {% elif thread_type == 'Open Question' %}<span class="tag tag-question">Question</span>
                    {% elif thread_type == 'Next Step' %}<span class="tag tag-next">Next</span>
                    {% else %}<span class="tag tag-notbuilt">{{ thread_type }}</span>{% endif %}
                    {{ thread_text }}
                </li>
                {% endfor %}
            </ul>
        </div>
        {% endif %}

        <footer>
            <a href="/" style="color:#888; text-decoration:none;">&larr; Back to Dashboard</a>
        </footer>
    </div>
</body>
</html>
"""


# =============================================================================
# ROUTES
# =============================================================================

@app.route('/')
def dashboard():
    projects = _project_cache.get('projects')
    if not projects:
        projects = _load_cached_projects()

    chart_data = _aggregate_activity(projects, mode='day')
    project_cards = _project_activity_breakdown(projects)

    total_events = sum(c['total_events'] for c in project_cards)
    total_threads = sum(c['open_threads'] for c in project_cards)
    total_blockers = sum(c['blockers'] for c in project_cards)

    return render_template_string(
        DASHBOARD_HTML,
        total_projects=len(projects),
        total_events=total_events,
        total_threads=total_threads,
        total_blockers=total_blockers,
        chart_data=chart_data,
        project_cards=project_cards,
        scan_paths=_project_cache.get('scan_paths', '~'),
    )


@app.route('/api/chart-data')
def api_chart_data():
    """API endpoint for chart mode switching (day/week/month)."""
    mode = request.args.get('mode', 'day')
    projects = _project_cache.get('projects', [])
    data = _aggregate_activity(projects, mode=mode)
    return jsonify(data)


@app.route('/project/<int:idx>')
def project_detail(idx):
    projects = _project_cache.get('projects', [])
    if idx < 0 or idx >= len(projects):
        flash('Project not found.', 'error')
        return redirect(url_for('dashboard'))

    project = projects[idx]
    return render_template_string(PROJECT_DETAIL_HTML, project=project)


@app.route('/upload', methods=['POST'])
def upload():
    """Handle chat history upload and refresh data."""
    chat_history_path = None
    chat_file = request.files.get('chat_history')
    if chat_file and chat_file.filename:
        save_path = os.path.join(UPLOAD_DIR, chat_file.filename)
        chat_file.save(save_path)
        chat_history_path = save_path
        print(f"Chat history uploaded: {save_path}")

    scan_paths_str = request.form.get('scan_paths', '~').strip() or '~'

    _load_cached_projects(scan_paths_str, chat_history_path)

    total = len(_project_cache['projects'])
    flash(f'Loaded {total} projects.' +
          (' Chat history integrated.' if chat_history_path else ''), 'success')
    return redirect(url_for('dashboard'))


@app.route('/generate-pdf')
def generate_pdf():
    """Generate and download the portfolio PDF."""
    projects = _project_cache.get('projects', [])
    if not projects:
        projects = _load_cached_projects()

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


if __name__ == '__main__':
    # Auto-load projects on startup
    print("Pre-loading projects...")
    _load_cached_projects()
    total = len(_project_cache['projects'])
    print(f"Loaded {total} projects")

    print("\n" + "="*60)
    print("  Project Portfolio Dashboard")
    print("  Open http://localhost:5111 in your browser")
    print("  Press Ctrl+C to stop")
    print("="*60 + "\n")

    app.run(host='127.0.0.1', port=5111, debug=False)
