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
import json
import os
import re
import sys
import zipfile
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
# STATUS LINE - Non-blocking progress display
# =============================================================================

class StatusLine:
    """Displays a single updating status line at the top of output."""

    def __init__(self, enabled=True):
        self.enabled = enabled and sys.stdout.isatty()
        self._last_len = 0

    def update(self, message):
        """Update the status line in-place."""
        if not self.enabled:
            return
        # Clear previous line, write new one
        clear = '\r' + ' ' * self._last_len + '\r'
        line = f"\033[36m⟳ {message}\033[0m"
        sys.stdout.write(clear + line)
        sys.stdout.flush()
        self._last_len = len(message) + 4  # account for prefix

    def done(self, message=None):
        """Clear status line and optionally print a final message."""
        if self.enabled:
            sys.stdout.write('\r' + ' ' * self._last_len + '\r')
            sys.stdout.flush()
        if message:
            print(message)

status = StatusLine()


# =============================================================================
# CONFIG & API KEY MANAGEMENT
# =============================================================================

CONFIG_PATH = os.path.expanduser('~/.claudesync/config.json')


def load_config():
    """Load config from ~/.claudesync/config.json."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_config(config):
    """Save config to ~/.claudesync/config.json."""
    config_dir = os.path.dirname(CONFIG_PATH)
    os.makedirs(config_dir, exist_ok=True)
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)


def get_api_key(config=None):
    """Get Claude API key from config, env, or prompt the user."""
    if config is None:
        config = load_config()

    # 1. Check config file
    key = config.get('anthropic_api_key', '')
    if key:
        return key

    # 2. Check environment variable
    key = os.environ.get('ANTHROPIC_API_KEY', '')
    if key:
        return key

    # 3. Prompt the user
    if sys.stdout.isatty():
        print("\n\033[33m⚠  No Claude API key found.\033[0m")
        print("An API key is needed for AI-powered project state assessment.")
        print("Get one at: https://console.anthropic.com/settings/keys\n")
        key = input("Enter your Anthropic API key (or press Enter to skip): ").strip()
        if key:
            config['anthropic_api_key'] = key
            save_config(config)
            print("\033[32m✓ API key saved to ~/.claudesync/config.json\033[0m\n")
            return key
        else:
            print("Skipping AI state assessment. You can set it later with:")
            print("  export ANTHROPIC_API_KEY=sk-ant-...")
            print(f"  or add it to {CONFIG_PATH}\n")

    return None


# =============================================================================
# DEV STATE DEFINITIONS
# =============================================================================

# Default development states with color codes
DEV_STATES = {
    'test': {
        'label': 'Test',
        'description': 'Push with no evidence of testing',
        'color': '#E67E22',    # Orange
        'pdf_color': '#E67E22',
    },
    'refine': {
        'label': 'Refine',
        'description': 'Chat abandoned — user satisfied or riffing on features',
        'color': '#3498DB',    # Blue
        'pdf_color': '#3498DB',
    },
    'continue': {
        'label': 'Continue',
        'description': 'Tests ongoing, not fully resolved',
        'color': '#E74C3C',    # Red
        'pdf_color': '#E74C3C',
    },
}


def load_custom_states():
    """Load user-defined custom dev states from config."""
    config = load_config()
    custom = config.get('custom_dev_states', {})
    merged = dict(DEV_STATES)
    merged.update(custom)
    return merged


def get_dev_state_color(state_key):
    """Get the color for a dev state."""
    all_states = load_custom_states()
    state = all_states.get(state_key, {})
    return state.get('color', '#95A5A6')  # Gray fallback


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


# =============================================================================
# CHAT HISTORY PROCESSING - Claude.ai export (conversations.json in ZIP/DMS)
# =============================================================================

def load_chat_files(chat_path):
    """Load conversations from a Claude.ai export (ZIP/DMS with conversations.json)
    or a directory/file of text-based chat exports.

    Claude.ai exports are .dms files (renamed ZIPs) containing conversations.json:
    a JSON array of conversation objects with uuid, name, created_at, updated_at,
    and chat_messages[].

    Returns list of dicts: [{'filename': str, 'content': str, 'date': datetime|None}, ...]
    """
    chat_files = []
    if chat_path is None:
        return chat_files

    chat_path = os.path.expanduser(chat_path)

    if not os.path.exists(chat_path):
        return chat_files

    # Try as ZIP/DMS archive first
    if zipfile.is_zipfile(chat_path):
        chat_files = _load_from_zip(chat_path)
    elif os.path.isdir(chat_path):
        # Walk directory for text files
        for root, _dirs, files in os.walk(chat_path):
            for fname in files:
                if fname.endswith(('.md', '.txt', '.json')):
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, 'r', errors='replace') as f:
                            text = f.read()
                        if fname == 'conversations.json':
                            chat_files.extend(_parse_conversations_json(text))
                        else:
                            mod_time = datetime.fromtimestamp(os.path.getmtime(fpath))
                            chat_files.append({
                                'filename': fname,
                                'content': text,
                                'date': mod_time,
                            })
                    except Exception:
                        continue
    elif os.path.isfile(chat_path):
        try:
            with open(chat_path, 'r', errors='replace') as f:
                text = f.read()
            if chat_path.endswith('.json'):
                chat_files.extend(_parse_conversations_json(text))
            else:
                mod_time = datetime.fromtimestamp(os.path.getmtime(chat_path))
                chat_files.append({
                    'filename': os.path.basename(chat_path),
                    'content': text,
                    'date': mod_time,
                })
        except Exception:
            pass

    return chat_files


def _load_from_zip(zip_path):
    """Extract conversations from a ZIP/DMS archive."""
    chat_files = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Check for conversations.json (Claude.ai native export)
            names = zf.namelist()
            conversations_files = [n for n in names
                                   if os.path.basename(n) == 'conversations.json']
            if conversations_files:
                for cf in conversations_files:
                    try:
                        raw = zf.read(cf).decode('utf-8', errors='replace')
                        chat_files.extend(_parse_conversations_json(raw))
                    except Exception:
                        continue
            else:
                # Fallback: treat individual files as chat exports
                for name in names:
                    if name.endswith(('.md', '.txt', '.json')):
                        try:
                            raw = zf.read(name).decode('utf-8', errors='replace')
                            info = zf.getinfo(name)
                            mod_time = datetime(*info.date_time) if info.date_time else None
                            chat_files.append({
                                'filename': os.path.basename(name),
                                'content': raw,
                                'date': mod_time,
                            })
                        except Exception:
                            continue
    except Exception:
        pass
    return chat_files


def _parse_conversations_json(json_text):
    """Parse a Claude.ai conversations.json export.

    Format: JSON array of conversation objects with:
      - uuid, name, created_at, updated_at
      - chat_messages[]: each with text, sender, created_at, content[]

    Returns list of chat_file dicts compatible with our pipeline.
    """
    chat_files = []
    try:
        data = json.loads(json_text)
    except (json.JSONDecodeError, TypeError):
        return chat_files

    if not isinstance(data, list):
        return chat_files

    for conv in data:
        if not isinstance(conv, dict):
            continue

        # Extract conversation metadata
        conv_name = conv.get('name', '') or ''
        conv_uuid = conv.get('uuid', '')
        created_at = conv.get('created_at', '')
        updated_at = conv.get('updated_at', '')

        # Parse date - prefer updated_at for "when was this worked on"
        conv_date = None
        for date_str in [updated_at, created_at]:
            if date_str:
                try:
                    conv_date = datetime.fromisoformat(
                        date_str.replace('Z', '+00:00')
                    )
                    break
                except (ValueError, TypeError):
                    continue

        # Build combined text content from all messages
        messages = conv.get('chat_messages', [])
        if not messages:
            continue

        text_parts = []
        # Add conversation title
        if conv_name:
            text_parts.append(f"# {conv_name}\n")

        for msg in messages:
            if not isinstance(msg, dict):
                continue
            sender = msg.get('sender', '')
            # Get text from top-level text field
            msg_text = msg.get('text', '')
            # Also try content blocks
            if not msg_text:
                content_blocks = msg.get('content', [])
                if isinstance(content_blocks, list):
                    for block in content_blocks:
                        if isinstance(block, dict) and block.get('type') == 'text':
                            msg_text = block.get('text', '')
                            break

            if msg_text:
                label = 'Human' if sender == 'human' else 'Assistant'
                text_parts.append(f"{label}: {msg_text}")

        if not text_parts:
            continue

        combined_text = '\n\n'.join(text_parts)

        # Build filename from title or UUID
        if conv_name:
            safe_name = re.sub(r'[^\w\s-]', '', conv_name)[:60].strip()
            filename = safe_name or conv_uuid[:12]
        else:
            filename = conv_uuid[:12] if conv_uuid else 'untitled'

        chat_files.append({
            'filename': filename,
            'content': combined_text,
            'date': conv_date,
            'conversation_name': conv_name,
            'uuid': conv_uuid,
        })

    return chat_files


def _build_search_terms(project_name):
    """Build fuzzy search patterns from a project name."""
    name_lower = project_name.lower().strip()
    terms = set()
    terms.add(name_lower)

    # Without version suffix
    no_version = re.sub(r'\s*v\d+(\.\d+)*\s*$', '', name_lower).strip()
    if no_version and len(no_version) > 3:
        terms.add(no_version)

    # No spaces
    squashed = name_lower.replace(' ', '')
    if len(squashed) > 5:
        terms.add(squashed)

    # First two significant words
    words = [w for w in name_lower.split()
             if len(w) > 2 and w not in ('the', 'and', 'for', 'app', 'project')]
    if len(words) >= 2:
        terms.add(words[0] + ' ' + words[1])

    # Longest significant word (if long enough)
    if words:
        longest = max(words, key=len)
        if len(longest) >= 8:
            terms.add(longest)

    return list(terms)


def _split_into_paragraphs(text):
    """Split chat text into meaningful paragraphs, filtering out code blocks."""
    # Remove speaker labels
    cleaned = re.sub(r'^(Human|Assistant|User|Claude|System)\s*:', '', text, flags=re.MULTILINE)
    # Split on double newlines or horizontal rules
    raw_blocks = re.split(r'\n\s*\n|\n---+\n', cleaned)

    paragraphs = []
    for block in raw_blocks:
        block = block.strip()
        if not block or block.startswith('```') or len(block) < 30:
            continue

        # Skip code-heavy blocks
        code_indicators = ('$', '>', '#!', 'import ', 'from ', 'def ', 'class ',
                           'function ', 'const ', 'let ', 'var ', 'return ', '{', '}')
        code_line_count = sum(1 for line in block.split('\n')
                              if line.strip().startswith(code_indicators))
        total_lines = len(block.split('\n'))
        if total_lines > 1 and code_line_count / total_lines > 0.6:
            continue

        # Clean formatting
        clean = block.replace('**', '').replace('`', '')
        clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', clean)  # [text](url) -> text
        clean = re.sub(r'^#+\s+', '', clean, flags=re.MULTILINE)  # Remove headers
        clean = re.sub(r'\n+', ' ', clean).strip()

        if len(clean) >= 30:
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


def match_chat_to_projects(chat_files, projects, verbose=False, progress_callback=None):
    """Match chat history to projects using fuzzy name matching.

    Returns:
        tuple: (project_chat_data, chat_stats)
            project_chat_data: {project_name: {snippets: [...], timeline_entries: [...],
                                                conversation_entries: [...]}}
            chat_stats: {total_files, total_conversations, matched_projects,
                         unmatched_files, unmatched_chats: [...]}
    """
    def _progress(detail=''):
        if progress_callback:
            progress_callback('matching', detail)

    project_chat_data = {}
    matched_filenames = set()  # Track which chat files matched any project
    total_conversations_matched = 0

    for pi, project in enumerate(projects):
        name = project.get('name', '')
        if not name:
            continue

        _progress(f'Matching chats to {name} ({pi + 1}/{len(projects)})...')
        search_terms = _build_search_terms(name)
        scored_paragraphs = []  # (score, text, date, filename)
        matched_conversations = {}  # filename -> {date, paragraph_count}

        for chat in chat_files:
            paragraphs = _split_into_paragraphs(chat['content'])
            chat_date = chat.get('date')
            chat_filename = chat.get('filename', '')
            conv_name = chat.get('conversation_name', '')

            # Also check if the conversation title itself mentions the project
            title_bonus = 0
            if conv_name:
                title_lower = conv_name.lower()
                for term in search_terms:
                    if term in title_lower:
                        title_bonus = 50  # Strong signal from title match
                        break

            for para in paragraphs:
                para_lower = para.lower()
                score = title_bonus  # Start with title bonus if any

                for term in search_terms:
                    count = para_lower.count(term)
                    if count > 0:
                        score += count * len(term)

                if score > 0:
                    # Bonuses for quality
                    length_bonus = min(len(para), 500) / 100
                    descriptive_words = ['project', 'build', 'feature', 'implement',
                                         'design', 'status', 'progress', 'complete',
                                         'working', 'develop', 'launch', 'deploy']
                    desc_bonus = sum(1 for w in descriptive_words if w in para_lower)
                    total_score = score + length_bonus + desc_bonus
                    scored_paragraphs.append((total_score, para, chat_date, chat_filename))

                    # Track per-conversation matching
                    if chat_filename not in matched_conversations:
                        matched_conversations[chat_filename] = {
                            'date': chat_date,
                            'paragraph_count': 0,
                        }
                    matched_conversations[chat_filename]['paragraph_count'] += 1

        scored_paragraphs.sort(key=lambda x: x[0], reverse=True)

        # Best snippets (deduped)
        best_snippets = []
        timeline_entries = []

        for _score, para, chat_date, chat_filename in scored_paragraphs:
            is_redundant = any(_overlap_ratio(para, existing) > 0.65
                               for existing in best_snippets)
            if not is_redundant:
                best_snippets.append(para)

                # Create dated timeline entry
                if chat_date:
                    date_str = chat_date.strftime('%Y-%m-%d')
                else:
                    date_str = ''

                summary_line = para[:150]
                if len(para) > 150:
                    last_period = summary_line.rfind('.')
                    if last_period > 80:
                        summary_line = summary_line[:last_period + 1]
                    else:
                        summary_line = summary_line + '...'

                timeline_entries.append({
                    'date': date_str,
                    'source': 'Claude.ai Chat',
                    'text': summary_line,
                })

                if len(best_snippets) >= 50:
                    break

        # Build per-conversation entries (one per matched conversation)
        conversation_entries = []
        for fname, info in matched_conversations.items():
            matched_filenames.add(fname)
            if info.get('date'):
                date_str = info['date'].strftime('%Y-%m-%d')
            else:
                date_str = ''
            conversation_entries.append({
                'date': date_str,
                'source': 'Claude.ai Chat',
                'text': f"Chat conversation ({info['paragraph_count']} relevant sections)",
            })

        if best_snippets or conversation_entries:
            project_chat_data[name] = {
                'snippets': best_snippets,
                'timeline_entries': timeline_entries,
                'conversation_entries': conversation_entries,
            }
            total_conversations_matched += len(matched_conversations)

            if verbose:
                print(f"  Chat match for '{name}': {len(scored_paragraphs)} candidates, "
                      f"kept {len(best_snippets)} snippets, "
                      f"{len(matched_conversations)} conversations")

    # Build unmatched list
    unmatched_chats = []
    for chat in chat_files:
        fname = chat.get('filename', '')
        if fname not in matched_filenames:
            # Build excerpt: strip code blocks, remove labels, take first 300 chars
            raw = chat.get('content', '')
            excerpt = re.sub(r'```[\s\S]*?```', '', raw)
            excerpt = re.sub(r'^(Human|Assistant|User|Claude|System)\s*:',
                             '', excerpt, flags=re.MULTILINE)
            excerpt = excerpt.strip()[:300]

            chat_date = chat.get('date')
            date_str = chat_date.strftime('%Y-%m-%d') if chat_date else ''

            unmatched_chats.append({
                'filename': fname,
                'date': date_str,
                'excerpt': excerpt,
            })

    chat_stats = {
        'total_files': len(chat_files),
        'total_conversations': total_conversations_matched,
        'matched_projects': len(project_chat_data),
        'unmatched_files': len(unmatched_chats),
        'unmatched_chats': unmatched_chats,
    }

    return project_chat_data, chat_stats


# =============================================================================
# PROJECT STATUS FILE SCANNING
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

        status.update(f"Scanning {base_path} for projects...")

        for root, dirs, files in os.walk(base_path):
            # Calculate depth
            depth = root.replace(base_path, '').count(os.sep)
            if depth >= max_depth:
                dirs[:] = []  # Don't go deeper
                continue

            # Skip certain directories
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

            if 'PROJECT_STATUS.md' in files:
                project_name = os.path.basename(root)
                status.update(f"Found project: {project_name}")
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
                placeholder_starts = ['describe', 'list ', 'add ', 'none']
                placeholder_contains = ['nothing yet', 'none yet', 'tbd', 'todo',
                                        'initial project', 'project structure']
                item_lower = item.lower()
                is_placeholder = (
                    item.startswith('(') or
                    any(item_lower.startswith(pw) for pw in placeholder_starts) or
                    any(pw in item_lower for pw in placeholder_contains) or
                    len(item) < 10
                )
                if item and not is_placeholder:
                    items.append(item)
                    if len(items) >= max_items:
                        break
    return items


COMMIT_SKIP_PATTERNS = [
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


def get_recent_commits(project_dir, max_commits=5):
    """Get recent meaningful commit messages from git log."""
    import subprocess

    try:
        # Scan ALL commits across ALL branches to find meaningful ones
        result = subprocess.run(
            ['git', 'log', '--all', '--pretty=format:%s'],
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
                is_garbage = any(pattern in line_lower for pattern in COMMIT_SKIP_PATTERNS)

                if not is_garbage:
                    commits.append(line)
                    if len(commits) >= max_commits:
                        break
            return commits
    except Exception:
        pass
    return []


def get_recent_commits_with_dates(project_dir, max_commits=20):
    """Get recent meaningful commits with dates from git log.

    Returns list of (date_str, message) tuples where date_str is YYYY-MM-DD.
    """
    import subprocess

    try:
        result = subprocess.run(
            ['git', 'log', '--all', '--pretty=format:%aI%n%s'],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            commits = []
            i = 0
            while i < len(lines) - 1:
                date_line = lines[i].strip()
                msg_line = lines[i + 1].strip() if i + 1 < len(lines) else ''
                i += 2

                if not msg_line or len(msg_line) < 15:
                    continue

                msg_lower = msg_line.lower()
                is_garbage = any(p in msg_lower for p in COMMIT_SKIP_PATTERNS)
                if is_garbage:
                    continue

                # Parse ISO date to YYYY-MM-DD
                try:
                    dt = datetime.fromisoformat(date_line)
                    date_str = dt.strftime('%Y-%m-%d')
                except (ValueError, TypeError):
                    date_str = ''

                commits.append((date_str, msg_line))
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

        status.update(f"Parsing: {project['name']}")

        # Extract from metadata table
        patterns = {
            'repo': r'\*\*Repository\*\*\s*\|\s*(.+)',
            'category': r'\*\*Category\*\*\s*\|\s*(.+)',
            'progress': r'\*\*Progress\*\*\s*\|\s*(\d+)',
            'status': r'\*\*Status\*\*\s*\|\s*(.+)',
            'has_repo': r'\*\*Has GitHub Repo\*\*\s*\|\s*(.+)',
            'dev_state': r'\*\*Dev State\*\*\s*\|\s*(.+)',
            'last_worked': r'\*\*Last Worked\*\*\s*\|\s*(.+)',
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
        project.setdefault('dev_state', '')

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
        status.update(f"Reading commits: {project['name']}")
        project['recent_commits'] = get_recent_commits(project['project_path'], 5)

        # Set category_group (alias used by web dashboard)
        project['category_group'] = project.get('category', 'Personal')

        # Set last_worked default
        project.setdefault('last_worked', '')

        # ---- Extract structured sections for web dashboard ----

        # What's Not Working
        project['not_working'] = extract_list_items(content, r"### What's Not Working", 20)

        # Blockers
        project['blockers'] = extract_list_items(content, r"### Blockers", 20)

        # Open Questions (from "Still stuck on:" entries across all log dates)
        open_questions = []
        for match in re.finditer(r'\*\*Still stuck on:\*\*\s*\n((?:[-*]\s+.+\n?)+)', content):
            for line in match.group(1).split('\n'):
                line = line.strip().lstrip('-* ').strip()
                if line and len(line) >= 10:
                    open_questions.append(line)
        project['open_questions'] = open_questions

        # Next Steps (from "Next time:" entries across all log dates)
        next_steps = []
        for match in re.finditer(r'\*\*Next time:\*\*\s*\n((?:[-*]\s+.+\n?)+)', content):
            for line in match.group(1).split('\n'):
                line = line.strip().lstrip('-* ').strip()
                if line and len(line) >= 10:
                    next_steps.append(line)
        project['next_steps'] = next_steps

        # Open threads: combined list of (type, text) tuples
        open_threads = []
        for b in project['blockers']:
            open_threads.append(('Blocker', b))
        for q in open_questions:
            open_threads.append(('Open Question', q))
        for ns in next_steps:
            open_threads.append(('Next Step', ns))
        for nw in project['not_working']:
            open_threads.append(('Not Yet Built', nw))
        project['open_threads'] = open_threads

        # ---- Build timeline from progress log dates ----
        timeline = []
        # Find all ### YYYY-MM-DD headings and their content
        log_section = re.search(r'## Progress Log\s*\n(.*)', content, re.DOTALL)
        if log_section:
            log_text = log_section.group(1)
            # Match each dated entry
            date_entries = re.finditer(
                r'### (\d{4}-\d{2}-\d{2})\s*\n(.*?)(?=### \d{4}-\d{2}-\d{2}|\Z)',
                log_text, re.DOTALL
            )
            for entry in date_entries:
                log_date = entry.group(1)
                log_body = entry.group(2).strip()
                # Extract "What was built" as summary
                built_match = re.search(r'\*\*What was built:\*\*\s*\n((?:[-*]\s+.+\n?)+)', log_body)
                if built_match:
                    for line in built_match.group(1).split('\n'):
                        line = line.strip().lstrip('-* ').strip()
                        if line and len(line) >= 10:
                            timeline.append({
                                'date': log_date,
                                'source': 'Progress Log',
                                'text': line,
                            })
                # Also extract "What was figured out" entries
                figured_match = re.search(r'\*\*What was figured out:\*\*\s*\n((?:[-*]\s+.+\n?)+)', log_body)
                if figured_match:
                    for line in figured_match.group(1).split('\n'):
                        line = line.strip().lstrip('-* ').strip()
                        if line and len(line) >= 10:
                            timeline.append({
                                'date': log_date,
                                'source': 'Progress Log',
                                'text': line,
                            })

        # Add git commits with dates to timeline
        commits_with_dates = get_recent_commits_with_dates(project['project_path'], 20)
        for cdate, cmsg in commits_with_dates:
            if cdate:
                timeline.append({
                    'date': cdate,
                    'source': 'Git Commit',
                    'text': cmsg,
                })

        # Sort timeline by date descending (newest first)
        timeline.sort(key=lambda e: e.get('date', ''), reverse=True)
        project['timeline'] = timeline

        # Update last_worked from actual activity if not set in metadata
        if not project['last_worked'] and timeline:
            dates = [e['date'] for e in timeline if e.get('date')]
            if dates:
                project['last_worked'] = max(dates)

        # Store raw content for AI assessment
        project['_raw_content'] = content

        return project

    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return None


def load_projects(scan_paths=None, verbose=False, chat_history_path=None,
                   progress_callback=None, flat=False):
    """Load all projects from PROJECT_STATUS.md files.

    Args:
        scan_paths: List of paths to scan for PROJECT_STATUS.md files.
        verbose: Print verbose output.
        chat_history_path: Path to chat history ZIP (for web dashboard).
        progress_callback: Callable(step, detail) for progress updates.
        flat: If True, return a flat list of projects (for web dashboard).
              If False, return {'with_repos': [...], 'without_repos': [...]}.

    Returns:
        Flat list of project dicts if flat=True, else dict with with_repos/without_repos.
    """
    def _progress(step, detail=''):
        if progress_callback:
            progress_callback(step, detail)

    _progress('scanning', 'Scanning for projects...')
    status_files = find_project_status_files(scan_paths)

    status.done()
    if verbose:
        print(f"\nFound {len(status_files)} PROJECT_STATUS.md files:")
        for sf in status_files:
            print(f"  - {sf}")

    all_projects = []
    with_repos = []
    without_repos = []

    total = len(status_files)
    for i, sf in enumerate(status_files, 1):
        _progress('parsing', f'Parsing project {i}/{total}...')
        status.update(f"Loading project {i}/{total}: {os.path.basename(os.path.dirname(sf))}")
        project = parse_project_status(sf)
        if project:
            if verbose:
                status.done()
                features = project.get('features', [])
                commits = project.get('recent_commits', [])
                print(f"\n{project['name']}:")
                print(f"  Features: {len(features)}")
                for f in features[:2]:
                    print(f"    - {f[:50]}...")
                print(f"  Commits: {len(commits)}")
                for c in commits[:2]:
                    print(f"    - {c[:50]}...")

            all_projects.append(project)
            if project['has_github_repo']:
                with_repos.append(project)
            else:
                without_repos.append(project)

    status.done()

    # ---- Chat history integration ----
    chat_stats = {}
    if chat_history_path:
        _progress('reading_chat', 'Loading chat history...')
        status.update('Loading chat history...')
        chat_files = load_chat_files(chat_history_path)
        status.done()

        if chat_files:
            _progress('matching', f'Matching {len(chat_files)} conversations to projects...')
            status.update(f'Matching {len(chat_files)} conversations to projects...')
            chat_project_data, chat_stats = match_chat_to_projects(
                chat_files, all_projects, verbose=verbose,
                progress_callback=progress_callback,
            )
            status.done()

            if verbose:
                print(f"\n  Loaded {len(chat_files)} conversations")
                print(f"  Matched to {chat_stats['matched_projects']} projects")
                print(f"  {chat_stats['unmatched_files']} unmatched")

            # Merge chat data into project timelines
            for project in all_projects:
                name = project.get('name', '')
                chat_data = chat_project_data.get(name)
                if chat_data:
                    existing_timeline = project.get('timeline', [])

                    # Add chat timeline entries (deduped against existing)
                    for entry in chat_data.get('timeline_entries', []):
                        is_redundant = any(
                            entry['date'] == e['date'] and
                            _overlap_ratio(entry['text'], e['text']) > 0.4
                            for e in existing_timeline
                        )
                        if not is_redundant:
                            existing_timeline.append(entry)

                    # Add per-conversation entries
                    for entry in chat_data.get('conversation_entries', []):
                        existing_timeline.append(entry)

                    # Re-sort timeline
                    existing_timeline.sort(
                        key=lambda e: e.get('date', ''), reverse=True
                    )
                    project['timeline'] = existing_timeline

                    # Update last_worked if chat has newer dates
                    chat_dates = [e['date'] for e in existing_timeline
                                  if e.get('date') and 'Chat' in e.get('source', '')]
                    if chat_dates:
                        newest_chat = max(chat_dates)
                        if newest_chat > project.get('last_worked', ''):
                            project['last_worked'] = newest_chat

                    # Store snippets for narrative building
                    project['_chat_snippets'] = chat_data.get('snippets', [])
        else:
            chat_stats = {
                'total_files': 0, 'total_conversations': 0,
                'matched_projects': 0, 'unmatched_files': 0,
                'unmatched_chats': [],
            }

    # Store chat_stats as function attribute so web_app can access it
    load_projects._last_chat_stats = chat_stats

    _progress('done', f'Loaded {len(all_projects)} projects')

    if flat:
        # Sort by progress descending for web dashboard
        all_projects.sort(key=lambda x: x['progress'], reverse=True)
        return all_projects

    # Sort by progress descending
    with_repos.sort(key=lambda x: x['progress'], reverse=True)
    without_repos.sort(key=lambda x: x['progress'], reverse=True)

    return {'with_repos': with_repos, 'without_repos': without_repos}


# =============================================================================
# AI-POWERED STATE ASSESSMENT
# =============================================================================

def assess_dev_state(project, api_key):
    """Use Claude API to assess which dev state a project is in."""
    try:
        import urllib.request
        import urllib.error

        name = project['name']
        commits = project.get('recent_commits', [])
        progress = project.get('progress', 0)
        current_status = project.get('status', 'Unknown')
        raw = project.get('_raw_content', '')

        # Extract progress log section for context
        log_match = re.search(r'## Progress Log\s*\n(.*)', raw, re.DOTALL)
        progress_log = log_match.group(1)[:2000] if log_match else ''

        all_states = load_custom_states()
        state_descriptions = '\n'.join(
            f'- "{key}": {s["description"]}'
            for key, s in all_states.items()
        )

        prompt = f"""Analyze this project and determine its current development state.

Project: {name}
Progress: {progress}%
Status: {current_status}
Recent commits: {json.dumps(commits[:5])}

Progress log (excerpt):
{progress_log[:1500]}

Available states:
{state_descriptions}

Based on the evidence, which single state best describes this project? Look for:
- "test": Recent pushes but no mention of tests passing, no test results in logs
- "refine": Work appears paused, user seems satisfied or moved on to feature ideas
- "continue": Active testing, unresolved bugs, ongoing test cycles

Respond with ONLY the state key (e.g. "test", "refine", or "continue"). Nothing else."""

        body = json.dumps({
            'model': 'claude-sonnet-4-20250514',
            'max_tokens': 20,
            'messages': [{'role': 'user', 'content': prompt}]
        }).encode('utf-8')

        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=body,
            headers={
                'Content-Type': 'application/json',
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
            },
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            answer = result['content'][0]['text'].strip().lower().strip('"\'')
            # Validate it's a known state
            if answer in all_states:
                return answer

    except Exception:
        pass

    return None


def assess_all_projects(projects, api_key):
    """Run AI assessment on all projects that don't have a dev_state set."""
    all_projects = projects['with_repos'] + projects['without_repos']
    needs_assessment = [p for p in all_projects if not p.get('dev_state')]

    if not needs_assessment:
        return

    total = len(needs_assessment)
    for i, project in enumerate(needs_assessment, 1):
        status.update(f"AI assessing state {i}/{total}: {project['name']}")
        state = assess_dev_state(project, api_key)
        if state:
            project['dev_state'] = state

    status.done()


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

    # Build labels with dev state indicators
    all_states = load_custom_states()
    names = []
    for p in all_projects:
        ds = p.get('dev_state', '')
        label = p['name']
        if ds and ds in all_states:
            label = f"{p['name']}  [{all_states[ds]['label']}]"
        names.append(label)

    progress = [p['progress'] for p in all_projects]
    colors_list = [get_progress_color(p) for p in progress]

    # Adjust figure height based on number of projects
    fig_height = max(3, min(8, len(names) * 0.4))
    fig, ax = plt.subplots(figsize=(6, fig_height))

    y_pos = np.arange(len(names))
    bars = ax.barh(y_pos, progress, color=colors_list, height=0.7)

    # Add dev state color dots on the left side
    for i, p in enumerate(all_projects):
        ds = p.get('dev_state', '')
        if ds:
            dot_color = get_dev_state_color(ds)
            ax.plot(-2, i, 'o', color=dot_color, markersize=6, clip_on=False)

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

    # Dev state style for colored labels
    all_states = load_custom_states()

    def dev_state_cell(project):
        """Return a colored Paragraph for the dev state."""
        ds = project.get('dev_state', '')
        if ds and ds in all_states:
            state_info = all_states[ds]
            color = state_info['color']
            label = state_info['label']
            return Paragraph(f"<font color='{color}'><b>{label}</b></font>", styles['Normal'])
        return Paragraph('<font color="#CCCCCC">—</font>', styles['Normal'])

    # Projects WITH repos
    if projects['with_repos']:
        elements.append(Paragraph('Projects with GitHub Repositories', subsection_style))
        with_repos_data = [['Project', 'Repository', 'Status', 'State', 'Progress']]
        for p in projects['with_repos']:
            with_repos_data.append([
                p['name'],
                p.get('repo', ''),
                p.get('status', ''),
                dev_state_cell(p),
                f"{p.get('progress', 0)}%"
            ])

        with_repos_table = Table(with_repos_data, colWidths=[1.3*inch, 2.2*inch, 1.0*inch, 0.8*inch, 0.8*inch])
        with_repos_table.setStyle(table_header_style)
        elements.append(with_repos_table)
        elements.append(Spacer(1, 0.15*inch))

    # Projects WITHOUT repos
    if projects['without_repos']:
        elements.append(Paragraph('Projects WITHOUT GitHub Repositories', subsection_style))
        without_repos_data = [['Project', 'Status', 'State', 'Progress', 'Category']]
        for p in projects['without_repos']:
            without_repos_data.append([
                p['name'],
                p.get('status', ''),
                dev_state_cell(p),
                f"{p.get('progress', 0)}%",
                p.get('category', 'Personal')
            ])

        without_repos_table = Table(without_repos_data, colWidths=[1.5*inch, 1.2*inch, 0.8*inch, 0.7*inch, 1.9*inch])
        without_repos_table.setStyle(table_header_style)
        elements.append(without_repos_table)

    # Footer for page 1
    elements.append(Spacer(1, 0.3*inch))
    elements.append(Paragraph('If this tool saves you time: Venmo @ctreada', footer_style))

    # ==========================================================================
    # PAGE 2+: Features Built (2-column layout)
    # ==========================================================================
    elements.append(PageBreak())

    # Page 2 Header
    elements.append(Paragraph('<b>Project Details: Recent Work</b>', title_style))
    elements.append(Spacer(1, 0.15*inch))

    # Styles for page 2
    project_name_style = ParagraphStyle(
        'ProjectName', parent=styles['Heading3'],
        fontSize=9, textColor=colors.HexColor('#2C3E50'),
        spaceBefore=4, spaceAfter=2
    )
    commit_style = ParagraphStyle(
        'Commit', parent=styles['Normal'],
        fontSize=6, textColor=colors.HexColor('#555555'),
        leftIndent=5, spaceBefore=1, spaceAfter=1
    )
    no_data_style = ParagraphStyle(
        'NoData', parent=styles['Normal'],
        fontSize=6, textColor=colors.HexColor('#999999'),
        leftIndent=5, fontName='Helvetica-Oblique'
    )

    all_projects = projects['with_repos'] + projects['without_repos']
    all_projects.sort(key=lambda x: x['name'])

    dev_state_tag_style = ParagraphStyle(
        'DevStateTag', parent=styles['Normal'],
        fontSize=6, spaceBefore=0, spaceAfter=2
    )

    def build_project_cell(p):
        """Build content for a single project cell."""
        cell_content = []
        progress = p.get('progress', 0)
        progress_color = '#2ECC71' if progress > 75 else '#3498DB' if progress >= 50 else '#F1C40F' if progress >= 25 else '#E74C3C'

        # Project name with progress
        name_line = f"<b>{p['name']}</b> <font color='{progress_color}'>({progress}%)</font>"
        cell_content.append(Paragraph(name_line, project_name_style))

        # Dev state tag
        ds = p.get('dev_state', '')
        if ds and ds in all_states:
            state_info = all_states[ds]
            sc = state_info['color']
            sl = state_info['label']
            cell_content.append(Paragraph(
                f"<font color='{sc}'>[{sl}]</font> <font color='#999999' size='5'>{state_info['description']}</font>",
                dev_state_tag_style
            ))

        commits = p.get('recent_commits', [])
        if commits:
            for commit in commits[:5]:
                display_commit = commit[:55] + '...' if len(commit) > 55 else commit
                cell_content.append(Paragraph(f"› {display_commit}", commit_style))
        else:
            cell_content.append(Paragraph('No recent work logged', no_data_style))

        return cell_content

    # Build 2-column table
    col_width = 3.7 * inch
    row_data = []

    for i in range(0, len(all_projects), 2):
        left_cell = build_project_cell(all_projects[i])
        if i + 1 < len(all_projects):
            right_cell = build_project_cell(all_projects[i + 1])
        else:
            right_cell = []

        row_data.append([left_cell, right_cell])

    # Create table with project pairs
    for row in row_data:
        row_table = Table([[row[0], row[1]]], colWidths=[col_width, col_width])
        row_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(row_table)

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
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show detailed debug output')
    parser.add_argument('--no-ai', action='store_true',
                        help='Skip AI-powered state assessment')
    parser.add_argument('--set-key', default=None, metavar='API_KEY',
                        help='Set Anthropic API key and save to config')
    args = parser.parse_args()

    # Handle --set-key
    if args.set_key:
        config = load_config()
        config['anthropic_api_key'] = args.set_key
        save_config(config)
        print("\033[32m✓ API key saved to ~/.claudesync/config.json\033[0m")
        if not args.output and not args.scan_paths:
            return  # Just setting key, no PDF generation requested

    # Load projects dynamically
    status.update("Scanning for PROJECT_STATUS.md files...")
    projects = load_projects(args.scan_paths, verbose=args.verbose)

    total = len(projects['with_repos']) + len(projects['without_repos'])
    if total == 0:
        print("\nNo PROJECT_STATUS.md files found!")
        print("Run init_project_status.py to create status files for your projects:")
        print("  python3 init_project_status.py ~/myproject --name 'My Project' --category School")
        return

    print(f"Found {total} projects")

    # AI-powered dev state assessment
    if not args.no_ai:
        config = load_config()
        api_key = get_api_key(config)
        if api_key:
            assess_all_projects(projects, api_key)
        else:
            print("Skipping AI state assessment (no API key)")
    else:
        print("Skipping AI state assessment (--no-ai)")

    # Generate PDF
    status.update("Generating PDF report...")
    if args.output is None:
        today = datetime.now().strftime('%Y-%m-%d')
        output_dir = os.path.expanduser('~/claudesync2')
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f'status_report_{today}.pdf')
    else:
        output_path = os.path.expanduser(args.output)

    status.update("Building charts and tables...")
    create_pdf(output_path, projects)
    status.done()


if __name__ == '__main__':
    main()
