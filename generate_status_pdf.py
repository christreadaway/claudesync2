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
import json
import os
import platform
import re
import subprocess
import sys
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

def _extract_conversations_from_json(text, filename, fallback_date=None):
    """Parse a JSON file that may contain multiple conversations.

    Handles Claude.ai export format (array of conversation objects)
    as well as single conversation objects.  Returns a list of
    {filename, content, date} dicts — one per conversation.
    """
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        # Not valid JSON — treat as plain text
        return [{'filename': filename, 'content': text, 'date': fallback_date}]

    conversations = []

    # Claude.ai export: top-level list of conversation objects
    if isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, dict):
                conv = _parse_single_conversation(item, i, filename, fallback_date)
                if conv:
                    conversations.append(conv)
    elif isinstance(data, dict):
        # Single conversation object, or wrapper with a list inside
        for key in ('conversations', 'chat_messages', 'data', 'items', 'results'):
            if key in data and isinstance(data[key], list):
                for i, item in enumerate(data[key]):
                    if isinstance(item, dict):
                        conv = _parse_single_conversation(item, i, filename, fallback_date)
                        if conv:
                            conversations.append(conv)
                break
        else:
            # It's a single conversation dict
            conv = _parse_single_conversation(data, 0, filename, fallback_date)
            if conv:
                conversations.append(conv)

    if not conversations:
        # Fallback: treat the raw text as one conversation
        conversations.append({'filename': filename, 'content': text, 'date': fallback_date})

    return conversations


def _parse_single_conversation(obj, index, parent_filename, fallback_date):
    """Extract a single conversation from a JSON object.

    Handles multiple Claude.ai export variants and generic chat formats.
    """
    # Build a readable name
    name = (obj.get('name') or obj.get('title') or
            obj.get('conversation_name') or obj.get('subject') or '')
    if not name:
        name = f'{os.path.splitext(parent_filename)[0]}_{index + 1}'
    # Sanitize for use as a filename-like key
    safe_name = re.sub(r'[^\w\s-]', '', name).strip()[:80] or f'conversation_{index + 1}'

    # Extract date
    conv_date = fallback_date
    for date_key in ('created_at', 'updated_at', 'date', 'timestamp', 'created', 'create_time'):
        raw = obj.get(date_key)
        if raw:
            try:
                if isinstance(raw, (int, float)):
                    conv_date = datetime.fromtimestamp(raw)
                else:
                    # Try ISO 8601 first, then common formats
                    for fmt in ('%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ',
                                '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
                        try:
                            conv_date = datetime.strptime(str(raw)[:26], fmt)
                            break
                        except ValueError:
                            continue
            except Exception:
                pass
            if conv_date != fallback_date:
                break

    # Extract message text — handles several common structures
    text_parts = []

    # Claude.ai format: chat_messages list with sender + text
    messages = (obj.get('chat_messages') or obj.get('messages') or
                obj.get('mapping') or obj.get('content') or [])

    if isinstance(messages, list):
        for msg in messages:
            if isinstance(msg, dict):
                role = (msg.get('sender') or msg.get('role') or
                        msg.get('author', {}).get('role', '') if isinstance(msg.get('author'), dict) else
                        msg.get('author', ''))
                # Get text content
                body = msg.get('text', '')
                if not body:
                    # OpenAI/generic format: content can be string or list
                    body = msg.get('content', '')
                    if isinstance(body, list):
                        body = ' '.join(
                            part.get('text', '') if isinstance(part, dict) else str(part)
                            for part in body
                        )
                if body and isinstance(body, str):
                    prefix = 'Human' if role in ('human', 'user') else 'Assistant' if role in ('assistant', 'bot', 'claude') else ''
                    if prefix:
                        text_parts.append(f'{prefix}: {body}')
                    else:
                        text_parts.append(body)
            elif isinstance(msg, str):
                text_parts.append(msg)
    elif isinstance(messages, dict):
        # OpenAI mapping format (dict of node IDs)
        for node in messages.values():
            if isinstance(node, dict) and 'message' in node:
                m = node['message']
                if isinstance(m, dict):
                    role = m.get('author', {}).get('role', '') if isinstance(m.get('author'), dict) else ''
                    content = m.get('content', {})
                    if isinstance(content, dict):
                        parts = content.get('parts', [])
                        body = ' '.join(str(p) for p in parts if isinstance(p, str))
                    elif isinstance(content, str):
                        body = content
                    else:
                        body = ''
                    if body:
                        prefix = 'Human' if role == 'user' else 'Assistant' if role == 'assistant' else ''
                        text_parts.append(f'{prefix}: {body}' if prefix else body)

    full_text = '\n\n'.join(text_parts)

    # If no messages extracted, try to use the whole object as text
    if not full_text.strip():
        # Maybe the conversation text is in a top-level field
        for text_key in ('text', 'body', 'transcript', 'content'):
            val = obj.get(text_key)
            if isinstance(val, str) and len(val) > 20:
                full_text = val
                break

    if not full_text.strip():
        return None

    return {
        'filename': f'{safe_name}.json',
        'content': full_text,
        'date': conv_date,
    }


def load_chat_files(chat_path):
    """Load text content from a zip file, directory, or single file.

    Handles Claude.ai JSON exports (with multiple conversations in one file),
    as well as plain .md/.txt files with one conversation each.
    """
    chat_files = []
    if chat_path is None:
        return chat_files

    chat_path = os.path.expanduser(chat_path)

    raw_files = []  # List of (filename, text, date) tuples

    if zipfile.is_zipfile(chat_path):
        with zipfile.ZipFile(chat_path, 'r') as zf:
            for name in zf.namelist():
                # Skip directories and hidden files
                basename = os.path.basename(name)
                if not basename or basename.startswith('.'):
                    continue
                # Accept common text/data formats
                lower = basename.lower()
                if not lower.endswith(('.md', '.txt', '.json', '.jsonl', '.csv', '.yaml', '.yml')):
                    continue
                try:
                    raw = zf.read(name)
                    text = raw.decode('utf-8', errors='replace')
                    info = zf.getinfo(name)
                    mod_time = datetime(*info.date_time) if info.date_time else None
                    raw_files.append((basename, text, mod_time))
                except Exception:
                    continue
    elif os.path.isdir(chat_path):
        for root, _dirs, files in os.walk(chat_path):
            for fname in files:
                if fname.startswith('.'):
                    continue
                lower = fname.lower()
                if not lower.endswith(('.md', '.txt', '.json', '.jsonl', '.csv', '.yaml', '.yml')):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, 'r', errors='replace') as f:
                        text = f.read()
                    mod_time = datetime.fromtimestamp(os.path.getmtime(fpath))
                    raw_files.append((fname, text, mod_time))
                except Exception:
                    continue
    else:
        try:
            with open(chat_path, 'r', errors='replace') as f:
                text = f.read()
            mod_time = datetime.fromtimestamp(os.path.getmtime(chat_path))
            raw_files.append((os.path.basename(chat_path), text, mod_time))
        except Exception:
            pass

    # Now split JSON files that contain multiple conversations
    for filename, text, mod_time in raw_files:
        if filename.lower().endswith(('.json', '.jsonl')):
            if filename.lower().endswith('.jsonl'):
                # JSONL: one JSON object per line
                for line_num, line in enumerate(text.splitlines()):
                    line = line.strip()
                    if not line:
                        continue
                    convs = _extract_conversations_from_json(line, f'{filename}_L{line_num + 1}', mod_time)
                    chat_files.extend(convs)
            else:
                convs = _extract_conversations_from_json(text, filename, mod_time)
                chat_files.extend(convs)
        else:
            # Plain text file — one conversation per file
            chat_files.append({
                'filename': filename,
                'content': text,
                'date': mod_time,
            })

    print(f"  Extracted {len(chat_files)} conversations from {len(raw_files)} files")
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
        if not block or block.startswith('```') or len(block) < 30:
            continue

        code_line_count = sum(1 for line in block.split('\n')
                              if line.strip().startswith(('$', '>', '#!', 'import ', 'from ', 'def ', 'class ')))
        total_lines = len(block.split('\n'))
        if total_lines > 1 and code_line_count / total_lines > 0.6:
            continue

        clean = block.replace('**', '').replace('`', '')
        clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', clean)
        clean = re.sub(r'^#+\s+', '', clean, flags=re.MULTILINE)
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


def match_chat_to_projects(chat_files, projects, verbose=False):
    """Match chat history to projects. Returns dict of snippets and dated entries.

    Two-tier matching:
    1) Per-conversation: if ANY paragraph in a chat file mentions a project,
       that whole conversation counts as a chat event for that project.
    2) Per-paragraph: best matching paragraphs become detailed timeline entries.
    """
    project_chat_data = {}

    # Pre-build search terms for each project
    project_terms = {}
    for project in projects:
        name = project.get('name', '')
        if name:
            project_terms[name] = _build_search_terms(name)

    # First pass: score every (project, chat_file) pair and collect paragraphs
    # This lets us count conversations, not just paragraphs
    for project in projects:
        name = project.get('name', '')
        if not name:
            continue

        search_terms = project_terms[name]
        # Track which conversation files matched this project
        matched_conversations = {}  # filename -> {date, best_score, paragraph_count}
        scored_paragraphs = []

        for chat in chat_files:
            paragraphs = _split_into_paragraphs(chat['content'])
            chat_date = chat.get('date')
            chat_filename = chat.get('filename', '')
            file_matched = False
            file_para_count = 0

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
                    file_matched = True
                    file_para_count += 1

            # Record the conversation-level match
            if file_matched:
                matched_conversations[chat_filename] = {
                    'date': chat_date,
                    'paragraph_count': file_para_count,
                }

        scored_paragraphs.sort(key=lambda x: x[0], reverse=True)

        # Best snippets for narrative (keep up to 50 for richer context)
        best_snippets = []
        # Detailed timeline entries from best-scoring paragraphs
        detailed_entries = []

        for _score, para, chat_date, chat_filename in scored_paragraphs:
            is_redundant = any(_overlap_ratio(para, existing) > 0.65 for existing in best_snippets)
            if not is_redundant:
                best_snippets.append(para)

                if chat_date:
                    date_str = chat_date.strftime('%Y-%m-%d')
                else:
                    date_str = 'Unknown date'
                source_hint = chat_filename.replace('.md', '').replace('.txt', '').replace('.json', '').replace('_', ' ')
                summary_line = para[:150]
                if len(para) > 150:
                    last_period = summary_line.rfind('.')
                    if last_period > 80:
                        summary_line = summary_line[:last_period + 1]
                    else:
                        summary_line = summary_line + '...'

                detailed_entries.append({
                    'date': date_str,
                    'source': f'Claude.ai Chat — {source_hint}',
                    'text': summary_line,
                })

                if len(best_snippets) >= 50:
                    break

        # Build per-conversation timeline entries (1 entry per conversation file)
        conversation_entries = []
        for fname, info in matched_conversations.items():
            if info['date']:
                date_str = info['date'].strftime('%Y-%m-%d')
            else:
                date_str = 'Unknown date'
            source_hint = fname.replace('.md', '').replace('.txt', '').replace('.json', '').replace('_', ' ')
            conversation_entries.append({
                'date': date_str,
                'source': f'Claude.ai Chat — {source_hint}',
                'text': f'Chat conversation ({info["paragraph_count"]} relevant sections)',
            })

        if best_snippets or conversation_entries:
            project_chat_data[name] = {
                'snippets': best_snippets,
                'timeline_entries': detailed_entries,
                'conversation_entries': conversation_entries,
                'conversation_count': len(matched_conversations),
            }
            if verbose:
                print(f"  Chat match for '{name}': {len(matched_conversations)} conversations, "
                      f"{len(scored_paragraphs)} paragraph matches, "
                      f"kept {len(best_snippets)} snippets, {len(detailed_entries)} detailed + "
                      f"{len(conversation_entries)} conversation entries")

    return project_chat_data


# =============================================================================
# PROJECT STATUS FILE PARSING
# =============================================================================

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
                    item = item.replace('**', '')
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

                # Check against skip patterns
                line_lower = line.lower()
                is_garbage = any(pattern in line_lower for pattern in COMMIT_SKIP_PATTERNS)

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

        # Defaults
        project.setdefault('progress', 0)
        project.setdefault('status', 'Unknown')
        project.setdefault('category', 'Personal')
        project.setdefault('repo', '')
        project.setdefault('has_repo', 'No')
        project.setdefault('last_worked', '')
        project.setdefault('last_synced', '')
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
            all_projects.append(project)
        if i % 5 == 0:
            _progress('parsing', f'Parsed {i+1}/{len(status_files)} files...')

            all_projects.append(project)
            if project['has_github_repo']:
                with_repos.append(project)
            else:
                without_repos.append(project)

        if chat_files:
            _progress('matching_chat', f'Matching {len(chat_files)} conversations to {len(all_projects)} projects...')
            chat_project_data = match_chat_to_projects(chat_files, all_projects, verbose=verbose)
            chat_stats['matched_projects'] = len(chat_project_data)
            chat_stats['total_conversations'] = sum(
                d.get('conversation_count', 0) for d in chat_project_data.values()
            )
            # Count unique matched files
            matched_files = set()
            for data in chat_project_data.values():
                for entry in data.get('conversation_entries', []):
                    src = entry.get('source', '')
                    matched_files.add(src)
            chat_stats['unmatched_files'] = len(chat_files) - len(matched_files)
            print(f"  Matched chat context to {len(chat_project_data)} projects "
                  f"({chat_stats['total_conversations']} conversations, "
                  f"{chat_stats['unmatched_files']} unmatched files)")

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

        project['narrative'] = build_project_narrative(project, chat_data)
        project['timeline'] = build_project_timeline(project, chat_data)
        project['open_threads'] = build_open_threads(project)
        # Store per-project chat conversation count
        if chat_data:
            project['chat_conversations'] = chat_data.get('conversation_count', 0)
        else:
            project['chat_conversations'] = 0

        if verbose:
            print(f"\n{project['name']}:")
            print(f"  Category: {project['category_group']}")
            print(f"  Timeline entries: {len(project['timeline'])}")
            print(f"  Open threads: {len(project['open_threads'])}")
            print(f"  Chat conversations: {project['chat_conversations']}")

        if i % 5 == 0:
            _progress('building', f'Built {i+1}/{len(all_projects)} project timelines...')

    all_projects.sort(key=lambda x: x['progress'], reverse=True)

    # Store stats + unmatched files for AI classification
    # Figure out which chat files were NOT matched to any project
    matched_filenames = set()
    for data in chat_project_data.values():
        for entry in data.get('conversation_entries', []):
            # Extract filename from source string
            src = entry.get('source', '')
            if ' — ' in src:
                fname_hint = src.split(' — ', 1)[1]
                matched_filenames.add(fname_hint)

    unmatched_chats = []
    for chat in (chat_files if chat_history_path else []):
        fname_hint = chat['filename'].replace('.md', '').replace('.txt', '').replace('.json', '').replace('_', ' ')
        if fname_hint not in matched_filenames:
            # Grab a short excerpt for AI classification
            content = chat.get('content', '')
            # Get the first ~300 chars of non-code text
            excerpt = re.sub(r'```[\s\S]*?```', '', content)
            excerpt = re.sub(r'^(Human|Assistant|User|Claude|System)\s*:', '', excerpt, flags=re.MULTILINE)
            excerpt = excerpt.strip()[:300]
            unmatched_chats.append({
                'filename': chat['filename'],
                'date': chat['date'].strftime('%Y-%m-%d') if chat.get('date') else 'Unknown',
                'excerpt': excerpt,
            })

    chat_stats['unmatched_chats'] = unmatched_chats
    load_projects._last_chat_stats = chat_stats

    _progress('done', f'Loaded {len(all_projects)} projects.')
    return all_projects

# Initialize the stats attribute
load_projects._last_chat_stats = {}


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
    parser.add_argument('--open', action='store_true',
                        help='Open the PDF after generation')
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

    if args.open:
        system = platform.system()
        if system == 'Darwin':
            subprocess.run(['open', output_path])
        elif system == 'Linux':
            subprocess.run(['xdg-open', output_path])
        elif system == 'Windows':
            os.startfile(output_path)


if __name__ == '__main__':
    main()
