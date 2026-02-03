#!/usr/bin/env python3
"""
Claude Project Sync - PDF Dashboard Generator

Generates a visual PDF report by SCANNING PROJECT_STATUS.md files.
No hardcoded data - reads from your actual projects.

Usage:
    python3 generate_status_pdf.py [--output /path/to/output.pdf]
    python3 generate_status_pdf.py --scan-paths ~/projects ~/work
"""

import argparse
import os
import re
from datetime import datetime
from io import BytesIO

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT


# =============================================================================
# DYNAMIC PROJECT SCANNING - Reads from PROJECT_STATUS.md files
# =============================================================================

DEFAULT_SCAN_PATHS = [
    os.path.expanduser('~'),  # Home directory (top level)
]

SKIP_DIRS = {
    'node_modules', '.git', '__pycache__', 'venv', '.venv',
    'dist', 'build', '.next', 'coverage', 'Library', '.Trash',
    'Applications', 'Pictures', 'Music', 'Movies', 'Documents'
}


def find_project_status_files(scan_paths=None, max_depth=2):
    """Find all PROJECT_STATUS.md files in scan paths."""
    if scan_paths is None:
        scan_paths = DEFAULT_SCAN_PATHS

    status_files = []

    for base_path in scan_paths:
        base_path = os.path.expanduser(base_path)
        if not os.path.isdir(base_path):
            continue

        for root, dirs, files in os.walk(base_path):
            # Calculate depth
            depth = root.replace(base_path, '').count(os.sep)
            if depth >= max_depth:
                dirs[:] = []  # Don't go deeper
                continue

            # Skip certain directories
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

            if 'PROJECT_STATUS.md' in files:
                status_files.append(os.path.join(root, 'PROJECT_STATUS.md'))

    return status_files


def extract_list_items(content, header_pattern, max_items=3):
    """Extract bullet points following a header pattern."""
    items = []
    # Find the header and get content after it
    match = re.search(header_pattern + r'\s*\n((?:[-*]\s+.+\n?)+)', content, re.MULTILINE)
    if match:
        list_text = match.group(1)
        # Extract individual items
        for line in list_text.split('\n'):
            line = line.strip()
            if line.startswith('-') or line.startswith('*'):
                item = line.lstrip('-* ').strip()
                # Skip placeholder items
                placeholder_words = ['describe', 'nothing yet', 'none yet', 'tbd', 'todo',
                                     'list ', 'add ', 'initial project', 'project structure']
                is_placeholder = (
                    item.startswith('(') or
                    any(pw in item.lower() for pw in placeholder_words) or
                    len(item) < 10
                )
                if item and not is_placeholder:
                    items.append(item)
                    if len(items) >= max_items:
                        break
    return items


def get_recent_commits(project_dir, max_commits=5):
    """Get recent meaningful commit messages from git log."""
    import subprocess

    # Garbage commit patterns to skip
    skip_patterns = [
        'add files via upload',
        'initial commit',
        'first commit',
        'init commit',
        'create readme',
        'update readme',
        'delete ',
        'remove ',
        'merge branch',
        'merge pull request',
        'wip',
        'fix typo',
        'minor fix',
        'small fix',
        'quick fix',
        'bump version',
        'update dependencies',
        'update package',
        'lint fix',
        'format code',
        'cleanup',
        'refactor',
    ]

    try:
        # Scan ALL commits to find meaningful ones
        result = subprocess.run(
            ['git', 'log', '--pretty=format:%s'],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            commits = []
            for line in result.stdout.strip().split('\n'):
                line = line.strip()
                if not line or len(line) < 15:
                    continue

                # Check against skip patterns
                line_lower = line.lower()
                is_garbage = any(pattern in line_lower for pattern in skip_patterns)

                if not is_garbage:
                    commits.append(line)
                    if len(commits) >= max_commits:
                        break
            return commits
    except Exception:
        pass
    return []


def parse_project_status(file_path):
    """Parse a PROJECT_STATUS.md file and extract metadata."""
    try:
        with open(file_path, 'r') as f:
            content = f.read()

        project = {
            'file_path': file_path,
            'project_path': os.path.dirname(file_path),
        }

        # Extract project name
        name_match = re.search(r'# PROJECT_STATUS:\s*(.+)', content)
        if name_match:
            project['name'] = name_match.group(1).strip()
        else:
            project['name'] = os.path.basename(os.path.dirname(file_path))

        # Extract from metadata table
        patterns = {
            'repo': r'\*\*Repository\*\*\s*\|\s*(.+)',
            'category': r'\*\*Category\*\*\s*\|\s*(.+)',
            'progress': r'\*\*Progress\*\*\s*\|\s*(\d+)',
            'status': r'\*\*Status\*\*\s*\|\s*(.+)',
            'has_repo': r'\*\*Has GitHub Repo\*\*\s*\|\s*(.+)',
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, content)
            if match:
                value = match.group(1).strip()
                if key == 'progress':
                    project[key] = int(value)
                else:
                    project[key] = value

        # Set defaults
        project.setdefault('progress', 0)
        project.setdefault('status', 'Unknown')
        project.setdefault('category', 'Personal')
        project.setdefault('repo', '')
        project.setdefault('has_repo', 'No')

        # Determine if has repo
        has_repo = project.get('has_repo', 'No').lower()
        project['has_github_repo'] = has_repo == 'yes' or (
            project['repo'] and 'not' not in project['repo'].lower()
        )

        # Extract features from "What's Working" section (most specific)
        features = extract_list_items(content, r"### What's Working", 5)

        # If not enough, try "What was built" entries
        if len(features) < 3:
            features.extend(extract_list_items(content, r'\*\*What was built:\*\*', 3))

        # Dedupe while preserving order
        seen = set()
        unique_features = []
        for f in features:
            if f.lower() not in seen:
                seen.add(f.lower())
                unique_features.append(f)
        project['features'] = unique_features[:5]

        # Get recent commits for additional context
        project['recent_commits'] = get_recent_commits(project['project_path'], 3)

        return project

    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return None


def load_projects(scan_paths=None):
    """Load all projects from PROJECT_STATUS.md files."""
    status_files = find_project_status_files(scan_paths)

    with_repos = []
    without_repos = []

    for sf in status_files:
        project = parse_project_status(sf)
        if project:
            if project['has_github_repo']:
                with_repos.append(project)
            else:
                without_repos.append(project)

    # Sort by progress descending
    with_repos.sort(key=lambda x: x['progress'], reverse=True)
    without_repos.sort(key=lambda x: x['progress'], reverse=True)

    return {'with_repos': with_repos, 'without_repos': without_repos}


# =============================================================================
# CHART GENERATION
# =============================================================================

def get_progress_color(progress):
    """Return color based on progress percentage."""
    if progress > 75:
        return '#2ECC71'  # Green
    elif progress >= 50:
        return '#3498DB'  # Blue
    elif progress >= 25:
        return '#F1C40F'  # Yellow
    else:
        return '#E74C3C'  # Red


def create_progress_chart(projects):
    """Create horizontal bar chart showing all project progress."""
    all_projects = projects['with_repos'] + projects['without_repos']

    if not all_projects:
        # Return empty chart if no projects
        fig, ax = plt.subplots(figsize=(6, 2))
        ax.text(0.5, 0.5, 'No projects found.\nRun init_project_status.py to add projects.',
                ha='center', va='center', fontsize=10)
        ax.axis('off')
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        plt.close()
        buf.seek(0)
        return buf

    all_projects.sort(key=lambda x: x['progress'], reverse=True)

    names = [p['name'] for p in all_projects]
    progress = [p['progress'] for p in all_projects]
    colors_list = [get_progress_color(p) for p in progress]

    # Adjust figure height based on number of projects
    fig_height = max(3, min(8, len(names) * 0.4))
    fig, ax = plt.subplots(figsize=(6, fig_height))

    y_pos = np.arange(len(names))
    bars = ax.barh(y_pos, progress, color=colors_list, height=0.7)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel('Progress %', fontsize=9)
    ax.set_title('Project Progress Overview', fontsize=11, fontweight='bold')

    for bar, pct in zip(bars, progress):
        ax.text(bar.get_width() + 2, bar.get_y() + bar.get_height()/2,
                f'{pct}%', va='center', fontsize=7)

    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    plt.close()
    buf.seek(0)
    return buf


def create_repo_pie_chart(projects):
    """Create pie chart showing GitHub repo status."""
    has_repo = len(projects['with_repos'])
    no_repo = len(projects['without_repos'])

    if has_repo == 0 and no_repo == 0:
        fig, ax = plt.subplots(figsize=(3.5, 3))
        ax.text(0.5, 0.5, 'No projects', ha='center', va='center')
        ax.axis('off')
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        plt.close()
        buf.seek(0)
        return buf

    fig, ax = plt.subplots(figsize=(3.5, 3))
    sizes = [has_repo, no_repo]
    labels = [f'Has Repo ({has_repo})', f'No Repo ({no_repo})']
    colors_list = ['#2ECC71', '#E74C3C']

    # Handle case where one is zero
    if has_repo == 0:
        sizes = [no_repo]
        labels = [f'No Repo ({no_repo})']
        colors_list = ['#E74C3C']
    elif no_repo == 0:
        sizes = [has_repo]
        labels = [f'Has Repo ({has_repo})']
        colors_list = ['#2ECC71']

    ax.pie(sizes, labels=labels, colors=colors_list,
           autopct='%1.0f%%', shadow=False, startangle=90,
           textprops={'fontsize': 8})
    ax.set_title('GitHub Repo Status', fontsize=10, fontweight='bold')

    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    plt.close()
    buf.seek(0)
    return buf


def create_category_chart(projects):
    """Create bar chart showing projects by category."""
    all_projects = projects['with_repos'] + projects['without_repos']

    if not all_projects:
        fig, ax = plt.subplots(figsize=(3.5, 2.5))
        ax.text(0.5, 0.5, 'No projects', ha='center', va='center')
        ax.axis('off')
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        plt.close()
        buf.seek(0)
        return buf

    categories = {}
    for p in all_projects:
        cat = p.get('category', 'Personal')
        categories[cat] = categories.get(cat, 0) + 1

    sorted_cats = sorted(categories.items(), key=lambda x: x[1], reverse=True)
    names = [c[0] for c in sorted_cats]
    counts = [c[1] for c in sorted_cats]

    cat_colors = {
        'Infrastructure': '#3498DB',
        'School': '#2ECC71',
        'Church': '#9B59B6',
        'Product': '#E67E22',
        'Research': '#1ABC9C',
        'Personal': '#95A5A6'
    }
    colors_list = [cat_colors.get(n, '#7F8C8D') for n in names]

    fig, ax = plt.subplots(figsize=(3.5, 2.5))
    x_pos = np.arange(len(names))
    bars = ax.bar(x_pos, counts, color=colors_list, width=0.6)

    ax.set_xticks(x_pos)
    ax.set_xticklabels(names, fontsize=7, rotation=45, ha='right')
    ax.set_ylabel('Count', fontsize=8)
    ax.set_title('Projects by Category', fontsize=10, fontweight='bold')
    ax.set_ylim(0, max(counts) + 1)

    for bar, count in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                str(count), ha='center', va='bottom', fontsize=8)

    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    plt.close()
    buf.seek(0)
    return buf


# =============================================================================
# PDF GENERATION
# =============================================================================

def create_pdf(output_path, projects):
    """Generate the complete PDF dashboard."""
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=0.5*inch,
        leftMargin=0.5*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'CustomTitle', parent=styles['Heading1'],
        fontSize=20, textColor=colors.HexColor('#2C3E50'), spaceAfter=6
    )
    subtitle_style = ParagraphStyle(
        'Subtitle', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor('#7F8C8D'), alignment=TA_RIGHT
    )
    section_style = ParagraphStyle(
        'Section', parent=styles['Heading2'],
        fontSize=14, textColor=colors.HexColor('#2C3E50'),
        spaceBefore=12, spaceAfter=6
    )
    subsection_style = ParagraphStyle(
        'Subsection', parent=styles['Heading3'],
        fontSize=11, textColor=colors.HexColor('#34495E'),
        spaceBefore=8, spaceAfter=4
    )
    footer_style = ParagraphStyle(
        'Footer', parent=styles['Normal'],
        fontSize=9, textColor=colors.HexColor('#95A5A6'), alignment=TA_CENTER
    )

    elements = []

    # Header
    now = datetime.now()
    date_str = now.strftime('%B %d, %Y at %I:%M %p')
    total_projects = len(projects['with_repos']) + len(projects['without_repos'])

    header_data = [
        [Paragraph('<b>Project Status Report</b>', title_style),
         Paragraph(f'Generated: {date_str}<br/>{total_projects} projects found', subtitle_style)]
    ]
    header_table = Table(header_data, colWidths=[4*inch, 3*inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.2*inch))

    elements.append(Paragraph('Dashboard', section_style))
    elements.append(Spacer(1, 0.1*inch))

    # Charts
    progress_chart = create_progress_chart(projects)
    pie_chart = create_repo_pie_chart(projects)
    category_chart = create_category_chart(projects)

    # Adjust chart height based on project count
    chart_height = max(3, min(5, total_projects * 0.35)) * inch
    progress_img = Image(progress_chart, width=4*inch, height=chart_height)
    pie_img = Image(pie_chart, width=2.8*inch, height=2.2*inch)
    category_img = Image(category_chart, width=2.8*inch, height=1.8*inch)

    right_charts = Table([[pie_img], [category_img]], colWidths=[3*inch])
    right_charts.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))

    chart_table = Table([[progress_img, right_charts]], colWidths=[4.2*inch, 3.3*inch])
    chart_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    elements.append(chart_table)
    elements.append(Spacer(1, 0.2*inch))

    # Table styles
    table_header_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2C3E50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#BDC3C7')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8F9FA')]),
    ])

    # Projects WITH repos
    if projects['with_repos']:
        elements.append(Paragraph('Projects with GitHub Repositories', subsection_style))
        with_repos_data = [['Project', 'Repository', 'Status', 'Progress']]
        for p in projects['with_repos']:
            with_repos_data.append([
                p['name'],
                p.get('repo', ''),
                p.get('status', ''),
                f"{p.get('progress', 0)}%"
            ])

        with_repos_table = Table(with_repos_data, colWidths=[1.5*inch, 2.5*inch, 1.3*inch, 0.8*inch])
        with_repos_table.setStyle(table_header_style)
        elements.append(with_repos_table)
        elements.append(Spacer(1, 0.15*inch))

    # Projects WITHOUT repos
    if projects['without_repos']:
        elements.append(Paragraph('Projects WITHOUT GitHub Repositories', subsection_style))
        without_repos_data = [['Project', 'Status', 'Progress', 'Category']]
        for p in projects['without_repos']:
            without_repos_data.append([
                p['name'],
                p.get('status', ''),
                f"{p.get('progress', 0)}%",
                p.get('category', 'Personal')
            ])

        without_repos_table = Table(without_repos_data, colWidths=[1.8*inch, 1.5*inch, 0.8*inch, 2*inch])
        without_repos_table.setStyle(table_header_style)
        elements.append(without_repos_table)

    # Footer for page 1
    elements.append(Spacer(1, 0.3*inch))
    elements.append(Paragraph('If this tool saves you time: Venmo @ctreada', footer_style))

    # ==========================================================================
    # PAGE 2: Features Built
    # ==========================================================================
    elements.append(PageBreak())

    # Page 2 Header
    elements.append(Paragraph('<b>Project Details: Features Built</b>', title_style))
    elements.append(Spacer(1, 0.2*inch))

    # Styles for page 2
    project_name_style = ParagraphStyle(
        'ProjectName', parent=styles['Heading3'],
        fontSize=11, textColor=colors.HexColor('#2C3E50'),
        spaceBefore=10, spaceAfter=2
    )
    label_style = ParagraphStyle(
        'Label', parent=styles['Normal'],
        fontSize=8, textColor=colors.HexColor('#7F8C8D'), fontName='Helvetica-Bold',
        spaceBefore=2, spaceAfter=1
    )
    item_style = ParagraphStyle(
        'Item', parent=styles['Normal'],
        fontSize=8, textColor=colors.HexColor('#2C3E50'),
        leftIndent=10, spaceBefore=1, spaceAfter=1
    )
    commit_style = ParagraphStyle(
        'Commit', parent=styles['Normal'],
        fontSize=7, textColor=colors.HexColor('#7F8C8D'),
        leftIndent=10, spaceBefore=1, spaceAfter=1, fontName='Courier'
    )

    all_projects = projects['with_repos'] + projects['without_repos']
    all_projects.sort(key=lambda x: x['name'])

    for p in all_projects:
        # Project name with progress
        progress = p.get('progress', 0)
        progress_color = '#2ECC71' if progress > 75 else '#3498DB' if progress >= 50 else '#F1C40F' if progress >= 25 else '#E74C3C'
        elements.append(Paragraph(
            f"<b>{p['name']}</b> <font color='{progress_color}'>({progress}%)</font>",
            project_name_style
        ))

        # Features (from What's Working)
        features = p.get('features', [])
        if features:
            elements.append(Paragraph('Working Features:', label_style))
            for item in features:
                display_item = item[:100] + '...' if len(item) > 100 else item
                elements.append(Paragraph(f"• {display_item}", item_style))

        # Recent commits
        commits = p.get('recent_commits', [])
        if commits:
            elements.append(Paragraph('Recent Work:', label_style))
            for commit in commits:
                display_commit = commit[:90] + '...' if len(commit) > 90 else commit
                elements.append(Paragraph(f"› {display_commit}", commit_style))

        # If nothing found, show minimal placeholder
        if not features and not commits:
            elements.append(Paragraph('<i>No features documented yet</i>', item_style))

        elements.append(Spacer(1, 0.08*inch))

    # Footer for page 2
    elements.append(Spacer(1, 0.2*inch))
    elements.append(Paragraph('If this tool saves you time: Venmo @ctreada', footer_style))

    doc.build(elements)
    print(f"PDF generated: {output_path}")
    print(f"  Projects with repos: {len(projects['with_repos'])}")
    print(f"  Projects without repos: {len(projects['without_repos'])}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate PDF dashboard from PROJECT_STATUS.md files'
    )
    parser.add_argument('--output', '-o', default=None,
                        help='Output path for the PDF')
    parser.add_argument('--scan-paths', nargs='+', default=None,
                        help='Paths to scan for PROJECT_STATUS.md files')
    args = parser.parse_args()

    # Load projects dynamically
    print("Scanning for PROJECT_STATUS.md files...")
    projects = load_projects(args.scan_paths)

    total = len(projects['with_repos']) + len(projects['without_repos'])
    if total == 0:
        print("\nNo PROJECT_STATUS.md files found!")
        print("Run init_project_status.py to create status files for your projects:")
        print("  python3 init_project_status.py ~/myproject --name 'My Project' --category School")
        return

    print(f"Found {total} projects")

    # Generate PDF
    if args.output is None:
        today = datetime.now().strftime('%Y-%m-%d')
        output_dir = os.path.expanduser('~/claude-project-sync')
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f'status_report_{today}.pdf')
    else:
        output_path = os.path.expanduser(args.output)

    create_pdf(output_path, projects)


if __name__ == '__main__':
    main()
