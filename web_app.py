#!/usr/bin/env python3
"""
Claude Project Sync - Localhost Web Frontend

Simple web UI for generating the Project Portfolio PDF.
Runs on localhost only — nothing exposed to the internet.

Features:
- Drag-and-drop chat history zip upload
- Configure scan paths
- One-click PDF generation
- Download the generated PDF directly

Usage:
    python3 web_app.py
    # Then open http://localhost:5111 in your browser
"""

import os
import tempfile
from datetime import datetime

from flask import Flask, request, send_file, render_template_string, flash, redirect, url_for

from generate_status_pdf import load_projects, create_pdf

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Store uploaded chat history path between requests
UPLOAD_DIR = tempfile.mkdtemp(prefix='claudesync_')

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Project Portfolio Generator</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f6f8;
            color: #1a1a1a;
            min-height: 100vh;
        }
        .container {
            max-width: 720px;
            margin: 0 auto;
            padding: 40px 20px;
        }
        h1 {
            font-size: 24px;
            color: #2C3E50;
            margin-bottom: 4px;
        }
        .subtitle {
            font-size: 13px;
            color: #888;
            margin-bottom: 32px;
        }
        .card {
            background: white;
            border-radius: 10px;
            padding: 28px;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }
        .card h2 {
            font-size: 15px;
            color: #2C3E50;
            margin-bottom: 16px;
            font-weight: 600;
        }
        .drop-zone {
            border: 2px dashed #ccd;
            border-radius: 8px;
            padding: 32px;
            text-align: center;
            cursor: pointer;
            transition: all 0.2s;
            background: #fafbfc;
        }
        .drop-zone:hover, .drop-zone.dragover {
            border-color: #3498DB;
            background: #f0f7ff;
        }
        .drop-zone p {
            font-size: 14px;
            color: #666;
        }
        .drop-zone .icon {
            font-size: 32px;
            margin-bottom: 8px;
            display: block;
        }
        .drop-zone input[type="file"] {
            display: none;
        }
        .drop-zone .filename {
            margin-top: 8px;
            font-size: 13px;
            color: #2ECC71;
            font-weight: 600;
        }
        label {
            display: block;
            font-size: 13px;
            color: #555;
            margin-bottom: 6px;
            font-weight: 500;
        }
        input[type="text"] {
            width: 100%;
            padding: 10px 12px;
            border: 1px solid #ddd;
            border-radius: 6px;
            font-size: 14px;
            margin-bottom: 12px;
            transition: border-color 0.2s;
        }
        input[type="text"]:focus {
            outline: none;
            border-color: #3498DB;
        }
        .help-text {
            font-size: 11px;
            color: #999;
            margin-top: -8px;
            margin-bottom: 12px;
        }
        .btn {
            display: inline-block;
            padding: 12px 28px;
            background: #2C3E50;
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
            text-decoration: none;
        }
        .btn:hover { background: #34495E; }
        .btn-primary { background: #3498DB; }
        .btn-primary:hover { background: #2980B9; }
        .btn-success { background: #2ECC71; }
        .btn-success:hover { background: #27AE60; }
        .btn-row {
            display: flex;
            gap: 12px;
            margin-top: 20px;
        }
        .flash {
            padding: 12px 16px;
            border-radius: 6px;
            margin-bottom: 16px;
            font-size: 13px;
        }
        .flash-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .flash-error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .flash-info { background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }
        .stats {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            margin-top: 16px;
        }
        .stat-box {
            background: #f8f9fa;
            border-radius: 6px;
            padding: 14px;
            text-align: center;
        }
        .stat-box .number {
            font-size: 22px;
            font-weight: 700;
            color: #2C3E50;
        }
        .stat-box .label {
            font-size: 11px;
            color: #888;
            margin-top: 2px;
        }
        .result-card {
            border-left: 4px solid #2ECC71;
        }
        footer {
            text-align: center;
            font-size: 11px;
            color: #aaa;
            margin-top: 40px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Project Portfolio Generator</h1>
        <p class="subtitle">Bridges Claude Code and Claude.ai chat — generates your timestamped portfolio PDF</p>

        {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
            {% for category, message in messages %}
            <div class="flash flash-{{ category }}">{{ message }}</div>
            {% endfor %}
        {% endif %}
        {% endwith %}

        {% if result %}
        <div class="card result-card">
            <h2>PDF Generated Successfully</h2>
            <div class="stats">
                <div class="stat-box">
                    <div class="number">{{ result.total_projects }}</div>
                    <div class="label">Projects</div>
                </div>
                <div class="stat-box">
                    <div class="number">{{ result.total_timeline }}</div>
                    <div class="label">Timeline Entries</div>
                </div>
                <div class="stat-box">
                    <div class="number">{{ result.total_threads }}</div>
                    <div class="label">Open Threads</div>
                </div>
            </div>
            <div class="btn-row">
                <a href="/download" class="btn btn-success">Download PDF</a>
                <a href="/" class="btn">Generate Again</a>
            </div>
        </div>
        {% endif %}

        <form method="POST" action="/generate" enctype="multipart/form-data">
            <div class="card">
                <h2>1. Chat History (Optional)</h2>
                <p style="font-size:13px; color:#666; margin-bottom:14px;">
                    Upload your Claude.ai chat export to enrich project narratives with conversation context.
                </p>
                <div class="drop-zone" id="dropZone">
                    <span class="icon">&#128193;</span>
                    <p>Drag & drop a zip file here, or click to browse</p>
                    <p class="filename" id="fileName"></p>
                    <input type="file" name="chat_history" id="fileInput" accept=".zip,.tar,.gz,.md,.txt">
                </div>
            </div>

            <div class="card">
                <h2>2. Project Scan Paths</h2>
                <label for="scan_paths">Directories to scan for PROJECT_STATUS.md files</label>
                <input type="text" name="scan_paths" id="scan_paths"
                       value="{{ scan_paths or '~' }}"
                       placeholder="~/projects ~/work">
                <p class="help-text">Space-separated paths. Use ~ for home directory. Default scans ~/.</p>
            </div>

            <div class="btn-row">
                <button type="submit" class="btn btn-primary">Generate Portfolio PDF</button>
            </div>
        </form>

        <footer>
            claudesync2 — localhost only, nothing leaves this machine<br>
            If this tool saves you time: Venmo @ctreada
        </footer>
    </div>

    <script>
        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');
        const fileName = document.getElementById('fileName');

        dropZone.addEventListener('click', () => fileInput.click());

        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });

        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            if (e.dataTransfer.files.length) {
                fileInput.files = e.dataTransfer.files;
                fileName.textContent = e.dataTransfer.files[0].name;
            }
        });

        fileInput.addEventListener('change', () => {
            if (fileInput.files.length) {
                fileName.textContent = fileInput.files[0].name;
            }
        });
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, result=None, scan_paths='~')


@app.route('/generate', methods=['POST'])
def generate():
    # Handle chat history upload
    chat_history_path = None
    chat_file = request.files.get('chat_history')
    if chat_file and chat_file.filename:
        save_path = os.path.join(UPLOAD_DIR, chat_file.filename)
        chat_file.save(save_path)
        chat_history_path = save_path
        print(f"Chat history uploaded: {save_path}")

    # Parse scan paths
    scan_paths_str = request.form.get('scan_paths', '~').strip()
    if scan_paths_str:
        scan_paths = [os.path.expanduser(p.strip()) for p in scan_paths_str.split()]
    else:
        scan_paths = [os.path.expanduser('~')]

    # Load projects
    try:
        all_projects = load_projects(
            scan_paths=scan_paths,
            chat_history_path=chat_history_path,
            verbose=True
        )
    except Exception as e:
        flash(f'Error loading projects: {e}', 'error')
        return redirect(url_for('index'))

    if not all_projects:
        flash('No PROJECT_STATUS.md files found in the specified scan paths.', 'error')
        return redirect(url_for('index'))

    # Generate PDF
    today = datetime.now().strftime('%Y-%m-%d')
    output_path = os.path.join(UPLOAD_DIR, f'Project_Portfolio_Status_{today}.pdf')

    try:
        create_pdf(output_path, all_projects)
    except Exception as e:
        flash(f'Error generating PDF: {e}', 'error')
        return redirect(url_for('index'))

    # Compute stats
    total_projects = len(all_projects)
    total_timeline = sum(len(p.get('timeline', [])) for p in all_projects)
    total_threads = sum(len(p.get('open_threads', [])) for p in all_projects)

    # Store output path for download
    app.config['LAST_PDF'] = output_path

    result = {
        'total_projects': total_projects,
        'total_timeline': total_timeline,
        'total_threads': total_threads,
    }

    flash(f'PDF generated with {total_projects} projects!', 'success')
    return render_template_string(HTML_TEMPLATE, result=result,
                                  scan_paths=scan_paths_str)


@app.route('/download')
def download():
    pdf_path = app.config.get('LAST_PDF')
    if not pdf_path or not os.path.exists(pdf_path):
        flash('No PDF available. Generate one first.', 'error')
        return redirect(url_for('index'))

    return send_file(
        pdf_path,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=os.path.basename(pdf_path)
    )


if __name__ == '__main__':
    print("\n" + "="*60)
    print("  Project Portfolio Generator — Web UI")
    print("  Open http://localhost:5111 in your browser")
    print("  Press Ctrl+C to stop")
    print("="*60 + "\n")

    app.run(
        host='127.0.0.1',
        port=5111,
        debug=False,
    )
