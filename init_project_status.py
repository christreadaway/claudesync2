#!/usr/bin/env python3
"""
Claude Project Sync - Project Status Initializer

Initializes a PROJECT_STATUS.md file for a new project.
This file contains STATUS DATA, not instructions.

Usage:
    python3 init_project_status.py /path/to/project --name "My Project" --category School
"""

import argparse
import os
from datetime import datetime


CATEGORIES = ['Infrastructure', 'School', 'Church', 'Product', 'Research', 'Personal']

TEMPLATE = '''# PROJECT_STATUS: {name}

> This file contains project STATUS data.
> For Claude Code instructions, see ~/.claude/CLAUDE.md

---

## Metadata

| Field | Value |
|-------|-------|
| **Project Name** | {name} |
| **Repository** | {repo} |
| **Category** | {category} |
| **Progress** | {progress}% |
| **Status** | {status} |
| **Last Worked** | {date} |
| **Has GitHub Repo** | {has_repo} |

---

## Current State

### What's Working
- (Describe current functionality)

### What's Not Working
- (Describe known issues)

### Blockers
- (List any blockers)

---

## Progress Log

### {date}

**What was built:**
- Initial project status file created

**What was figured out:**
- Project structure defined

**Still stuck on:**
- (Nothing yet)

**Next time:**
- Begin development

---

## Reusable Assets

| Asset | Description | Tags |
|-------|-------------|------|
| (none yet) | | |

---

*Last updated: {date}*
'''


def init_project_status(project_path, name, category, repo=None, progress=0, status='Not Started'):
    """Initialize a PROJECT_STATUS.md file in the given project directory."""

    project_path = os.path.abspath(os.path.expanduser(project_path))

    if not os.path.isdir(project_path):
        print(f"Error: {project_path} is not a valid directory")
        return False

    status_file = os.path.join(project_path, 'PROJECT_STATUS.md')

    if os.path.exists(status_file):
        response = input(f"PROJECT_STATUS.md already exists. Overwrite? (y/N): ")
        if response.lower() != 'y':
            print("Aborted.")
            return False

    today = datetime.now().strftime('%Y-%m-%d')
    has_repo = 'Yes' if repo else 'No'
    repo_str = repo if repo else '(not yet created)'

    content = TEMPLATE.format(
        name=name,
        repo=repo_str,
        category=category,
        progress=progress,
        status=status,
        date=today,
        has_repo=has_repo
    )

    with open(status_file, 'w') as f:
        f.write(content)

    print(f"Created: {status_file}")
    print(f"  Project: {name}")
    print(f"  Category: {category}")
    print(f"  Progress: {progress}%")

    return True


def main():
    parser = argparse.ArgumentParser(
        description='Initialize a PROJECT_STATUS.md file for a new project',
        epilog=f'Categories: {", ".join(CATEGORIES)}'
    )

    parser.add_argument('project_path', help='Path to the project directory')
    parser.add_argument('--name', '-n', required=True, help='Name of the project')
    parser.add_argument('--category', '-c', default='Personal', choices=CATEGORIES)
    parser.add_argument('--repo', '-r', default=None, help='GitHub repository')
    parser.add_argument('--progress', '-p', type=int, default=0, help='Initial progress (0-100)')
    parser.add_argument('--status', '-s', default='Not Started', help='Initial status string')

    args = parser.parse_args()

    if not 0 <= args.progress <= 100:
        print("Error: Progress must be between 0 and 100")
        return

    init_project_status(args.project_path, args.name, args.category,
                        args.repo, args.progress, args.status)


if __name__ == '__main__':
    main()
