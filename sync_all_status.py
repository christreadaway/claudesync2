#!/usr/bin/env python3
"""
Sync all PROJECT_STATUS.md files with recent git activity.
Scans each project, extracts recent commits, and appends to Progress Log.
"""

import os
import subprocess
from datetime import datetime, timedelta

# All project directories (relative to home)
PROJECTS = [
    ("audioscribe", "audioscribe"),
    ("Catholic Events", "catholicevents"),
    ("Claude Project Sync (v1)", "claude-project-sync"),
    ("Claude Project Sync v2", "claudesync2"),
    ("Desmond", "desmond"),
    ("GrantFinder AI", "grantfinder"),
    ("iMessage Dashboard v6", "imessage-dashboard-v6"),
    ("Ministry Fair App", "ministryfair"),
    ("MinistryLife", "ministrylife"),
    ("multiloc.ai (Polygraph)", "polygraph"),
    ("ParentPoint", "parentpoint"),
    ("ParentPoint EDU", "parentpointedu"),
    ("Personal CRM", "personalcrm"),
]

HOME = os.path.expanduser("~")
TODAY = datetime.now().strftime("%Y-%m-%d")

# Skip garbage commits
SKIP_PATTERNS = [
    "wip", "fix typo", "typo", "cleanup", "clean up", "formatting",
    "merge", "initial commit", "add files via upload", "delete",
    "update readme", "readme", "gitignore"
]

def get_recent_commits(project_dir, days=7):
    """Get meaningful commits from the last N days."""
    try:
        since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        result = subprocess.run(
            ["git", "log", f"--since={since_date}", "--pretty=format:%s", "--all"],
            cwd=project_dir,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return []

        commits = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line or len(line) < 15:
                continue
            # Skip garbage commits
            if any(skip.lower() in line.lower() for skip in SKIP_PATTERNS):
                continue
            commits.append(line)
        return commits[:5]  # Max 5 commits
    except Exception as e:
        print(f"  Error getting commits: {e}")
        return []

def update_status_file(project_name, project_dir):
    """Update PROJECT_STATUS.md with recent activity."""
    status_file = os.path.join(project_dir, "PROJECT_STATUS.md")

    if not os.path.exists(status_file):
        print(f"  ⚠️  No PROJECT_STATUS.md found")
        return False

    # Get recent commits
    commits = get_recent_commits(project_dir)
    if not commits:
        print(f"  ℹ️  No new commits in last 7 days")
        return False

    # Read current file
    with open(status_file, "r") as f:
        content = f.read()

    # Check if we already have an entry for today
    if f"### {TODAY}" in content:
        print(f"  ℹ️  Already has entry for {TODAY}")
        return False

    # Build the new entry
    entry_lines = [f"\n### {TODAY}\n"]
    entry_lines.append("**Recent commits:**\n")
    for commit in commits:
        entry_lines.append(f"- {commit}\n")
    entry_lines.append("\n")
    new_entry = "".join(entry_lines)

    # Find Progress Log section and insert after the header
    if "## Progress Log" in content:
        # Insert after "## Progress Log" line
        parts = content.split("## Progress Log", 1)
        if len(parts) == 2:
            # Find the end of the Progress Log header line
            after_header = parts[1]
            # Skip any blank lines right after the header
            lines = after_header.split("\n", 2)
            if len(lines) >= 2:
                new_content = parts[0] + "## Progress Log\n" + new_entry + after_header.lstrip("\n")
            else:
                new_content = parts[0] + "## Progress Log\n" + new_entry + after_header

            with open(status_file, "w") as f:
                f.write(new_content)
            print(f"  ✅ Added {len(commits)} commits to Progress Log")
            return True

    print(f"  ⚠️  No Progress Log section found")
    return False

def main():
    print(f"🔄 Syncing PROJECT_STATUS.md files ({TODAY})\n")

    updated = 0
    skipped = 0

    for project_name, project_folder in PROJECTS:
        project_dir = os.path.join(HOME, project_folder)
        print(f"📁 {project_name} ({project_folder}/)")

        if not os.path.isdir(project_dir):
            print(f"  ⚠️  Directory not found")
            skipped += 1
            continue

        if update_status_file(project_name, project_dir):
            updated += 1
        else:
            skipped += 1

    print(f"\n✅ Done: {updated} updated, {skipped} skipped")
    print(f"\nRun 'python3 ~/claudesync2/generate_status_pdf.py' to regenerate PDF")

if __name__ == "__main__":
    main()
