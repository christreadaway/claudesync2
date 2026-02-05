# Portfolio Index

> **Single Source of Truth** for all active projects.
> This file tracks every project, its status, and where to find detailed info.

---

## Quick Stats

| Metric | Count |
|--------|-------|
| **Total Projects** | 14 |
| **With GitHub Repos** | 13 |
| **Without GitHub Repos** | 1 |

---

## All Projects

| # | Project Name | Repository | Category | Has Repo | Status File |
|---|--------------|------------|----------|----------|-------------|
| 1 | audioscribe | christreadaway/audioscribe | Product | Yes | ~/audioscribe/PROJECT_STATUS.md |
| 2 | Catholic Events | christreadaway/catholicevents | Church | Yes | ~/catholicevents/PROJECT_STATUS.md |
| 3 | Claude Project Sync (v1) | christreadaway/claude-project-sync | Infrastructure | Yes | ~/claude-project-sync/PROJECT_STATUS.md |
| 4 | Claude Project Sync v2 | christreadaway/claudesync2 | Infrastructure | Yes | [PROJECT_STATUS.md](PROJECT_STATUS.md) |
| 5 | Desmond | christreadaway/desmond | Personal | Yes | ~/desmond/PROJECT_STATUS.md |
| 6 | GrantFinder AI | christreadaway/grantfinder | Product | Yes | ~/grantfinder/PROJECT_STATUS.md |
| 7 | iMessage Dashboard v6 | christreadaway/imessage-dashboard-v6 | Personal | Yes | ~/imessage-dashboard-v6/PROJECT_STATUS.md |
| 8 | Ministry Fair App | christreadaway/ministryfair | Church | Yes | ~/ministryfair/PROJECT_STATUS.md |
| 9 | MinistryLife | christreadaway/ministrylife | Church | Yes | ~/ministrylife/PROJECT_STATUS.md |
| 10 | multiloc.ai (Polygraph) | christreadaway/polygraph | Product | Yes | ~/polygraph/PROJECT_STATUS.md |
| 11 | ParentPoint | christreadaway/parentpoint | School | Yes | ~/parentpoint/PROJECT_STATUS.md |
| 12 | ParentPoint EDU | christreadaway/parentpointedu | School | Yes | ~/parentpointedu/PROJECT_STATUS.md |
| 13 | Personal CRM | christreadaway/personalcrm | Personal | Yes | ~/personalcrm/PROJECT_STATUS.md |
| 14 | Sacramental Records | (not created) | Church | No | [PROJECT_STATUS_SacramentalRecords.md](PROJECT_STATUS_SacramentalRecords.md) |

---

## By Category

### Infrastructure
| Project | Repository | Key Features |
|---------|------------|--------------|
| Claude Project Sync (v1) | claude-project-sync | Original sync tool |
| Claude Project Sync v2 | claudesync2 | PDF dashboard, MCP integration, multi-platform |

### Church / Catholic Tech
| Project | Repository | Key Features |
|---------|------------|--------------|
| Catholic Events | catholicevents | Product spec v2, parish/school directory, bulletin parsing |
| Ministry Fair App | ministryfair | Public-facing app, admin console, Google Sign-In |
| MinistryLife | ministrylife | Product spec v1, admin HTML interface |
| Sacramental Records | (none) | Spec complete, 5 register views, cross-parish notifications |

### School
| Project | Repository | Key Features |
|---------|------------|--------------|
| ParentPoint | parentpoint | Family profiles, custody schedules, Alexa integration |
| ParentPoint EDU | parentpointedu | Firebase, Google sign-in, academic calendar, AI chat |

### Product
| Project | Repository | Key Features |
|---------|------------|--------------|
| audioscribe | audioscribe | WhisperX transcription, Gradio web UI, speaker diarization |
| GrantFinder AI | grantfinder | Product spec v2.4, grant discovery, probability scoring |
| multiloc.ai (Polygraph) | polygraph | Domain purchased, full spec document, job scheduler |

### Personal
| Project | Repository | Key Features |
|---------|------------|--------------|
| Desmond | desmond | v1 shipped, iMessage exporter, Windows/Android support |
| iMessage Dashboard v6 | imessage-dashboard-v6 | Package dependencies defined |
| Personal CRM | personalcrm | GitHub repo created, README exists |

---

## Projects Needing Attention

### No GitHub Repo Yet
| Project | Next Step |
|---------|-----------|
| Sacramental Records | Create christreadaway/sacramentalrecords repo |

### Early Stage (minimal features/commits)
| Project | Status |
|---------|--------|
| Personal CRM | Repo created, needs development |
| iMessage Dashboard v6 | Dependencies defined, no commits yet |
| Claude Project Sync (v1) | Superseded by v2 |

---

## How to Update This Index

1. **Run the PDF generator** on your local machine:
   ```bash
   python3 ~/claudesync2/generate_status_pdf.py --verbose
   ```

2. **Update this file** with any new projects or status changes

3. **Commit and push** to keep the index in sync

---

## Architecture Note

Each project has its own `PROJECT_STATUS.md` in its local directory. This index aggregates them into one view. The PDF generator (`generate_status_pdf.py`) scans all projects automatically — this index is for human reference and Claude context.

---

*Last updated: 2026-02-05*
