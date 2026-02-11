#!/usr/bin/env python3
"""
Claude Project Sync - Project Portfolio PDF Generator

Generates a narrative portfolio PDF by SCANNING PROJECT_STATUS.md files
and optionally integrating Claude chat history exports.

The PDF bridges context between Claude Code and Claude.ai chat by showing:
- Project summaries with progress/status
- Timestamped activity timeline (from Progress Log + chat history)
- Open threads: blockers, unresolved questions, next steps
- Cross-project view of everything left unfinished

Usage:
    python3 generate_status_pdf.py [--output /path/to/output.pdf]
    python3 generate_status_pdf.py --chat-history ~/claude-export.zip
    python3 generate_status_pdf.py --scan-paths ~/projects ~/work -v
"""

import argparse
import os
import re
import subprocess
import zipfile
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, KeepTogether,
    HRFlowable
)
from reportlab.lib.enums import TA_CENTER


# =============================================================================
# CONFIGURATION
# =============================================================================

DEFAULT_SCAN_PATHS = [
    os.path.expanduser('~'),
]

SKIP_DIRS = {
    'node_modules', '.git', '__pycache__', 'venv', '.venv',
    'dist', 'build', '.next', 'coverage', 'Library', '.Trash',
    'Applications', 'Pictures', 'Music', 'Movies', 'Documents'
}

CATEGORY_ORDER = [
    'Church', 'School', 'Product', 'Infrastructure', 'Personal', 'Research',
]

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
# CHAT HISTORY INTEGRATION
# =============================================================================

def load_chat_files(chat_path):
    """Load text content from a zip file, directory, or single file."""
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
                        # Try to get file modification time from zip
                        info = zf.getinfo(name)
                        mod_time = datetime(*info.date_time) if info.date_time else None
                        chat_files.append({
                            'filename': os.path.basename(name),
                            'content': text,
                            'date': mod_time,
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
                        mod_time = datetime.fromtimestamp(os.path.getmtime(fpath))
                        chat_files.append({
                            'filename': fname,
                            'content': text,
                            'date': mod_time,
                        })
                    except Exception:
                        continue
    else:
        try:
            with open(chat_path, 'r', errors='replace') as f:
                text = f.read()
            mod_time = datetime.fromtimestamp(os.path.getmtime(chat_path))
            chat_files.append({
                'filename': os.path.basename(chat_path),
                'content': text,
                'date': mod_time,
            })
        except Exception:
            pass

    return chat_files


def _build_search_terms(project_name):
    """Build fuzzy search patterns from a project name."""
    name_lower = project_name.lower().strip()
    terms = set()
    terms.add(name_lower)

    no_version = re.sub(r'\s*v\d+(\.\d+)*\s*$', '', name_lower).strip()
    if no_version and len(no_version) > 3:
        terms.add(no_version)

    squashed = name_lower.replace(' ', '')
    if len(squashed) > 5:
        terms.add(squashed)

    words = [w for w in name_lower.split() if len(w) > 2 and w not in ('the', 'and', 'for', 'app')]
    if len(words) >= 2:
        terms.add(words[0] + ' ' + words[1])

    if words:
        longest = max(words, key=len)
        if len(longest) >= 8:
            terms.add(longest)

    return list(terms)


def _split_into_paragraphs(text):
    """Split chat text into meaningful paragraphs, filtering out code blocks."""
    cleaned = re.sub(r'^(Human|Assistant|User|Claude|System)\s*:', '', text, flags=re.MULTILINE)
    raw_blocks = re.split(r'\n\s*\n|\n---+\n', cleaned)

    paragraphs = []
    for block in raw_blocks:
        block = block.strip()
        if not block or block.startswith('```') or len(block) < 50:
            continue

        code_line_count = sum(1 for line in block.split('\n')
                              if line.strip().startswith(('$', '>', '#!', 'import ', 'from ', 'def ', 'class ')))
        total_lines = len(block.split('\n'))
        if total_lines > 1 and code_line_count / total_lines > 0.5:
            continue

        clean = block.replace('**', '').replace('`', '')
        clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', clean)
        clean = re.sub(r'^#+\s+', '', clean, flags=re.MULTILINE)
        clean = re.sub(r'\n+', ' ', clean).strip()

        if len(clean) >= 50:
            paragraphs.append(clean)

    return paragraphs


def _overlap_ratio(a, b):
    """Quick overlap check between two strings using word sets."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    smaller = min(len(words_a), len(words_b))
    return len(intersection) / smaller if smaller > 0 else 0.0


def match_chat_to_projects(chat_files, projects, verbose=False):
    """Match chat history to projects. Returns dict of snippets and dated entries."""
    project_chat_data = {}

    for project in projects:
        name = project.get('name', '')
        if not name:
            continue

        search_terms = _build_search_terms(name)
        scored_paragraphs = []

        for chat in chat_files:
            paragraphs = _split_into_paragraphs(chat['content'])
            chat_date = chat.get('date')
            chat_filename = chat.get('filename', '')

            for para in paragraphs:
                para_lower = para.lower()
                score = 0
                for term in search_terms:
                    count = para_lower.count(term)
                    if count > 0:
                        score += count * len(term)

                if score > 0:
                    length_bonus = min(len(para), 500) / 100
                    descriptive_words = ['project', 'build', 'feature', 'implement',
                                         'design', 'status', 'progress', 'complete',
                                         'working', 'develop', 'launch', 'deploy']
                    desc_bonus = sum(1 for w in descriptive_words if w in para_lower)
                    total_score = score + length_bonus + desc_bonus
                    scored_paragraphs.append((total_score, para, chat_date, chat_filename))

        scored_paragraphs.sort(key=lambda x: x[0], reverse=True)

        # Best snippets for narrative
        best_snippets = []
        # Dated entries for timeline
        dated_entries = []

        for _score, para, chat_date, chat_filename in scored_paragraphs:
            is_redundant = any(_overlap_ratio(para, existing) > 0.5 for existing in best_snippets)
            if not is_redundant:
                best_snippets.append(para)

                # Create a dated timeline entry from chat
                if chat_date:
                    date_str = chat_date.strftime('%Y-%m-%d')
                else:
                    date_str = 'Unknown date'
                # Use chat filename as source hint
                source_hint = chat_filename.replace('.md', '').replace('.txt', '').replace('_', ' ')
                summary_line = para[:150]
                if len(para) > 150:
                    last_period = summary_line.rfind('.')
                    if last_period > 80:
                        summary_line = summary_line[:last_period + 1]
                    else:
                        summary_line = summary_line + '...'

                dated_entries.append({
                    'date': date_str,
                    'source': f'Claude.ai Chat — {source_hint}',
                    'text': summary_line,
                })

                if len(best_snippets) >= 8:
                    break

        if best_snippets or dated_entries:
            project_chat_data[name] = {
                'snippets': best_snippets,
                'timeline_entries': dated_entries,
            }
            if verbose:
                print(f"  Chat match for '{name}': {len(scored_paragraphs)} candidates, "
                      f"kept {len(best_snippets)} snippets, {len(dated_entries)} timeline entries")

    return project_chat_data


# =============================================================================
# PROJECT STATUS FILE PARSING
# =============================================================================

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
            depth = root.replace(base_path, '').count(os.sep)
            if depth >= max_depth:
                dirs[:] = []
                continue
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
    """Extract full text content under a markdown header."""
    match = re.search(
        header_pattern + r'\s*\n(.*?)(?=\n## |\n---|\Z)',
        content, re.DOTALL
    )
    if match:
        text = match.group(1).strip()
        text = text.replace('**', '')
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        lines = []
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('- ') or line.startswith('* '):
                line = line[2:]
            if line:
                lines.append(line)
        return ' '.join(lines)
    return ''


def extract_progress_log(content):
    """Parse the ## Progress Log section into dated entries.

    Returns a list of dicts: [{'date': str, 'source': str, 'text': str}, ...]
    sorted newest first.
    """
    entries = []

    # Find the Progress Log section
    log_match = re.search(r'## Progress Log\s*\n(.*?)(?=\n## |\n---\s*\n\*Last|\Z)',
                          content, re.DOTALL)
    if not log_match:
        return entries

    log_text = log_match.group(1)

    # Split on ### headers which are date entries
    # Pattern: ### 2026-02-04 (Claude.ai Chat — Topic)
    # or: ### 2026-02-04 (Claude Code)
    # or: ### 2025-12-17
    entry_pattern = r'###\s+(\d{4}-\d{2}-\d{2})(?:\s+\(([^)]*)\))?\s*\n'
    parts = re.split(entry_pattern, log_text)

    # parts[0] is before first match (usually empty), then groups of 3: date, source, body
    i = 1
    while i < len(parts):
        date_str = parts[i].strip() if i < len(parts) else ''
        source = parts[i + 1].strip() if i + 1 < len(parts) and parts[i + 1] else ''
        body = parts[i + 2].strip() if i + 2 < len(parts) else ''
        i += 3

        if not date_str:
            continue

        # Clean up the body: extract source line and bullet points
        body_lines = []
        for line in body.split('\n'):
            line = line.strip()
            if line.startswith('**Source:**'):
                # Already captured source from header; skip or supplement
                if not source:
                    source = line.replace('**Source:**', '').strip()
                continue
            if line.startswith('- ') or line.startswith('* '):
                line = line.lstrip('-* ').strip()
            if line:
                line = line.replace('**', '')
                body_lines.append(line)

        if body_lines:
            # Combine into a summary, keeping it concise
            combined = ' '.join(body_lines)
            # Trim to ~250 chars for the timeline view
            if len(combined) > 250:
                trimmed = combined[:250]
                last_period = trimmed.rfind('.')
                if last_period > 150:
                    combined = trimmed[:last_period + 1]
                else:
                    combined = trimmed + '...'

            entries.append({
                'date': date_str,
                'source': source or 'Unknown',
                'text': combined,
            })

    return entries


def extract_open_questions(content):
    """Extract open design questions from markdown tables."""
    questions = []

    # Look for tables with | # | Question | pattern
    table_match = re.search(
        r'## Open Design Questions.*?\n\|.*?\|.*?\|.*?\n\|[-\s|]+\n((?:\|.*\n)*)',
        content, re.DOTALL
    )
    if table_match:
        rows = table_match.group(1).strip().split('\n')
        for row in rows:
            cells = [c.strip() for c in row.split('|') if c.strip()]
            if len(cells) >= 2:
                question = cells[1].strip()
                if question and len(question) > 10:
                    questions.append(question)

    return questions


def extract_next_steps(content):
    """Extract next steps from status file."""
    items = extract_list_items(content, r'## Next Steps', 8)
    if not items:
        items = extract_list_items(content, r'### Next Steps', 8)

    # Also try numbered lists
    if not items:
        match = re.search(r'## Next Steps\s*\n((?:\d+\.\s+.+\n?)+)', content, re.MULTILINE)
        if match:
            for line in match.group(1).split('\n'):
                line = line.strip()
                line = re.sub(r'^\d+\.\s+', '', line).strip()
                if line and len(line) > 5:
                    items.append(line.replace('**', ''))
                    if len(items) >= 8:
                        break

    return items


def get_dated_commits(project_dir, max_commits=50):
    """Get recent commits with dates from a git repo.

    Returns list of dicts: [{'date': 'YYYY-MM-DD', 'source': 'Git Commit', 'text': '...'}, ...]
    """
    commits = []
    git_dir = os.path.join(project_dir, '.git')
    if not os.path.isdir(git_dir):
        return commits

    skip_patterns = [
        'add files via upload', 'initial commit', 'first commit',
        'merge branch', 'merge pull request', 'wip', 'fix typo',
        'minor fix', 'bump version', 'update dependencies', 'lint fix',
        'format code', 'cleanup',
    ]

    try:
        result = subprocess.run(
            ['git', 'log', '--all', '--pretty=format:%ad|%s', '--date=short'],
            cwd=project_dir, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if '|' not in line:
                    continue
                date_str, message = line.split('|', 1)
                date_str = date_str.strip()
                message = message.strip()

                if not message or len(message) < 10:
                    continue

                msg_lower = message.lower()
                if any(p in msg_lower for p in skip_patterns):
                    continue

                commits.append({
                    'date': date_str,
                    'source': 'Git Commit',
                    'text': message,
                })

                if len(commits) >= max_commits:
                    break
    except Exception:
        pass

    return commits


def parse_project_status(file_path):
    """Parse a PROJECT_STATUS.md file and extract all metadata including temporal data."""
    try:
        with open(file_path, 'r') as f:
            content = f.read()

        project = {
            'file_path': file_path,
            'project_path': os.path.dirname(file_path),
        }

        # Project name
        name_match = re.search(r'# PROJECT_STATUS:\s*(.+)', content)
        if name_match:
            project['name'] = name_match.group(1).strip()
        else:
            project['name'] = os.path.basename(os.path.dirname(file_path))

        # Metadata table
        patterns = {
            'repo': r'\*\*Repository\*\*\s*\|\s*(.+)',
            'category': r'\*\*Category\*\*\s*\|\s*(.+)',
            'progress': r'\*\*Progress\*\*\s*\|\s*(\d+)',
            'status': r'\*\*Status\*\*\s*\|\s*(.+)',
            'has_repo': r'\*\*Has GitHub Repo\*\*\s*\|\s*(.+)',
            'last_worked': r'\*\*Last Worked\*\*\s*\|\s*(.+)',
            'last_synced': r'\*\*Last Synced to Claude\.ai\*\*\s*\|\s*(.+)',
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, content)
            if match:
                value = match.group(1).strip().rstrip('|').strip()
                if key == 'progress':
                    project[key] = int(value)
                else:
                    project[key] = value

        # Defaults
        project.setdefault('progress', 0)
        project.setdefault('status', 'Unknown')
        project.setdefault('category', 'Personal')
        project.setdefault('repo', '')
        project.setdefault('has_repo', 'No')
        project.setdefault('last_worked', '')
        project.setdefault('last_synced', '')

        # Normalize category
        raw_cat = project['category'].lower().strip()
        project['category_group'] = CATEGORY_MAP.get(raw_cat, project['category'])

        # Has repo?
        has_repo = project.get('has_repo', 'No').lower()
        project['has_github_repo'] = has_repo == 'yes' or (
            project['repo']
            and 'not' not in project['repo'].lower()
            and 'none' not in project['repo'].lower()
        )

        # Summary/description
        summary = extract_section_text(content, r'## Project Summary')
        if not summary:
            summary = extract_section_text(content, r'## Description')
        if not summary:
            summary = extract_section_text(content, r'## Notes')
        project['summary'] = summary

        # Features
        features = extract_list_items(content, r"### What's Working", 10)
        if len(features) < 3:
            features.extend(extract_list_items(content, r"### What Exists", 10))
        seen = set()
        unique = []
        for f in features:
            if f.lower() not in seen:
                seen.add(f.lower())
                unique.append(f)
        project['features'] = unique

        # Blockers
        blockers = extract_list_items(content, r'### Blockers', 5)
        blockers = [b for b in blockers if 'none' not in b.lower()[:10]]
        project['blockers'] = blockers

        # Not working / doesn't exist yet
        not_working = extract_list_items(content, r"### What's Not Working", 5)
        if not not_working:
            not_working = extract_list_items(content, r"### What Doesn't Exist Yet", 5)
        project['not_working'] = not_working

        # Next steps
        project['next_steps'] = extract_next_steps(content)

        # Open design questions
        project['open_questions'] = extract_open_questions(content)

        # Progress log (temporal data!)
        project['progress_log'] = extract_progress_log(content)

        # Git commits (temporal data!)
        if project['has_github_repo']:
            project['git_commits'] = get_dated_commits(project['project_path'])
        else:
            project['git_commits'] = []

        # Narrative and timeline built later after chat history is loaded
        project['narrative'] = ''
        project['timeline'] = []
        project['open_threads'] = []

        return project

    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return None


# =============================================================================
# NARRATIVE + TIMELINE BUILDING
# =============================================================================

def build_project_narrative(project, chat_data=None):
    """Build the summary narrative paragraph."""
    parts = []

    summary = project.get('summary', '')
    if summary:
        parts.append(summary)

    features = project.get('features', [])
    if features and not summary:
        if len(features) >= 3:
            parts.append('Current capabilities include: ' +
                         ', '.join(features[:5]).rstrip('.') + '.')
        else:
            for f in features:
                parts.append(f.rstrip('.') + '.')

    # Supplement with chat snippets
    if chat_data:
        snippets = chat_data.get('snippets', [])
        existing_text = ' '.join(parts).lower()
        for snippet in snippets:
            if _overlap_ratio(snippet, existing_text) < 0.4:
                trimmed = snippet[:600]
                if len(snippet) > 600:
                    last_period = trimmed.rfind('.')
                    if last_period > 300:
                        trimmed = trimmed[:last_period + 1]
                parts.append(trimmed)

    if not parts:
        return 'Status file exists but no detailed description available yet.'

    return ' '.join(parts)


def build_project_timeline(project, chat_data=None):
    """Merge progress log entries with chat-sourced dated entries into one timeline.

    Returns entries sorted newest-first.
    """
    timeline = []

    # Add progress log entries
    for entry in project.get('progress_log', []):
        timeline.append(entry.copy())

    # Add git commits
    for entry in project.get('git_commits', []):
        timeline.append(entry.copy())

    # Add chat-sourced entries
    if chat_data:
        for entry in chat_data.get('timeline_entries', []):
            # Check for redundancy against existing timeline
            is_redundant = any(
                entry['date'] == existing['date'] and
                _overlap_ratio(entry['text'], existing['text']) > 0.4
                for existing in timeline
            )
            if not is_redundant:
                timeline.append(entry.copy())

    # Sort by date descending (newest first)
    def sort_key(e):
        try:
            return datetime.strptime(e['date'], '%Y-%m-%d')
        except (ValueError, TypeError):
            return datetime.min

    timeline.sort(key=sort_key, reverse=True)

    return timeline


def build_open_threads(project):
    """Collect all unfinished items into a single list of open threads.

    Sources: blockers, open questions, not working, next steps.
    """
    threads = []

    # Blockers are highest priority
    for b in project.get('blockers', []):
        threads.append(('Blocker', b))

    # Open design questions
    for q in project.get('open_questions', []):
        threads.append(('Open Question', q))

    # Things not working / not built yet
    for nw in project.get('not_working', [])[:3]:
        threads.append(('Not Yet Built', nw))

    # Next steps (what was left to do)
    for ns in project.get('next_steps', []):
        threads.append(('Next Step', ns))

    return threads


# =============================================================================
# LOAD AND ASSEMBLE
# =============================================================================

def load_projects(scan_paths=None, chat_history_path=None, verbose=False):
    """Load all projects, merge with chat history, build timelines."""
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

    # Load chat history
    chat_project_data = {}
    if chat_history_path:
        print(f"Loading chat history from: {chat_history_path}")
        chat_files = load_chat_files(chat_history_path)
        print(f"  Loaded {len(chat_files)} chat files")
        if chat_files:
            chat_project_data = match_chat_to_projects(chat_files, all_projects, verbose=verbose)
            print(f"  Matched chat context to {len(chat_project_data)} projects")

    # Build narratives, timelines, and open threads
    for project in all_projects:
        name = project.get('name', '')
        chat_data = chat_project_data.get(name)

        project['narrative'] = build_project_narrative(project, chat_data)
        project['timeline'] = build_project_timeline(project, chat_data)
        project['open_threads'] = build_open_threads(project)

        if verbose:
            print(f"\n{project['name']}:")
            print(f"  Category: {project['category_group']}")
            print(f"  Timeline entries: {len(project['timeline'])}")
            print(f"  Open threads: {len(project['open_threads'])}")
            has_chat = name in chat_project_data
            print(f"  Chat context: {'Yes' if has_chat else 'No'}")

    all_projects.sort(key=lambda x: x['progress'], reverse=True)
    return all_projects


# =============================================================================
# PDF GENERATION
# =============================================================================

def _render_project_block(p, styles_dict):
    """Build the PDF elements for a single project."""
    elements = []

    progress = p.get('progress', 0)
    status = p.get('status', '')
    name = p.get('name', 'Unknown')
    last_worked = p.get('last_worked', '')
    last_synced = p.get('last_synced', '')

    # --- Project Header ---
    detail_parts = []
    if progress > 0:
        detail_parts.append(f"{progress}%")
    if status:
        detail_parts.append(status)
    if detail_parts:
        header_text = f"{name} — {' | '.join(detail_parts)}"
    else:
        header_text = name

    elements.append(Paragraph(header_text, styles_dict['project_header']))

    # Last active / last synced subline
    meta_parts = []
    if last_worked:
        meta_parts.append(f"Last active: {last_worked}")
    if last_synced:
        meta_parts.append(f"Last synced to Claude.ai: {last_synced}")
    if meta_parts:
        elements.append(Paragraph(' | '.join(meta_parts), styles_dict['meta']))

    # --- Summary Narrative ---
    narrative = p.get('narrative', 'No description available.')
    elements.append(Paragraph(narrative, styles_dict['narrative']))

    # --- Recent Activity Timeline ---
    timeline = p.get('timeline', [])
    if timeline:
        elements.append(Spacer(1, 4))
        elements.append(Paragraph('Recent Activity:', styles_dict['section_label']))
        for entry in timeline[:5]:  # Show last 5 entries
            date_str = entry.get('date', '?')
            source = entry.get('source', '')
            text = entry.get('text', '')

            # Format: "Feb 4 (Claude.ai Chat) — Did the thing..."
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d')
                display_date = dt.strftime('%b %d')
            except (ValueError, TypeError):
                display_date = date_str

            source_tag = f' ({source})' if source else ''
            line = f"<b>{display_date}</b>{source_tag} — {text}"
            elements.append(Paragraph(line, styles_dict['timeline_entry']))

    # --- Open Threads ---
    open_threads = p.get('open_threads', [])
    if open_threads:
        elements.append(Spacer(1, 4))
        elements.append(Paragraph('Open Threads:', styles_dict['section_label']))
        for thread_type, thread_text in open_threads[:6]:  # Cap at 6
            # Color-code by type
            if thread_type == 'Blocker':
                tag = '<font color="#E74C3C">[Blocker]</font>'
            elif thread_type == 'Open Question':
                tag = '<font color="#E67E22">[Question]</font>'
            elif thread_type == 'Next Step':
                tag = '<font color="#3498DB">[Next]</font>'
            else:
                tag = f'<font color="#7F8C8D">[{thread_type}]</font>'

            # Trim long text
            display_text = thread_text[:120]
            if len(thread_text) > 120:
                display_text += '...'

            elements.append(Paragraph(f"{tag} {display_text}", styles_dict['thread_entry']))

    return elements


def create_pdf(output_path, all_projects):
    """Generate the full portfolio PDF with temporal tracking."""
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=0.6*inch,
        leftMargin=0.6*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch
    )

    styles = getSampleStyleSheet()

    s = {}  # our custom styles dict

    s['title'] = ParagraphStyle(
        'PortfolioTitle', parent=styles['Heading1'],
        fontSize=18, textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=2, fontName='Helvetica-Bold', alignment=TA_CENTER
    )
    s['subtitle'] = ParagraphStyle(
        'PortfolioSubtitle', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor('#555555'),
        alignment=TA_CENTER, spaceAfter=16
    )
    s['category'] = ParagraphStyle(
        'CategoryHeader', parent=styles['Heading2'],
        fontSize=14, textColor=colors.HexColor('#2C3E50'),
        spaceBefore=16, spaceAfter=8, fontName='Helvetica-Bold',
    )
    s['project_header'] = ParagraphStyle(
        'ProjectHeader', parent=styles['Heading3'],
        fontSize=10, textColor=colors.HexColor('#1a1a1a'),
        spaceBefore=10, spaceAfter=1, fontName='Helvetica-Bold',
    )
    s['meta'] = ParagraphStyle(
        'ProjectMeta', parent=styles['Normal'],
        fontSize=7, textColor=colors.HexColor('#888888'),
        spaceAfter=4, fontName='Helvetica-Oblique',
    )
    s['narrative'] = ParagraphStyle(
        'Narrative', parent=styles['Normal'],
        fontSize=9, textColor=colors.HexColor('#333333'),
        leading=13, spaceAfter=4, fontName='Helvetica',
    )
    s['section_label'] = ParagraphStyle(
        'SectionLabel', parent=styles['Normal'],
        fontSize=8, textColor=colors.HexColor('#2C3E50'),
        spaceAfter=2, fontName='Helvetica-Bold',
    )
    s['timeline_entry'] = ParagraphStyle(
        'TimelineEntry', parent=styles['Normal'],
        fontSize=7.5, textColor=colors.HexColor('#444444'),
        leading=10, leftIndent=8, spaceAfter=2, fontName='Helvetica',
    )
    s['thread_entry'] = ParagraphStyle(
        'ThreadEntry', parent=styles['Normal'],
        fontSize=7.5, textColor=colors.HexColor('#444444'),
        leading=10, leftIndent=8, spaceAfter=2, fontName='Helvetica',
    )
    s['footer'] = ParagraphStyle(
        'Footer', parent=styles['Normal'],
        fontSize=8, textColor=colors.HexColor('#999999'),
        alignment=TA_CENTER, spaceBefore=20
    )
    s['cross_project_header'] = ParagraphStyle(
        'CrossProjectHeader', parent=styles['Heading2'],
        fontSize=13, textColor=colors.HexColor('#2C3E50'),
        spaceBefore=12, spaceAfter=6, fontName='Helvetica-Bold',
    )
    s['cross_project_name'] = ParagraphStyle(
        'CrossProjectName', parent=styles['Normal'],
        fontSize=9, textColor=colors.HexColor('#1a1a1a'),
        spaceBefore=6, spaceAfter=2, fontName='Helvetica-Bold',
    )

    elements = []

    # === HEADER ===
    now = datetime.now()
    date_str = now.strftime('%B %d, %Y')
    total_projects = len(all_projects)

    cat_counts = {}
    for p in all_projects:
        cat = p.get('category_group', 'Personal')
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    cat_parts = [cat for cat in CATEGORY_ORDER if cat in cat_counts]
    if len(cat_parts) > 1:
        cat_summary = ', '.join(cat_parts[:-1]) + ' &amp; ' + cat_parts[-1]
    elif cat_parts:
        cat_summary = cat_parts[0]
    else:
        cat_summary = ''

    elements.append(Paragraph('Chris Treadaway — Project Portfolio Status', s['title']))
    elements.append(Paragraph(
        f'{date_str} | {total_projects} Projects Across {cat_summary}',
        s['subtitle']
    ))

    # === PROJECTS BY CATEGORY ===
    grouped = {}
    for p in all_projects:
        cat = p.get('category_group', 'Personal')
        grouped.setdefault(cat, []).append(p)

    for cat in grouped:
        grouped[cat].sort(key=lambda x: x['progress'], reverse=True)

    rendered_cats = set()

    for cat in CATEGORY_ORDER:
        if cat not in grouped:
            continue

        projects = grouped[cat]

        if cat in ('Infrastructure', 'Personal'):
            if cat == 'Personal':
                continue  # merged with Infrastructure
            cat_label = 'Infrastructure &amp; Personal Projects'
            if 'Personal' in grouped:
                projects = projects + grouped['Personal']
            rendered_cats.add('Infrastructure')
            rendered_cats.add('Personal')
        else:
            cat_label = f'{cat} Projects'
            rendered_cats.add(cat)

        elements.append(Paragraph(cat_label, s['category']))

        for p in projects:
            project_elements = _render_project_block(p, s)
            elements.append(KeepTogether(project_elements))

    # Handle any categories not in CATEGORY_ORDER
    for cat in grouped:
        if cat not in rendered_cats:
            elements.append(Paragraph(f'{cat} Projects', s['category']))
            for p in grouped[cat]:
                project_elements = _render_project_block(p, s)
                elements.append(KeepTogether(project_elements))

    # === CROSS-PROJECT: WHAT'S LEFT UNFINISHED ===
    projects_with_threads = [(p['name'], p['open_threads'])
                              for p in all_projects if p.get('open_threads')]

    if projects_with_threads:
        elements.append(Spacer(1, 0.15*inch))
        elements.append(HRFlowable(width="100%", thickness=1,
                                    color=colors.HexColor('#BDC3C7'),
                                    spaceBefore=8, spaceAfter=8))
        elements.append(Paragraph(
            "What's Left Unfinished Across All Projects",
            s['cross_project_header']
        ))

        for proj_name, threads in projects_with_threads:
            elements.append(Paragraph(proj_name, s['cross_project_name']))
            for thread_type, thread_text in threads[:4]:
                if thread_type == 'Blocker':
                    tag = '<font color="#E74C3C">[Blocker]</font>'
                elif thread_type == 'Open Question':
                    tag = '<font color="#E67E22">[Question]</font>'
                elif thread_type == 'Next Step':
                    tag = '<font color="#3498DB">[Next]</font>'
                else:
                    tag = f'<font color="#7F8C8D">[{thread_type}]</font>'

                display_text = thread_text[:100]
                if len(thread_text) > 100:
                    display_text += '...'
                elements.append(Paragraph(f"{tag} {display_text}", s['thread_entry']))

    # Footer
    elements.append(Spacer(1, 0.3*inch))
    elements.append(Paragraph('If this tool saves you time: Venmo @ctreada', s['footer']))

    doc.build(elements)
    print(f"PDF generated: {output_path}")
    print(f"  {total_projects} projects across {len(grouped)} categories")
    total_timeline = sum(len(p.get('timeline', [])) for p in all_projects)
    total_threads = sum(len(p.get('open_threads', [])) for p in all_projects)
    print(f"  {total_timeline} timeline entries, {total_threads} open threads")


# =============================================================================
# MAIN
# =============================================================================

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
