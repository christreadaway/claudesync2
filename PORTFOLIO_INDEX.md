# Portfolio Index

> **Single Source of Truth** for all active projects.
> This file tracks every project, its status, and where to find detailed info.

---

## Quick Stats

| Metric | Count |
|--------|-------|
| **Total Projects** | 12 |
| **With GitHub Repos** | 11 |
| **Without GitHub Repos** | 1 |

---

## All Projects

| # | Project Name | Repository | Category | Progress | Status | Has Repo | Status File |
|---|--------------|------------|----------|----------|--------|----------|-------------|
| 1 | Claude Project Sync v2 | christreadaway/claudesync2 | Infrastructure | 40% | Active | Yes | [PROJECT_STATUS.md](PROJECT_STATUS.md) |
| 2 | Sacramental Records | (not created) | Church | 25% | Spec Complete | No | [PROJECT_STATUS_SacramentalRecords.md](PROJECT_STATUS_SacramentalRecords.md) |
| 3 | Ministry Life | christreadaway/ministrylife | Church | —% | — | Yes | ~/ministrylife/PROJECT_STATUS.md |
| 4 | Desmond | christreadaway/desmond | — | —% | — | Yes | ~/desmond/PROJECT_STATUS.md |
| 5 | Catholic Events | christreadaway/catholicevents | Church | —% | — | Yes | ~/catholicevents/PROJECT_STATUS.md |
| 6 | iMessage Dashboard v6 | christreadaway/imessage-dashboard-v6 | Personal | —% | — | Yes | ~/imessage-dashboard-v6/PROJECT_STATUS.md |
| 7 | [Project 7] | christreadaway/[repo] | — | —% | — | Yes | ~/[project]/PROJECT_STATUS.md |
| 8 | [Project 8] | christreadaway/[repo] | — | —% | — | Yes | ~/[project]/PROJECT_STATUS.md |
| 9 | [Project 9] | christreadaway/[repo] | — | —% | — | Yes | ~/[project]/PROJECT_STATUS.md |
| 10 | [Project 10] | christreadaway/[repo] | — | —% | — | Yes | ~/[project]/PROJECT_STATUS.md |
| 11 | [Project 11] | christreadaway/[repo] | — | —% | — | Yes | ~/[project]/PROJECT_STATUS.md |
| 12 | [Project 12] | christreadaway/[repo] | — | —% | — | Yes | ~/[project]/PROJECT_STATUS.md |

---

## By Category

### Infrastructure
- Claude Project Sync v2 (40%)

### Church / Catholic Tech
- Sacramental Records (25%)
- Ministry Life (—%)
- Catholic Events (—%)

### Personal
- iMessage Dashboard v6 (—%)

### School
- (none listed)

### Product
- (none listed)

### Research
- (none listed)

---

## Projects Needing Attention

### No GitHub Repo Yet
| Project | Next Step |
|---------|-----------|
| Sacramental Records | Create christreadaway/sacramentalrecords repo |

### Missing Data (need to sync from local PROJECT_STATUS.md)
- Ministry Life
- Desmond
- Catholic Events
- iMessage Dashboard v6
- Projects 7-12 (unknown)

---

## How to Update This Index

1. **Run the PDF generator** on your local machine to scan all PROJECT_STATUS.md files:
   ```bash
   python3 ~/claudesync2/generate_status_pdf.py --verbose
   ```

2. **Copy project data** from the verbose output into this index

3. **Commit and push** this file to keep it in sync

---

## Architecture Note

Each project has its own `PROJECT_STATUS.md` in its local directory. This index aggregates them into one view. The PDF generator (`generate_status_pdf.py`) scans all projects automatically — this index is for human reference and Claude context.

---

*Last updated: 2026-02-05*
