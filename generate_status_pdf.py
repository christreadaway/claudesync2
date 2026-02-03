#!/usr/bin/env python3
"""
Claude Project Sync - PDF Dashboard Generator

Generates a visual PDF report with charts showing all project progress.
Run daily at 6am via launchd or manually as needed.

NOTE: This generates STATUS data. It does NOT generate instructions.
      Instructions belong in ~/.claude/CLAUDE.md (separate file).

Usage:
    python3 generate_status_pdf.py [--output /path/to/output.pdf]
"""

import argparse
import os
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
# PROJECT DATA - Update this dictionary when projects change
# =============================================================================

PROJECTS = {
    'with_repos': [
        {
            'name': 'claude-project-sync',
            'repo': 'christreadaway/claude-project-sync',
            'status': 'Built',
            'progress': 90,
            'category': 'Infrastructure'
        },
        {
            'name': 'ParentPoint',
            'repo': 'christreadaway/parentpoint',
            'status': 'Beta Live',
            'progress': 70,
            'category': 'School'
        },
        {
            'name': 'ParentPoint EDU',
            'repo': 'christreadaway/parentpoint',
            'status': 'Ready to Build',
            'progress': 30,
            'category': 'School'
        },
        {
            'name': 'Ministry Fair App',
            'repo': 'christreadaway/ministryfair',
            'status': 'Needs Testing',
            'progress': 60,
            'category': 'Church'
        },
        {
            'name': 'Desmond',
            'repo': 'Public repo',
            'status': 'v1 Shipped',
            'progress': 100,
            'category': 'Infrastructure'
        },
        {
            'name': 'multiloc.ai',
            'repo': 'christreadaway/polygraph',
            'status': 'Domain Bought',
            'progress': 40,
            'category': 'Product'
        },
    ],
    'without_repos': [
        {
            'name': 'Audioscribe',
            'status': 'v1 Working',
            'progress': 75,
            'category': 'Product',
            'action_needed': 'Push to GitHub after Patreon'
        },
        {
            'name': 'eSPACE MCP',
            'status': 'Complete',
            'progress': 95,
            'category': 'Infrastructure',
            'action_needed': 'Create repo, document'
        },
        {
            'name': 'RenWeb MCP',
            'status': 'Planned',
            'progress': 10,
            'category': 'School',
            'action_needed': 'Scope complete, build next'
        },
        {
            'name': 'MinistryPlatform MCP',
            'status': 'Planned',
            'progress': 10,
            'category': 'Church',
            'action_needed': 'Scope complete, build next'
        },
        {
            'name': 'Bluewave MCP',
            'status': 'Planned',
            'progress': 5,
            'category': 'Church',
            'action_needed': 'Requires SQL approach'
        },
        {
            'name': 'Vaticoin',
            'status': 'Shelved',
            'progress': 25,
            'category': 'Product',
            'action_needed': 'Waiting on Vatican interest'
        },
        {
            'name': "Kim's Site",
            'status': 'Deadline-driven',
            'progress': 50,
            'category': 'Personal',
            'action_needed': 'WordPress, no repo needed'
        },
    ]
}

NON_PROJECT_ITEMS = {
    'Content & Thought Leadership': [
        {'name': 'Catholic MBA', 'status': 'GTM Built, Not Launched'},
        {'name': 'Modernize Catholic', 'status': '2 Posts Done'},
        {'name': 'Book Project', 'status': 'Not Started'},
    ],
    'Church Operations': [
        {'name': 'Emergency Procedures', 'status': 'Complete'},
        {'name': 'Facilities Onboarding', 'status': 'Complete'},
        {'name': 'Sacramental Records', 'status': 'Concept Stage'},
    ],
    'School Operations': [
        {'name': 'The Human Code Class', 'status': 'Teaching Active'},
    ],
    'Research & Personal': [
        {'name': 'Randy', 'status': 'TBD'},
        {'name': 'Ralph Wiggums', 'status': 'TBD'},
        {'name': 'HEB Scraper', 'status': 'Blocked'},
        {'name': '2026 Fitness Goals', 'status': 'Active'},
    ],
}


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


def create_progress_chart():
    """Create horizontal bar chart showing all project progress."""
    all_projects = PROJECTS['with_repos'] + PROJECTS['without_repos']
    all_projects.sort(key=lambda x: x['progress'], reverse=True)

    names = [p['name'] for p in all_projects]
    progress = [p['progress'] for p in all_projects]
    colors_list = [get_progress_color(p) for p in progress]

    fig, ax = plt.subplots(figsize=(6, 5))
    y_pos = np.arange(len(names))
    bars = ax.barh(y_pos, progress, color=colors_list, height=0.7)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel('Progress %', fontsize=9)
    ax.set_title('Project Progress Overview', fontsize=11, fontweight='bold')

    for i, (bar, pct) in enumerate(zip(bars, progress)):
        ax.text(bar.get_width() + 2, bar.get_y() + bar.get_height()/2,
                f'{pct}%', va='center', fontsize=7)

    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    plt.close()
    buf.seek(0)
    return buf


def create_repo_pie_chart():
    """Create pie chart showing GitHub repo status."""
    has_repo = len(PROJECTS['with_repos'])
    no_repo = len(PROJECTS['without_repos'])

    fig, ax = plt.subplots(figsize=(3.5, 3))
    sizes = [has_repo, no_repo]
    labels = [f'Has Repo ({has_repo})', f'No Repo ({no_repo})']
    colors_list = ['#2ECC71', '#E74C3C']
    explode = (0.05, 0)

    ax.pie(sizes, explode=explode, labels=labels, colors=colors_list,
           autopct='%1.0f%%', shadow=False, startangle=90,
           textprops={'fontsize': 8})
    ax.set_title('GitHub Repo Status', fontsize=10, fontweight='bold')

    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    plt.close()
    buf.seek(0)
    return buf


def create_category_chart():
    """Create bar chart showing projects by category."""
    all_projects = PROJECTS['with_repos'] + PROJECTS['without_repos']
    categories = {}
    for p in all_projects:
        cat = p['category']
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


def create_pdf(output_path):
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
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=20,
        textColor=colors.HexColor('#2C3E50'),
        spaceAfter=6
    )

    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#7F8C8D'),
        alignment=TA_RIGHT
    )

    section_style = ParagraphStyle(
        'Section',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#2C3E50'),
        spaceBefore=12,
        spaceAfter=6
    )

    subsection_style = ParagraphStyle(
        'Subsection',
        parent=styles['Heading3'],
        fontSize=11,
        textColor=colors.HexColor('#34495E'),
        spaceBefore=8,
        spaceAfter=4
    )

    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#95A5A6'),
        alignment=TA_CENTER
    )

    elements = []

    # Header
    now = datetime.now()
    date_str = now.strftime('%B %d, %Y at %I:%M %p')

    header_data = [
        [Paragraph('<b>Project Status Report</b>', title_style),
         Paragraph(f'Generated: {date_str}', subtitle_style)]
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
    progress_chart = create_progress_chart()
    pie_chart = create_repo_pie_chart()
    category_chart = create_category_chart()

    progress_img = Image(progress_chart, width=4*inch, height=3.3*inch)
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
    elements.append(Paragraph('Projects with GitHub Repositories', subsection_style))
    with_repos_data = [['Project', 'Repository', 'Status', 'Progress']]
    for p in PROJECTS['with_repos']:
        with_repos_data.append([p['name'], p['repo'], p['status'], f"{p['progress']}%"])

    with_repos_table = Table(with_repos_data, colWidths=[1.5*inch, 2.5*inch, 1.3*inch, 0.8*inch])
    with_repos_table.setStyle(table_header_style)
    elements.append(with_repos_table)
    elements.append(Spacer(1, 0.15*inch))

    # Projects WITHOUT repos
    elements.append(Paragraph('Projects WITHOUT GitHub Repositories', subsection_style))
    without_repos_data = [['Project', 'Status', 'Progress', 'Action Needed']]
    for p in PROJECTS['without_repos']:
        without_repos_data.append([p['name'], p['status'], f"{p['progress']}%", p.get('action_needed', '')])

    without_repos_table = Table(without_repos_data, colWidths=[1.5*inch, 1.2*inch, 0.8*inch, 2.6*inch])
    without_repos_table.setStyle(table_header_style)
    elements.append(without_repos_table)

    # Page 2: Non-project items
    elements.append(PageBreak())
    elements.append(Paragraph('Non-Project Items', section_style))

    for category, items in NON_PROJECT_ITEMS.items():
        elements.append(Paragraph(category, subsection_style))
        items_data = [['Item', 'Status']]
        for item in items:
            items_data.append([item['name'], item['status']])
        items_table = Table(items_data, colWidths=[3*inch, 3*inch])
        items_table.setStyle(table_header_style)
        elements.append(items_table)
        elements.append(Spacer(1, 0.1*inch))

    # Footer
    elements.append(Spacer(1, 0.3*inch))
    elements.append(Paragraph('If this tool saves you time: Venmo @ctreada', footer_style))

    doc.build(elements)
    print(f"PDF generated: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Generate Claude Project Sync PDF dashboard')
    parser.add_argument('--output', '-o', default=None,
                        help='Output path for the PDF')
    args = parser.parse_args()

    if args.output is None:
        today = datetime.now().strftime('%Y-%m-%d')
        output_dir = os.path.expanduser('~/claude-project-sync')
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f'status_report_{today}.pdf')
    else:
        output_path = os.path.expanduser(args.output)

    create_pdf(output_path)


if __name__ == '__main__':
    main()
