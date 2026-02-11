#!/usr/bin/env python3
"""
Claude Project Sync - Project Portfolio PDF Generator

Generates a narrative portfolio PDF by SCANNING PROJECT_STATUS.md files.
No hardcoded data - reads from your actual projects.

Output format matches the "Project Portfolio Status" style:
- Title header with name, date, project count
- Projects grouped by category (Church, School, Product, Infrastructure)
- Each project has a bold header with progress/status and a narrative paragraph

Usage:
    python3 generate_status_pdf.py [--output /path/to/output.pdf]
    python3 generate_status_pdf.py --scan-paths ~/projects ~/work
"""

import argparse
import os
import re
import zipfile
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, KeepTogether
)
from reportlab.lib.enums import TA_CENTER


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

# Category display order and grouping
CATEGORY_ORDER = [
    'Church',
    'School',
    'Product',
    'Infrastructure',
    'Personal',
    'Research',
]

# Map variations to canonical category names for grouping
CATEGORY_MAP = {
    'church': 'Church',
    'church / catholic tech': 'Church',
    'catholic tech': 'Church',
    'school': 'School',
    'education': 'School',
    'product': 'Product',
    'infrastructure': 'Infrastructure',
    'personal': 'Personal',
    'research': 'Research',
}


# =============================================================================
# CHAT HISTORY INTEGRATION - Reads from exported Claude chat files
# =============================================================================

def load_chat_files(chat_path):
    """Load text content from a zip file or directory of .md/.txt files.

    Returns a list of dicts: [{'filename': str, 'content': str}, ...]
    """
    chat_files = []

    if chat_path is None:
        return chat_files

    chat_path = os.path.expanduser(chat_path)

    if zipfile.is_zipfile(chat_path):
        with zipfile.ZipFile(chat_path, 'r') as zf:
            for name in zf.namelist():
                if name.endswith(('.md', '.txt', '.json')):
                    try:
                        raw = zf.read(name)
                        text = raw.decode('utf-8', errors='replace')
                        chat_files.append({
                            'filename': os.path.basename(name),
                            'content': text
                        })
                    except Exception:
                        continue
    elif os.path.isdir(chat_path):
        for root, _dirs, files in os.walk(chat_path):
            for fname in files:
                if fname.endswith(('.md', '.txt', '.json')):
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, 'r', errors='replace') as f:
                            text = f.read()
                        chat_files.append({
                            'filename': fname,
                            'content': text
                        })
                    except Exception:
                        continue
    else:
        # Single file
        try:
            with open(chat_path, 'r', errors='replace') as f:
                text = f.read()
            chat_files.append({
                'filename': os.path.basename(chat_path),
                'content': text
            })
        except Exception:
            pass

    return chat_files


def _build_search_terms(project_name):
    """Build a list of search patterns from a project name.

    'Sacramental Records' -> ['sacramental records', 'sacramentalrecords', 'sacramental']
    'Claude Project Sync v2' -> ['claude project sync', 'claudeprojectsync', 'claudesync']
    """
    name_lower = project_name.lower().strip()

    terms = set()
    terms.add(name_lower)

    # Remove version suffixes for matching
    no_version = re.sub(r'\s*v\d+(\.\d+)*\s*$', '', name_lower).strip()
    if no_version and len(no_version) > 3:
        terms.add(no_version)

    # Squashed (no spaces)
    squashed = name_lower.replace(' ', '')
    if len(squashed) > 5:
        terms.add(squashed)

    # First two significant words (for "Sacramental Records" -> "sacramental records")
    words = [w for w in name_lower.split() if len(w) > 2 and w not in ('the', 'and', 'for', 'app')]
    if len(words) >= 2:
        terms.add(words[0] + ' ' + words[1])

    # Single longest word if distinctive enough
    if words:
        longest = max(words, key=len)
        if len(longest) >= 8:
            terms.add(longest)

    return list(terms)


def _split_into_paragraphs(text):
    """Split text into meaningful paragraphs.

    Handles markdown conversations with --- separators, blank lines, etc.
    Filters out very short or code-heavy blocks.
    """
    # Strip common role markers used in chat exports
    # (Human:, Assistant:, User:, Claude:, etc.)
    cleaned = re.sub(r'^(Human|Assistant|User|Claude|System)\s*:', '', text, flags=re.MULTILINE)

    # Split on double newlines or --- separators
    raw_blocks = re.split(r'\n\s*\n|\n---+\n', cleaned)

    paragraphs = []
    for block in raw_blocks:
        block = block.strip()
        if not block:
            continue

        # Skip code blocks (```...```)
        if block.startswith('```'):
            continue

        # Skip very short blocks (headers, single words)
        if len(block) < 50:
            continue

        # Skip blocks that are mostly code or commands
        code_line_count = sum(1 for line in block.split('\n')
                              if line.strip().startswith(('$', '>', '#!', 'import ', 'from ', 'def ', 'class ')))
        total_lines = len(block.split('\n'))
        if total_lines > 1 and code_line_count / total_lines > 0.5:
            continue

        # Clean markdown formatting for readability
        clean = block.replace('**', '').replace('`', '')
        clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', clean)  # links -> text
        clean = re.sub(r'^#+\s+', '', clean, flags=re.MULTILINE)  # remove headers
        clean = re.sub(r'\n+', ' ', clean).strip()  # join into one line

        if len(clean) >= 50:
            paragraphs.append(clean)

    return paragraphs


def match_chat_to_projects(chat_files, projects, verbose=False):
    """Match chat history content to projects and extract the best snippets.

    Returns a dict: {project_name: [snippet1, snippet2, ...]}
    Each snippet is the most relevant paragraph about that project found in chats.
    """
    project_snippets = {}

    for project in projects:
        name = project.get('name', '')
        if not name:
            continue

        search_terms = _build_search_terms(name)
        scored_paragraphs = []

        for chat in chat_files:
            paragraphs = _split_into_paragraphs(chat['content'])

            for para in paragraphs:
                para_lower = para.lower()

                # Score based on how many search terms appear
                score = 0
                for term in search_terms:
                    count = para_lower.count(term)
                    if count > 0:
                        # Longer terms are more specific, worth more
                        score += count * len(term)

                if score > 0:
                    # Bonus for longer, more descriptive paragraphs (up to 500 chars)
                    length_bonus = min(len(para), 500) / 100
                    # Bonus for descriptive language
                    descriptive_words = ['project', 'build', 'feature', 'implement',
                                         'design', 'status', 'progress', 'complete',
                                         'working', 'develop', 'launch', 'deploy']
                    desc_bonus = sum(1 for w in descriptive_words if w in para_lower)
                    total_score = score + length_bonus + desc_bonus
                    scored_paragraphs.append((total_score, para))

        # Sort by score descending, take top snippets
        scored_paragraphs.sort(key=lambda x: x[0], reverse=True)

        # Pick the best 1-2 snippets, avoid redundancy
        best = []
        for _score, para in scored_paragraphs:
            # Skip if too similar to an already-picked snippet
            is_redundant = any(
                _overlap_ratio(para, existing) > 0.5
                for existing in best
            )
            if not is_redundant:
                best.append(para)
                if len(best) >= 2:
                    break

        if best:
            project_snippets[name] = best
            if verbose:
                print(f"  Chat match for '{name}': {len(scored_paragraphs)} candidates, "
                      f"kept {len(best)} snippets")

    return project_snippets


def _overlap_ratio(a, b):
    """Quick overlap check between two strings using word sets."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    smaller = min(len(words_a), len(words_b))
    return len(intersection) / smaller if smaller > 0 else 0.0


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

            for fname in files:
                if fname == 'PROJECT_STATUS.md' or (
                    fname.startswith('PROJECT_STATUS_') and fname.endswith('.md')
                ):
                    status_files.append(os.path.join(root, fname))

    return status_files


def extract_list_items(content, header_pattern, max_items=10):
    """Extract bullet points following a header pattern."""
    items = []
    match = re.search(header_pattern + r'\s*\n((?:[-*]\s+.+\n?)+)', content, re.MULTILINE)
    if match:
        list_text = match.group(1)
        for line in list_text.split('\n'):
            line = line.strip()
            if line.startswith('-') or line.startswith('*'):
                item = line.lstrip('-* ').strip()
                placeholder_words = ['describe', 'nothing yet', 'none yet', 'tbd', 'todo',
                                     'list ', 'add ', 'initial project', 'project structure']
                is_placeholder = (
                    item.startswith('(') or
                    any(pw in item.lower() for pw in placeholder_words) or
                    len(item) < 10
                )
                if item and not is_placeholder:
                    item = item.replace('**', '')
                    items.append(item)
                    if len(items) >= max_items:
                        break
    return items


def extract_section_text(content, header_pattern):
    """Extract the full text content under a markdown header, stopping at the next header."""
    match = re.search(
        header_pattern + r'\s*\n(.*?)(?=\n## |\n---|\Z)',
        content, re.DOTALL
    )
    if match:
        text = match.group(1).strip()
        # Clean up markdown artifacts
        text = text.replace('**', '')
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)  # links -> text
        # Remove bullet prefixes for a cleaner paragraph
        lines = []
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('- ') or line.startswith('* '):
                line = line[2:]
            if line:
                lines.append(line)
        return ' '.join(lines)
    return ''


def extract_next_steps(content):
    """Extract next steps from status file."""
    items = extract_list_items(content, r'## Next Steps', 5)
    if not items:
        items = extract_list_items(content, r'### Next Steps', 5)
    return items


def build_project_narrative(project, chat_snippets=None):
    """Build a narrative paragraph for a project from its status data.

    If chat_snippets are provided, they supplement the status file content
    to create richer descriptions.
    """
    parts = []

    # Use summary if available
    summary = project.get('summary', '')
    if summary:
        parts.append(summary)

    # Add working features if we need more content
    features = project.get('features', [])
    if features and not summary:
        if len(features) >= 3:
            parts.append(
                'Current capabilities include: ' +
                ', '.join(features[:5]).rstrip('.') + '.'
            )
        else:
            for f in features:
                parts.append(f.rstrip('.') + '.')

    # Add blockers
    blockers = project.get('blockers', [])
    if blockers:
        parts.append('Blockers: ' + '; '.join(blockers).rstrip('.') + '.')

    # Add next steps
    next_steps = project.get('next_steps', [])
    if next_steps:
        step_text = 'Next step is ' + next_steps[0].rstrip('.').lower() + '.'
        if len(next_steps) > 1:
            step_text = ('Next steps include ' +
                         ', '.join(s.rstrip('.').lower() for s in next_steps[:3]) + '.')
        parts.append(step_text)

    # Supplement with chat history snippets
    if chat_snippets:
        name = project.get('name', '')
        snippets = chat_snippets.get(name, [])
        if snippets:
            # Combine existing narrative text to check for redundancy
            existing_text = ' '.join(parts).lower()
            for snippet in snippets:
                # Only add if it brings genuinely new information
                if _overlap_ratio(snippet, existing_text) < 0.4:
                    # Trim to reasonable length for the PDF
                    trimmed = snippet[:600]
                    if len(snippet) > 600:
                        # Cut at last sentence boundary
                        last_period = trimmed.rfind('.')
                        if last_period > 300:
                            trimmed = trimmed[:last_period + 1]
                    parts.append(trimmed)

    if not parts:
        return 'Status file exists but no detailed description available yet.'

    return ' '.join(parts)


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
                value = match.group(1).strip().rstrip('|').strip()
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

        # Normalize category for grouping
        raw_cat = project['category'].lower().strip()
        project['category_group'] = CATEGORY_MAP.get(raw_cat, project['category'])

        # Determine if has repo
        has_repo = project.get('has_repo', 'No').lower()
        project['has_github_repo'] = has_repo == 'yes' or (
            project['repo']
            and 'not' not in project['repo'].lower()
            and 'none' not in project['repo'].lower()
        )

        # Extract project summary/description
        summary = extract_section_text(content, r'## Project Summary')
        if not summary:
            summary = extract_section_text(content, r'## Description')
        if not summary:
            summary = extract_section_text(content, r'## Notes')
        project['summary'] = summary

        # Extract features from "What's Working" section
        features = extract_list_items(content, r"### What's Working", 10)
        if len(features) < 3:
            features.extend(extract_list_items(content, r"### What Exists", 10))
        if len(features) < 3:
            features.extend(extract_list_items(content, r'\*\*What was built:\*\*', 5))

        # Dedupe while preserving order
        seen = set()
        unique_features = []
        for f in features:
            if f.lower() not in seen:
                seen.add(f.lower())
                unique_features.append(f)
        project['features'] = unique_features

        # Extract blockers
        blockers = extract_list_items(content, r'### Blockers', 5)
        # Filter out "none" type blockers
        blockers = [b for b in blockers if 'none' not in b.lower()[:10]]
        project['blockers'] = blockers

        # Extract not working
        not_working = extract_list_items(content, r"### What's Not Working", 5)
        if not not_working:
            not_working = extract_list_items(content, r"### What Doesn't Exist Yet", 5)
        project['not_working'] = not_working

        # Extract next steps
        project['next_steps'] = extract_next_steps(content)

        # Narrative is built later after chat history is loaded
        project['narrative'] = ''

        return project

    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return None


def load_projects(scan_paths=None, chat_history_path=None, verbose=False):
    """Load all projects from PROJECT_STATUS.md files.

    If chat_history_path is provided, also loads chat exports and matches
    them to projects to supplement the narrative descriptions.
    """
    status_files = find_project_status_files(scan_paths)

    if verbose:
        print(f"\nFound {len(status_files)} PROJECT_STATUS.md files:")
        for sf in status_files:
            print(f"  - {sf}")

    all_projects = []

    for sf in status_files:
        project = parse_project_status(sf)
        if project:
            all_projects.append(project)

    # Load chat history and match to projects
    chat_snippets = {}
    if chat_history_path:
        print(f"Loading chat history from: {chat_history_path}")
        chat_files = load_chat_files(chat_history_path)
        print(f"  Loaded {len(chat_files)} chat files")
        if chat_files:
            chat_snippets = match_chat_to_projects(chat_files, all_projects, verbose=verbose)
            print(f"  Matched chat context to {len(chat_snippets)} projects")

    # Build narratives (now with chat context available)
    for project in all_projects:
        project['narrative'] = build_project_narrative(project, chat_snippets)
        if verbose:
            print(f"\n{project['name']}:")
            print(f"  Category: {project['category_group']}")
            print(f"  Summary: {project.get('summary', '')[:60]}...")
            has_chat = project['name'] in chat_snippets
            print(f"  Chat context: {'Yes' if has_chat else 'No'}")
            print(f"  Narrative: {project.get('narrative', '')[:80]}...")

    # Sort by progress descending within each group
    all_projects.sort(key=lambda x: x['progress'], reverse=True)

    return all_projects


# =============================================================================
# PDF GENERATION - Narrative Portfolio Format
# =============================================================================

def create_pdf(output_path, all_projects):
    """Generate the narrative portfolio PDF."""
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=0.65*inch,
        leftMargin=0.65*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch
    )

    styles = getSampleStyleSheet()

    # Title: "Chris Treadaway — Project Portfolio Status"
    title_style = ParagraphStyle(
        'PortfolioTitle', parent=styles['Heading1'],
        fontSize=18, textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=2, fontName='Helvetica-Bold',
        alignment=TA_CENTER
    )

    # Subtitle: date and project count
    subtitle_style = ParagraphStyle(
        'PortfolioSubtitle', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor('#555555'),
        alignment=TA_CENTER, spaceAfter=16
    )

    # Category headers: "Church Projects", "School Projects", etc.
    category_style = ParagraphStyle(
        'CategoryHeader', parent=styles['Heading2'],
        fontSize=14, textColor=colors.HexColor('#2C3E50'),
        spaceBefore=16, spaceAfter=8,
        fontName='Helvetica-Bold',
        borderWidth=0, borderPadding=0,
    )

    # Project name + progress: "Ministry Fair App — 60% | Needs Testing"
    project_header_style = ParagraphStyle(
        'ProjectHeader', parent=styles['Heading3'],
        fontSize=10, textColor=colors.HexColor('#1a1a1a'),
        spaceBefore=10, spaceAfter=3,
        fontName='Helvetica-Bold',
    )

    # Project narrative paragraph
    narrative_style = ParagraphStyle(
        'Narrative', parent=styles['Normal'],
        fontSize=9, textColor=colors.HexColor('#333333'),
        leading=13, spaceAfter=6,
        fontName='Helvetica',
    )

    # Separator line style
    separator_style = ParagraphStyle(
        'Separator', parent=styles['Normal'],
        fontSize=2, spaceAfter=4, spaceBefore=4,
    )

    # Footer
    footer_style = ParagraphStyle(
        'Footer', parent=styles['Normal'],
        fontSize=8, textColor=colors.HexColor('#999999'),
        alignment=TA_CENTER, spaceBefore=20
    )

    elements = []

    # === HEADER ===
    now = datetime.now()
    date_str = now.strftime('%B %d, %Y')
    total_projects = len(all_projects)

    # Build category summary for subtitle
    cat_counts = {}
    for p in all_projects:
        cat = p.get('category_group', 'Personal')
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    cat_parts = []
    for cat in CATEGORY_ORDER:
        if cat in cat_counts:
            cat_parts.append(cat)
    cat_summary = ', '.join(cat_parts[:-1])
    if len(cat_parts) > 1:
        cat_summary += ' &amp; ' + cat_parts[-1]
    elif cat_parts:
        cat_summary = cat_parts[0]

    elements.append(Paragraph(
        'Chris Treadaway — Project Portfolio Status',
        title_style
    ))
    elements.append(Paragraph(
        f'{date_str} | {total_projects} Projects Across {cat_summary}',
        subtitle_style
    ))

    # === GROUP PROJECTS BY CATEGORY ===
    grouped = {}
    for p in all_projects:
        cat = p.get('category_group', 'Personal')
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(p)

    # Sort within each category by progress descending
    for cat in grouped:
        grouped[cat].sort(key=lambda x: x['progress'], reverse=True)

    # Render categories in order
    for cat in CATEGORY_ORDER:
        if cat not in grouped:
            continue

        projects = grouped[cat]

        # Category header with suffix "Projects" (except Personal)
        if cat in ('Infrastructure', 'Personal'):
            cat_label = 'Infrastructure &amp; Personal Projects'
            # Merge personal into infrastructure section
            if cat == 'Personal':
                continue  # handled when we hit Infrastructure
            if 'Personal' in grouped:
                projects = projects + grouped['Personal']
        else:
            cat_label = f'{cat} Projects'

        elements.append(Paragraph(cat_label, category_style))

        # Render each project
        for p in projects:
            progress = p.get('progress', 0)
            status = p.get('status', '')
            name = p.get('name', 'Unknown')

            # Format progress display
            if progress > 0:
                progress_str = f"{progress}%"
            else:
                progress_str = ''

            # Build header: "Project Name — 60% | Status"
            header_parts = [name]
            detail_parts = []
            if progress_str:
                detail_parts.append(progress_str)
            if status:
                detail_parts.append(status)

            if detail_parts:
                header_text = f"{name} — {' | '.join(detail_parts)}"
            else:
                header_text = name

            narrative = p.get('narrative', 'No description available.')

            # KeepTogether prevents orphaned headers
            project_block = [
                Paragraph(header_text, project_header_style),
                Paragraph(narrative, narrative_style),
            ]
            elements.append(KeepTogether(project_block))

    # Handle categories not in CATEGORY_ORDER
    for cat in grouped:
        if cat not in CATEGORY_ORDER and cat != 'Personal':
            elements.append(Paragraph(f'{cat} Projects', category_style))
            for p in grouped[cat]:
                progress = p.get('progress', 0)
                status = p.get('status', '')
                name = p.get('name', 'Unknown')
                detail_parts = []
                if progress > 0:
                    detail_parts.append(f"{progress}%")
                if status:
                    detail_parts.append(status)
                if detail_parts:
                    header_text = f"{name} — {' | '.join(detail_parts)}"
                else:
                    header_text = name
                narrative = p.get('narrative', 'No description available.')
                project_block = [
                    Paragraph(header_text, project_header_style),
                    Paragraph(narrative, narrative_style),
                ]
                elements.append(KeepTogether(project_block))

    # Footer
    elements.append(Spacer(1, 0.3*inch))
    elements.append(Paragraph('If this tool saves you time: Venmo @ctreada', footer_style))

    doc.build(elements)
    print(f"PDF generated: {output_path}")
    print(f"  {total_projects} projects across {len(grouped)} categories")


def main():
    parser = argparse.ArgumentParser(
        description='Generate project portfolio PDF from PROJECT_STATUS.md files'
    )
    parser.add_argument('--output', '-o', default=None,
                        help='Output path for the PDF')
    parser.add_argument('--scan-paths', nargs='+', default=None,
                        help='Paths to scan for PROJECT_STATUS.md files')
    parser.add_argument('--chat-history', '-c', default=None,
                        help='Path to chat history zip file or directory of .md/.txt exports')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show detailed debug output')
    args = parser.parse_args()

    # Load projects dynamically
    print("Scanning for PROJECT_STATUS.md files...")
    all_projects = load_projects(
        args.scan_paths,
        chat_history_path=args.chat_history,
        verbose=args.verbose
    )

    if not all_projects:
        print("\nNo PROJECT_STATUS.md files found!")
        print("Run init_project_status.py to create status files for your projects:")
        print("  python3 init_project_status.py ~/myproject --name 'My Project' --category School")
        return

    print(f"Found {len(all_projects)} projects")

    # Generate PDF
    if args.output is None:
        today = datetime.now().strftime('%Y-%m-%d')
        output_dir = os.path.expanduser('~/Downloads')
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f'Project_Portfolio_Status_{today}.pdf')
    else:
        output_path = os.path.expanduser(args.output)

    create_pdf(output_path, all_projects)


if __name__ == '__main__':
    main()
