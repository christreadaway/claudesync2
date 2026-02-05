#!/usr/bin/env python3
"""
Claude Project Sync - Batch Repository Updater

Auto-detects GitHub repos from local git directories and updates PROJECT_STATUS.md files.

Usage:
    # Auto-detect and update all projects
    python3 update_repos.py

    # List all projects and their status
    python3 update_repos.py --list

    # Update a specific project manually
    python3 update_repos.py --project "Project Name" --repo "user/repo"
"""

import argparse
import os
import re
import subprocess


def get_git_remote(project_dir):
    """Get the GitHub repo from git remote origin."""
    try:
        result = subprocess.run(
            ['git', 'remote', 'get-url', 'origin'],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # Parse various formats:
            # https://github.com/user/repo.git
            # git@github.com:user/repo.git
            # https://github.com/user/repo

            if 'github.com' in url:
                # Remove .git suffix
                url = url.rstrip('.git')

                if url.startswith('git@'):
                    # git@github.com:user/repo
                    match = re.search(r'github\.com[:/](.+/.+)', url)
                else:
                    # https://github.com/user/repo
                    match = re.search(r'github\.com/(.+/.+)', url)

                if match:
                    return match.group(1)
    except Exception:
        pass
    return None


def find_project_status_files(max_depth=2):
    """Find all PROJECT_STATUS.md files."""
    home = os.path.expanduser('~')
    skip_dirs = {'node_modules', '.git', '__pycache__', 'venv', '.venv',
                 'dist', 'build', '.next', 'coverage', 'Library', '.Trash',
                 'Applications', 'Pictures', 'Music', 'Movies', 'Documents'}

    status_files = []
    for root, dirs, files in os.walk(home):
        depth = root.replace(home, '').count(os.sep)
        if depth >= max_depth:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        if 'PROJECT_STATUS.md' in files:
            status_files.append(os.path.join(root, 'PROJECT_STATUS.md'))
    return status_files


def parse_project_status(file_path):
    """Parse a PROJECT_STATUS.md file."""
    with open(file_path, 'r') as f:
        content = f.read()

    project = {'file_path': file_path, 'content': content}

    name_match = re.search(r'# PROJECT_STATUS:\s*(.+)', content)
    project['name'] = name_match.group(1).strip() if name_match else os.path.basename(os.path.dirname(file_path))

    repo_match = re.search(r'\*\*Repository\*\*\s*\|\s*(.+)', content)
    project['repo'] = repo_match.group(1).strip().rstrip('|').strip() if repo_match else ''

    has_repo_match = re.search(r'\*\*Has GitHub Repo\*\*\s*\|\s*(.+)', content)
    project['has_repo'] = has_repo_match.group(1).strip().rstrip('|').strip() if has_repo_match else 'No'

    # Check if it's a real repo or placeholder
    project['has_real_repo'] = (
        project['has_repo'].lower() == 'yes' and
        project['repo'] and
        'not yet' not in project['repo'].lower()
    )

    return project


def update_repo_in_file(file_path, repo_name):
    """Update the repository info in a PROJECT_STATUS.md file."""
    with open(file_path, 'r') as f:
        content = f.read()

    # Update Repository field
    content = re.sub(
        r'(\*\*Repository\*\*\s*\|\s*)([^\n|]+)',
        f'\\1{repo_name}',
        content
    )

    # Update Has GitHub Repo field
    content = re.sub(
        r'(\*\*Has GitHub Repo\*\*\s*\|\s*)([^\n|]+)',
        r'\1Yes',
        content
    )

    with open(file_path, 'w') as f:
        f.write(content)

    return True


def list_projects(projects):
    """List all projects and their repo status."""
    print(f"\n{'='*60}")
    print(f"{'Project':<25} {'Repository':<25} {'Has Repo'}")
    print(f"{'='*60}")

    for p in sorted(projects, key=lambda x: x['name']):
        repo_display = p['repo'][:23] + '..' if len(p['repo']) > 25 else p['repo']
        status = 'Yes' if p['has_real_repo'] else 'No'
        print(f"{p['name']:<25} {repo_display:<25} {status}")

    print(f"{'='*60}")

    with_repo = sum(1 for p in projects if p['has_real_repo'])
    without_repo = len(projects) - with_repo
    print(f"Total: {len(projects)} projects ({with_repo} with repos, {without_repo} without)")


def auto_update(projects):
    """Auto-detect repos from git remotes and update PROJECT_STATUS.md files."""
    missing_repo = [p for p in projects if not p['has_real_repo']]

    if not missing_repo:
        print("\nAll projects already have repository information!")
        return

    print(f"\n{len(missing_repo)} projects missing repository info. Auto-detecting...\n")

    updated = 0
    not_found = []

    for p in missing_repo:
        project_dir = os.path.dirname(p['file_path'])
        repo = get_git_remote(project_dir)

        if repo:
            update_repo_in_file(p['file_path'], repo)
            print(f"  Updated: {p['name']} -> {repo}")
            updated += 1
        else:
            not_found.append(p['name'])

    print(f"\n{'='*50}")
    print(f"Updated: {updated} projects")

    if not_found:
        print(f"\nNo git remote found for {len(not_found)} projects:")
        for name in not_found:
            print(f"  - {name}")
        print("\nTo manually update these, use:")
        print("  python3 update_repos.py --project \"Name\" --repo \"user/repo\"")

    if updated > 0:
        print("\nRun 'python3 generate_status_pdf.py' to regenerate the PDF.")


def update_single_project(projects, project_name, repo_name):
    """Update a single project by name."""
    matches = [p for p in projects if p['name'].lower() == project_name.lower()]

    if not matches:
        print(f"Error: Project '{project_name}' not found")
        print("\nAvailable projects:")
        for p in sorted(projects, key=lambda x: x['name']):
            print(f"  - {p['name']}")
        return False

    p = matches[0]
    if '/' not in repo_name:
        # Assume user's GitHub username as prefix if not provided
        print(f"Note: No username prefix provided. Use 'user/repo' format for accuracy.")
        repo_name = repo_name

    update_repo_in_file(p['file_path'], repo_name)
    print(f"Updated {p['name']}: {repo_name}")
    return True


def main():
    parser = argparse.ArgumentParser(description='Update repository info in PROJECT_STATUS.md files')
    parser.add_argument('--list', '-l', action='store_true', help='List all projects')
    parser.add_argument('--project', '-p', help='Project name to update')
    parser.add_argument('--repo', '-r', help='Repository (user/repo format)')

    args = parser.parse_args()

    print("Scanning for PROJECT_STATUS.md files...")
    files = find_project_status_files()
    projects = [parse_project_status(f) for f in files]
    print(f"Found {len(projects)} projects")

    if args.list:
        list_projects(projects)
    elif args.project and args.repo:
        update_single_project(projects, args.project, args.repo)
    elif args.project or args.repo:
        print("Error: --project and --repo must be used together")
    else:
        auto_update(projects)


if __name__ == '__main__':
    main()
