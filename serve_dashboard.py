#!/usr/bin/env python3
"""
Claude Project Sync - Web Dashboard

Serves an interactive HTML dashboard on localhost.
Reuses project scanning from generate_status_pdf.py.

Usage:
    python3 serve_dashboard.py              # http://localhost:8050
    python3 serve_dashboard.py --port 9000  # http://localhost:9000
"""

import argparse
import json
import os
import re
import subprocess
import sys
import webbrowser
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

# ---------------------------------------------------------------------------
# Project scanning (same logic as generate_status_pdf.py, kept self-contained
# so this script has zero local imports)
# ---------------------------------------------------------------------------

DEFAULT_SCAN_PATHS = [os.path.expanduser('~')]

SKIP_DIRS = {
    'node_modules', '.git', '__pycache__', 'venv', '.venv',
    'dist', 'build', '.next', 'coverage', 'Library', '.Trash',
    'Applications', 'Pictures', 'Music', 'Movies', 'Documents'
}

CONFIG_PATH = os.path.expanduser('~/.claudesync/config.json')

DEV_STATES = {
    'test':     {'label': 'Test',     'description': 'Push with no evidence of testing',               'color': '#E67E22'},
    'refine':   {'label': 'Refine',   'description': 'Chat abandoned — user satisfied or riffing',     'color': '#3498DB'},
    'continue': {'label': 'Continue', 'description': 'Tests ongoing, not fully resolved',              'color': '#E74C3C'},
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, 'w') as f:
        json.dump(cfg, f, indent=2)


def load_custom_states():
    cfg = load_config()
    merged = dict(DEV_STATES)
    merged.update(cfg.get('custom_dev_states', {}))
    return merged


def find_project_status_files(scan_paths=None, max_depth=2):
    if scan_paths is None:
        scan_paths = DEFAULT_SCAN_PATHS
    files = []
    for base in scan_paths:
        base = os.path.expanduser(base)
        if not os.path.isdir(base):
            continue
        for root, dirs, fnames in os.walk(base):
            depth = root.replace(base, '').count(os.sep)
            if depth >= max_depth:
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            if 'PROJECT_STATUS.md' in fnames:
                files.append(os.path.join(root, 'PROJECT_STATUS.md'))
    return files


def get_recent_commits(project_dir, max_commits=5):
    skip = ['add files via upload','initial commit','first commit','init commit',
            'create readme','update readme','delete ','remove ','merge branch',
            'merge pull request','wip','fix typo','minor fix','small fix','quick fix',
            'bump version','update dependencies','update package','lint fix',
            'format code','cleanup','refactor']
    try:
        r = subprocess.run(['git','log','--all','--pretty=format:%s'],
                           cwd=project_dir, capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            commits = []
            for line in r.stdout.strip().split('\n'):
                line = line.strip()
                if not line or len(line) < 15:
                    continue
                if any(p in line.lower() for p in skip):
                    continue
                commits.append(line)
                if len(commits) >= max_commits:
                    break
            return commits
    except Exception:
        pass
    return []


def parse_project_status(file_path):
    try:
        with open(file_path) as f:
            content = f.read()
        project = {'file_path': file_path, 'project_path': os.path.dirname(file_path)}

        m = re.search(r'# PROJECT_STATUS:\s*(.+)', content)
        project['name'] = m.group(1).strip() if m else os.path.basename(os.path.dirname(file_path))

        patterns = {
            'repo':      r'\*\*Repository\*\*\s*\|\s*(.+)',
            'category':  r'\*\*Category\*\*\s*\|\s*(.+)',
            'progress':  r'\*\*Progress\*\*\s*\|\s*(\d+)',
            'status':    r'\*\*Status\*\*\s*\|\s*(.+)',
            'has_repo':  r'\*\*Has GitHub Repo\*\*\s*\|\s*(.+)',
            'dev_state': r'\*\*Dev State\*\*\s*\|\s*(.+)',
        }
        for key, pat in patterns.items():
            m = re.search(pat, content)
            if m:
                v = m.group(1).strip()
                project[key] = int(v) if key == 'progress' else v

        project.setdefault('progress', 0)
        project.setdefault('status', 'Unknown')
        project.setdefault('category', 'Personal')
        project.setdefault('repo', '')
        project.setdefault('has_repo', 'No')
        project.setdefault('dev_state', '')

        hr = project['has_repo'].lower()
        project['has_github_repo'] = hr == 'yes' or (project['repo'] and 'not' not in project['repo'].lower())
        project['recent_commits'] = get_recent_commits(project['project_path'], 5)
        project['_raw_content'] = content
        return project
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return None


def load_projects(scan_paths=None):
    with_repos, without_repos = [], []
    for sf in find_project_status_files(scan_paths):
        p = parse_project_status(sf)
        if p:
            (with_repos if p['has_github_repo'] else without_repos).append(p)
    with_repos.sort(key=lambda x: x['progress'], reverse=True)
    without_repos.sort(key=lambda x: x['progress'], reverse=True)
    return {'with_repos': with_repos, 'without_repos': without_repos}


# ---------------------------------------------------------------------------
# AI assessment (optional, requires API key)
# ---------------------------------------------------------------------------

def assess_dev_state(project, api_key):
    try:
        import urllib.request
        all_states = load_custom_states()
        log_match = re.search(r'## Progress Log\s*\n(.*)', project.get('_raw_content', ''), re.DOTALL)
        progress_log = log_match.group(1)[:2000] if log_match else ''
        state_desc = '\n'.join(f'- "{k}": {s["description"]}' for k, s in all_states.items())

        prompt = f"""Analyze this project and determine its development state.

Project: {project['name']}
Progress: {project.get('progress',0)}%
Status: {project.get('status','Unknown')}
Recent commits: {json.dumps(project.get('recent_commits',[])[:5])}

Progress log (excerpt):
{progress_log[:1500]}

Available states:
{state_desc}

Respond with ONLY the state key. Nothing else."""

        body = json.dumps({
            'model': 'claude-sonnet-4-20250514',
            'max_tokens': 20,
            'messages': [{'role': 'user', 'content': prompt}]
        }).encode()
        req = urllib.request.Request('https://api.anthropic.com/v1/messages', data=body,
            headers={'Content-Type':'application/json','x-api-key':api_key,'anthropic-version':'2023-06-01'}, method='POST')
        with urllib.request.urlopen(req, timeout=30) as resp:
            answer = json.loads(resp.read())['content'][0]['text'].strip().lower().strip('"\'')
            if answer in all_states:
                return answer
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# HTML Dashboard
# ---------------------------------------------------------------------------

def build_html(projects):
    all_p = projects['with_repos'] + projects['without_repos']
    all_states = load_custom_states()
    now = datetime.now().strftime('%B %d, %Y at %I:%M %p')
    total = len(all_p)

    # Build chart data
    sorted_p = sorted(all_p, key=lambda x: x['progress'], reverse=True)
    chart_names = json.dumps([p['name'] for p in sorted_p])
    chart_progress = json.dumps([p['progress'] for p in sorted_p])
    chart_colors = json.dumps([
        '#2ECC71' if p['progress'] > 75 else '#3498DB' if p['progress'] >= 50
        else '#F1C40F' if p['progress'] >= 25 else '#E74C3C' for p in sorted_p
    ])

    # Category counts
    cats = {}
    for p in all_p:
        c = p.get('category', 'Personal')
        cats[c] = cats.get(c, 0) + 1
    cat_names = json.dumps(list(cats.keys()))
    cat_counts = json.dumps(list(cats.values()))
    cat_color_map = {'Infrastructure':'#3498DB','School':'#2ECC71','Church':'#9B59B6',
                     'Product':'#E67E22','Research':'#1ABC9C','Personal':'#95A5A6'}
    cat_colors = json.dumps([cat_color_map.get(c, '#7F8C8D') for c in cats.keys()])

    # Project cards
    cards_html = ''
    for p in sorted_p:
        progress = p.get('progress', 0)
        pc = '#2ECC71' if progress > 75 else '#3498DB' if progress >= 50 else '#F1C40F' if progress >= 25 else '#E74C3C'
        ds = p.get('dev_state', '')
        state_badge = ''
        if ds and ds in all_states:
            si = all_states[ds]
            state_badge = f'<span class="state-badge" style="background:{si["color"]}20;color:{si["color"]};border:1px solid {si["color"]}">{si["label"]}</span>'

        commits_html = ''
        for c in p.get('recent_commits', [])[:5]:
            display = (c[:60] + '...') if len(c) > 60 else c
            commits_html += f'<div class="commit">&rsaquo; {display}</div>'
        if not commits_html:
            commits_html = '<div class="no-data">No recent work logged</div>'

        repo_link = ''
        if p.get('repo') and 'not' not in p.get('repo', '').lower():
            repo_link = f'<a href="https://github.com/{p["repo"]}" target="_blank" class="repo-link">{p["repo"]}</a>'

        cards_html += f'''
        <div class="card">
            <div class="card-header">
                <div class="card-title">{p['name']}</div>
                <div class="card-meta">
                    <span class="progress-badge" style="background:{pc}20;color:{pc}">{progress}%</span>
                    <span class="status-text">{p.get('status','')}</span>
                    {state_badge}
                </div>
                {repo_link}
            </div>
            <div class="progress-bar-container">
                <div class="progress-bar" style="width:{progress}%;background:{pc}"></div>
            </div>
            <div class="commits">{commits_html}</div>
        </div>'''

    # State legend
    legend_items = ''
    for key, si in all_states.items():
        legend_items += f'<span class="legend-item"><span class="legend-dot" style="background:{si["color"]}"></span>{si["label"]}: {si["description"]}</span>'

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claude Project Sync Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
         background:#f0f2f5; color:#2C3E50; }}
  .header {{ background:linear-gradient(135deg,#2C3E50,#34495E); color:white;
             padding:24px 32px; display:flex; justify-content:space-between; align-items:center; }}
  .header h1 {{ font-size:24px; font-weight:600; }}
  .header .meta {{ font-size:13px; opacity:0.8; text-align:right; }}
  .container {{ max-width:1200px; margin:0 auto; padding:24px; }}
  .charts {{ display:grid; grid-template-columns:2fr 1fr; gap:20px; margin-bottom:24px; }}
  .chart-box {{ background:white; border-radius:12px; padding:20px; box-shadow:0 1px 3px rgba(0,0,0,0.1); }}
  .chart-box h3 {{ font-size:14px; color:#7F8C8D; margin-bottom:12px; text-transform:uppercase; letter-spacing:0.5px; }}
  .legend {{ background:white; border-radius:12px; padding:16px 20px; margin-bottom:24px;
             box-shadow:0 1px 3px rgba(0,0,0,0.1); display:flex; flex-wrap:wrap; gap:16px; align-items:center; }}
  .legend-title {{ font-size:12px; color:#7F8C8D; text-transform:uppercase; font-weight:600; }}
  .legend-item {{ font-size:12px; color:#555; display:flex; align-items:center; gap:5px; }}
  .legend-dot {{ width:10px; height:10px; border-radius:50%; display:inline-block; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(360px, 1fr)); gap:16px; }}
  .card {{ background:white; border-radius:12px; padding:20px; box-shadow:0 1px 3px rgba(0,0,0,0.1);
           transition:transform 0.15s, box-shadow 0.15s; }}
  .card:hover {{ transform:translateY(-2px); box-shadow:0 4px 12px rgba(0,0,0,0.12); }}
  .card-header {{ margin-bottom:10px; }}
  .card-title {{ font-size:16px; font-weight:600; margin-bottom:6px; }}
  .card-meta {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; }}
  .progress-badge {{ font-size:12px; font-weight:600; padding:2px 8px; border-radius:12px; }}
  .status-text {{ font-size:12px; color:#7F8C8D; }}
  .state-badge {{ font-size:11px; font-weight:600; padding:2px 8px; border-radius:12px; }}
  .repo-link {{ font-size:12px; color:#3498DB; text-decoration:none; margin-top:4px; display:block; }}
  .repo-link:hover {{ text-decoration:underline; }}
  .progress-bar-container {{ height:6px; background:#ecf0f1; border-radius:3px; margin:10px 0; }}
  .progress-bar {{ height:100%; border-radius:3px; transition:width 0.5s; }}
  .commits {{ font-size:12px; color:#555; }}
  .commit {{ padding:3px 0; border-bottom:1px solid #f5f5f5; }}
  .commit:last-child {{ border-bottom:none; }}
  .no-data {{ color:#bbb; font-style:italic; padding:4px 0; }}
  .refresh-btn {{ background:rgba(255,255,255,0.15); border:1px solid rgba(255,255,255,0.3);
                  color:white; padding:8px 16px; border-radius:8px; cursor:pointer; font-size:13px; }}
  .refresh-btn:hover {{ background:rgba(255,255,255,0.25); }}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>Project Status Dashboard</h1>
    <div style="font-size:13px;opacity:0.7;margin-top:4px">{total} projects</div>
  </div>
  <div class="meta">
    <div>{now}</div>
    <button class="refresh-btn" onclick="location.reload()" style="margin-top:8px">Refresh</button>
  </div>
</div>
<div class="container">
  <div class="charts">
    <div class="chart-box">
      <h3>Project Progress</h3>
      <canvas id="progressChart"></canvas>
    </div>
    <div class="chart-box">
      <h3>By Category</h3>
      <canvas id="categoryChart"></canvas>
    </div>
  </div>
  <div class="legend">
    <span class="legend-title">Dev States:</span>
    {legend_items}
  </div>
  <div class="cards">
    {cards_html}
  </div>
  <div style="text-align:center;padding:24px;color:#95A5A6;font-size:13px">
    If this tool saves you time: Venmo @ctreada
  </div>
</div>
<script>
new Chart(document.getElementById('progressChart'), {{
  type: 'bar',
  data: {{
    labels: {chart_names},
    datasets: [{{ data: {chart_progress}, backgroundColor: {chart_colors}, borderRadius: 4 }}]
  }},
  options: {{
    indexAxis: 'y',
    plugins: {{ legend: {{ display: false }} }},
    scales: {{ x: {{ max: 100, ticks: {{ callback: v => v + '%' }} }} }},
    responsive: true,
    maintainAspectRatio: false
  }}
}});
new Chart(document.getElementById('categoryChart'), {{
  type: 'doughnut',
  data: {{
    labels: {cat_names},
    datasets: [{{ data: {cat_counts}, backgroundColor: {cat_colors} }}]
  }},
  options: {{ responsive: true, plugins: {{ legend: {{ position: 'bottom', labels: {{ font: {{ size: 11 }} }} }} }} }}
}});
// Auto-size the progress chart
document.getElementById('progressChart').parentElement.style.height = Math.max(300, {total} * 36) + 'px';
</script>
</body>
</html>'''


# ---------------------------------------------------------------------------
# HTTP Server
# ---------------------------------------------------------------------------

class DashboardHandler(BaseHTTPRequestHandler):
    projects = None
    api_key = None

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            html = build_html(self.projects)
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode())
        elif self.path == '/api/projects':
            all_p = self.projects['with_repos'] + self.projects['without_repos']
            safe = [{k: v for k, v in p.items() if not k.startswith('_')} for p in all_p]
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(safe, indent=2).encode())
        elif self.path == '/api/refresh':
            print("Refreshing project data...")
            DashboardHandler.projects = load_projects()
            if DashboardHandler.api_key:
                all_p = DashboardHandler.projects['with_repos'] + DashboardHandler.projects['without_repos']
                for p in all_p:
                    if not p.get('dev_state'):
                        state = assess_dev_state(p, DashboardHandler.api_key)
                        if state:
                            p['dev_state'] = state
            self.send_response(302)
            self.send_header('Location', '/')
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Quieter logging
        pass


def main():
    parser = argparse.ArgumentParser(description='Serve project dashboard on localhost')
    parser.add_argument('--port', '-p', type=int, default=8050)
    parser.add_argument('--no-ai', action='store_true', help='Skip AI state assessment')
    parser.add_argument('--no-open', action='store_true', help='Do not auto-open browser')
    args = parser.parse_args()

    print("Scanning for projects...")
    DashboardHandler.projects = load_projects()
    total = len(DashboardHandler.projects['with_repos']) + len(DashboardHandler.projects['without_repos'])
    print(f"Found {total} projects")

    # AI assessment
    if not args.no_ai:
        cfg = load_config()
        api_key = cfg.get('anthropic_api_key') or os.environ.get('ANTHROPIC_API_KEY')
        if api_key:
            DashboardHandler.api_key = api_key
            all_p = DashboardHandler.projects['with_repos'] + DashboardHandler.projects['without_repos']
            needs = [p for p in all_p if not p.get('dev_state')]
            if needs:
                print(f"Running AI state assessment on {len(needs)} projects...")
                for i, p in enumerate(needs, 1):
                    sys.stdout.write(f"\r  Assessing {i}/{len(needs)}: {p['name'][:40]}...")
                    sys.stdout.flush()
                    state = assess_dev_state(p, api_key)
                    if state:
                        p['dev_state'] = state
                print("\r  Done.                                        ")
        else:
            print("No API key found — skipping AI assessment")

    server = HTTPServer(('127.0.0.1', args.port), DashboardHandler)
    url = f'http://localhost:{args.port}'
    print(f"\nDashboard running at: {url}")
    print("Press Ctrl+C to stop\n")

    if not args.no_open:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == '__main__':
    main()
