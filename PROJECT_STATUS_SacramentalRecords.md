# PROJECT_STATUS: Sacramental Records

---

## Metadata

| Field | Value |
|-------|-------|
| **Project Name** | Sacramental Records Management System (SRMS) |
| **Repository** | None yet — needs GitHub repo created |
| **Category** | Church / Catholic Tech |
| **Progress** | 25% |
| **Status** | Spec Complete — Ready for Development |
| **Last Worked** | 2026-02-04 |
| **Has GitHub Repo** | No |
| **Last Synced to Claude.ai** | 2026-02-04 |

---

## Project Summary

A digital sacramental records management system for Catholic parishes. Replaces the manual, handwritten record-keeping process across five physical register books with a single integrated digital platform. Built from a real interview with a parish secretary at St. Theresa Catholic Church in Austin, TX, plus analysis of 8 physical register book pages (Baptismal, First Communion, Confirmation, Marriage).

The product spec (v1.0) is complete and ready for a developer to build from. No personal names or data from the registers were captured — images were used only to map column structures.

The project has a longer-term vision (v4/v5) that layers blockchain verification and Vaticoin on top, but v1 is purely about getting the basics right: a clean, usable records tool for parish secretaries.

---

## Current State

### What Exists
- **Product Spec v1.0** (PDF + DOCX) — Full 13-page specification built from parish secretary interview and physical register analysis
- **Project Summary** (Markdown) — Context document for MCP server / future Claude sessions
- One-page proposal: "Vatican Sacramental Records on Blockchain" (Google Drive, Dec 17, 2025)
- Vatican Blockchain Strategy with full roadmap (Google Drive, Jan 6, 2026)
- Vaticoin Executive Summary — DRAFT and professional versions (Google Drive, Jan 6, 2026)
- Conceptual blockchain architecture defined (three-tier: Ethereum mainnet → L2 → off-chain encrypted DB)
- Privacy model, multi-sig governance, death protocol all designed (for future blockchain layer)

### What Doesn't Exist Yet
- GitHub repository
- Any code
- Database schema (entities defined in spec, schema not yet built)
- UI/UX wireframes
- Tech stack decision (web app vs. desktop vs. hybrid)
- Cross-parish notification letter format/template

### Blockers
- No repo created yet
- Tech stack not decided
- 7 open design questions unresolved (see section below)

---

## The Core Problem

Catholic parishes must maintain permanent records of every sacrament (Baptism, First Communion, Confirmation, Marriage, Death) in physical register books per Canon Law. Today the process is:

- Entirely handwritten across 5 separate physical books
- Massively redundant — a single Easter Vigil RCIA candidate requires entries in 3 separate books
- Cross-parish communication is paper-based — when someone baptized at Parish A receives a sacrament at Parish B, Parish B has to mail a paper notification back to Parish A
- The baptismal parish is the canonical source of truth for a person's entire sacramental life — every subsequent sacrament must be reported back to it
- The parish secretary reserves entire summers just to catch up on record entry

---

## Primary User: The Parish Secretary

The parish secretary (or parish administrator) maintains all sacramental registers. She receives information from religious education coordinators, other parishes, the diocese, and clergy, and must accurately record every sacramental event in the correct register book. She also handles incoming requests from other parishes for sacramental verification and sends outgoing notifications when parishioners baptized elsewhere receive sacraments at her parish.

### Secondary Users
- **Religious Education Coordinator** (e.g., Claire) — Provides spreadsheets of kids/adults receiving sacraments. Responsible for sending cross-parish notifications for confirmations.
- **Clergy (Priests and Deacons)** — Administer sacraments, need to verify sacramental status before performing certain rites
- **Other Parishes** — Send and receive cross-parish notifications
- **The Diocese** — Requests aggregate info, issues dispensations and annulment notifications

### Key Roles Referenced in Interview
- **Parish Secretary** — Primary user, maintains all registers
- **Religious Education Coordinator** — Produces sacrament preparation spreadsheets, handles confirmation notifications
- **Adult Preparation Instructor** — Teaches adult sacrament preparation classes
- **Parish Deacon** — Has performed convalidations in the chapel

---

## Core Architecture: Person Record as Central Hub

Every individual has a single Person Record — the digital equivalent of the baptismal register entry, which Canon Law designates as the master record. This eliminates cross-referencing across multiple physical books.

### Person Record Contains:
- Full legal name + any religious/confirmation name
- Date and place of birth
- Parents' names (father's full name, mother's full maiden name)
- Baptism details: date, place, church, minister, sponsors/godparents
- If baptized in another denomination: original church, denomination, date
- Profession of Faith date (if converting)
- First Communion details: date, place, church, minister
- Confirmation details: date, place, church, minister (typically bishop), confirmation name, sponsor
- Marriage details: date, place, spouse, minister, witnesses, type (standard/convalidation/with dispensation)
- Marriage annotations: dispensations, annulments, convalidations
- Death record: date, if applicable
- Cross-parish notification log

---

## The Five Register Views

Each traditional register book becomes a filtered, chronological view of the same underlying data. Not separate databases — filtered views.

### Baptismal Register
Entry No. | Name | Date of Baptism | Church/Location | Date & Place of Birth | Father's Name | Mother's Maiden Name | Priest/Minister | Sponsors | Remarks (subsequent sacraments noted here)

### First Communion Register
Entry No. | Baptismal & Family Name | Place & Date of Birth | Age | Place & Date of Baptism | Date of First Communion | Residence | Minister

### Confirmation Register
Entry No. | Baptismal & Family Name | Confirmation Name | Age | Place & Date of Baptism | Residence | Parents | Sponsor | Minister (usually Bishop)

### Marriage Register
Entry No. | Contracting Parties (both names) | Residence | Place & Date of Marriage | Place & Date of Baptism | Parents | Witnesses | Priest/Minister | Banns/Dispensations/Remarks

### Death Register
Minimal for v1 — "not a sacrament" per the secretary, but tracked.

---

## Key Workflows

### Easter Vigil / RCIA Batch Workflow
The single highest-volume event for sacramental record-keeping. Multiple adults receive multiple sacraments on the same night.
- Enter the candidate once with all their information
- Select which sacraments they received (Baptism, First Communion, Confirmation, Profession of Faith)
- System auto-creates entries in all relevant registers from that single input
- For candidates baptized elsewhere, system flags that a cross-parish notification is needed

### Cross-Parish Notification System
The most operationally complex part of the current manual process:
- Auto-detects when a sacrament is recorded for someone whose baptismal parish is different
- Generates notification (digital if other parish is on platform, printable letter if not)
- Tracks notification status: sent, received, acknowledged
- Provides workflow for receiving notifications and adding events to baptismal records
- RE coordinator handles confirmation notifications; secretary handles the rest

---

## Business Rules and Logic

### 1. The Baptismal Parish Rule (foundational)
Wherever a person was baptized is the keeper of ALL their sacramental records. Every sacrament at any other parish must be reported back. This is the #1 rule the system enforces.

### 2. Denomination Handling
People baptized in other Christian denominations (Presbyterian, Baptist, Lutheran, etc.) get recorded with their original baptism info + a "Profession of Faith" entry when they become Catholic. They are NOT re-baptized.

### 3. Marriage Type Logic
- Both Catholic → standard marriage record
- One non-Catholic → requires dispensation notation (diocesan permission)
- Previously married civilly → convalidation (blessing of existing marriage — big spike during COVID)
- Prior marriage annulled → original record annotated (not deleted) with annulment date and tribunal reference

### 4. Minister Permissions
- Deacons CAN: baptize, perform marriages/convalidations (without Mass)
- Deacons CANNOT: First Communion, Confirmation
- Confirmation is usually the Bishop
- Weddings can be without Mass

### 5. Sacrament Sequencing
System should be aware of typical order but not rigidly enforce it (adults often receive out of order):
- Infant path: Baptism → First Communion (age 7-8) → Confirmation (varies) → Marriage (optional)
- Adult convert (RCIA): May receive Baptism + First Communion + Confirmation all at once
- Returning Catholic: May catch up on missed sacraments
- System flags unusual sequences for review but does not block entry

### 6. Annotation-Not-Deletion
Records are never deleted, only annotated. Mirrors Canon Law and physical book practice (line through error + corrective note, never erasure). Full audit trail of all changes.

---

## Data Entities

### Person
Full legal name, date of birth, place of birth, father's name, mother's maiden name, current address/residence, contact info (optional), unique system ID

### Sacramental Event
Event type (Baptism, First Communion, Confirmation, Marriage, Death, Profession of Faith), date administered, location/church, minister (name and title), entry number in register, associated persons (sponsors, godparents, witnesses, spouse), notes/remarks

### Parish
Parish name, diocese, address, contact info, whether on digital platform (for notification routing)

### Notification
Sending parish, receiving parish, person referenced, sacramental event details, date sent, date received/acknowledged, method (digital or paper)

### Data Integrity Rules
- No sacramental record may be deleted once entered — corrections via annotations only
- Entry numbers within each register must be sequential and unique
- All dates validated (no future dates for past events)
- Marriage records require two Person Records linked
- Full audit trail of all changes

---

## Inputs and Outputs

### Inputs
- Manual data entry by parish secretary (primary)
- Spreadsheet imports from RE coordinator (CSV/XLSX)
- Incoming cross-parish notifications (digital or manual from paper)
- Diocesan notifications (annulments, dispensation approvals)
- RCIA/Easter Vigil candidate lists

### Outputs
- Printable register pages matching physical book format (for parallel operation during transition)
- Cross-parish notification letters (auto-generated, printable)
- Sacramental certificates (Baptism, First Communion, Confirmation, Marriage)
- Search results for clergy verifying sacramental status
- Audit trail / notification log

### What the User Sees
Clean dashboard: recent entries, pending notifications (incoming and outgoing), upcoming sacramental events to record, quick access to each register view. Should feel as familiar as the physical books but remove the tedium.

---

## What's In Scope for v1

- Person Record (central hub)
- All 5 Register Views
- Manual data entry
- Spreadsheet import (CSV/XLSX)
- Easter Vigil / RCIA batch workflow
- Cross-parish notification generation (printable PDF letters)
- Notification tracking (sent/received/acknowledged)
- Printable register pages matching physical book format
- Sacramental certificate generation
- Search by name
- Full audit trail
- Self-contained — no external dependencies beyond CSV import and PDF export
- Optional: email integration for digital notifications
- Optional: diocesan directory API lookup

## What's Out of Scope for v1

- Financial / offertory management
- Parish calendar or scheduling
- Parishioner self-service portal (staff-only for v1)
- Integration with PDS, ParishSOFT, Realm, etc.
- Diocesan-level dashboards or reporting
- OCR / digitization of existing physical books (backfill is future)
- Sacramental preparation tracking (RCIA attendance, marriage prep)
- Multi-language support (English only)
- Blockchain verification (v3)
- Vaticoin integration (v4/v5)

---

## Success Criteria

1. Record a single sacramental event in under 2 minutes (vs. 5–10 today)
2. Easter Vigil batch of 10 candidates fully entered in under 30 minutes (vs. multi-hour today)
3. Cross-parish notifications generated automatically with zero manual letter composition
4. Any person's complete sacramental history retrievable by name in under 10 seconds
5. Printable register pages satisfy physical record obligations during transition
6. Zero data loss via audit trail and annotation model

---

## Open Design Questions (7 unresolved)

| # | Question | Notes |
|---|----------|-------|
| 1 | Should the system maintain physical book page/entry numbering alongside internal IDs? | Many parishes will run digital + physical in parallel during transition |
| 2 | What's the right cross-parish notification protocol when the other parish isn't on the platform? | Auto-generated PDF letter is baseline, but format and delivery need validation |
| 3 | Do we need role-based permissions for v1 (secretary vs. clergy vs. RE coordinator) or just single admin? | Start simple, add roles later if needed |
| 4 | How to handle partial/uncertain data (e.g., unknown baptism date for an adult convert)? | Physical books have question marks in some fields today |
| 5 | Can we launch single-parish and add the network later? | Single-parish value exists even without the network |
| 6 | Should printable register pages exactly replicate physical format or modernize? | Secretary familiarity vs. improved readability |
| 7 | How minimal can the death register be? | "Not a sacrament" per the secretary, but tracked |

---

## Version Roadmap

### v1 — Basic Records Management (current target)
Spec complete. Person Record + 5 Register Views + batch workflow + cross-parish notifications + search + certificates + audit trail. No blockchain, no crypto — just a clean database with a usable interface.

### v2 — Diocese-Level Features
Multi-parish data access for diocese offices. Cross-parish record verification. Reporting and analytics.

### v3 — Blockchain Verification Layer
On-chain record hashing for immutability. Verification without centralized database. Records survive parish closures, disasters, wars.

### v4/v5 — Vaticoin Integration
Commemorative coins with crypto pairing. Confraternity of Church Modernization as launch vehicle. Vatican Media authentication. Full economic ecosystem. Core principle: cryptocurrency is NEVER required to receive sacraments.

---

## Future Blockchain Architecture (v3+)

### Three-Party Multi-Signature System
- Parish Priest (witness/minister)
- Diocese/Bishop (canonical approval)
- Individual (consent/control of personal details)
- Requires 3-of-3 signatures to create a record

### Platform: Ethereum Layer 2
- Optimism, Arbitrum, or Base
- Three-tier: Ethereum Mainnet (master registry) → L2 (day-to-day ops) → Off-chain encrypted DB (personal info)

### Privacy Model
- Public on-chain: sacrament type, date, location, certificate ID (hashed)
- Private encrypted: names, family details, witnesses, sponsors
- Individual controls decryption keys; zero-knowledge proofs for verification

### Death Protocol
- Individual keys become permanently inactive (non-transferable)
- Church keys retain full access
- Family requests through diocese (same as today)

---

## Future Vaticoin Economics (v4/v5)

- 10 billion coins on Ethereum
- New coins minted only when Catholics receive sacraments (5 Vaticoin per baptism)
- Supply growth mirrors Catholic population (~2-3% annually)
- Vatican receives 50% initial supply over 20 years
- Commemorative coin tiers: Standard (€25-50), Premium (€100-250), Patron (€500+)
- Confraternity of Church Modernization: 1,000 founding members max, $2,500-$5,000 membership, annual pilgrimage requirement

---

## Related Documents

| Document | Created | Location |
|----------|---------|----------|
| Product Spec v1.0 (PDF + DOCX) | Feb 2026 | Claude.ai Project: Sacramental Records |
| Project Summary (Markdown) | Feb 2026 | Claude.ai Project: Sacramental Records |
| Vatican Sacramental Records on Blockchain (one-pager) | Dec 2025 | Google Drive (private) |
| Vatican Blockchain Strategy (full roadmap) | Jan 2026 | Google Drive (private) |
| Vaticoin Executive Summary — DRAFT | Jan 2026 | Google Drive (private) |
| Vaticoin Executive Summary (professional) | Jan 2026 | Google Drive (private) |

---

## Progress Log

### 2026-02-04
Integrated Product Spec v1.0 and Project Summary from Claude.ai Sacramental Records project into this status file. Spec was built from parish secretary interview at St. Theresa (Austin, TX) + physical register analysis. Status upgraded from "Planning" to "Spec Complete — Ready for Development." Progress bumped to 25%.

### 2026-02-04 (earlier)
Compiled all existing project documentation from Google Drive into this PROJECT_STATUS file. Established that v1 is the basic records management system (no blockchain), and that Vaticoin/blockchain is the v4/v5 future layer.

### 2026-01-06
Created Vatican Blockchain Strategy document with full implementation roadmap including Confraternity model, phased Vaticoin rollout, regulatory positioning. Created Vaticoin Executive Summary (draft + professional versions).

### 2025-12-17
Created initial one-page proposal covering core concept, three-party multi-sig architecture, Ethereum L2 recommendation, privacy model, death protocol, governance, pilot plan.

---

## Next Steps

1. Resolve the 7 open design questions
2. Decide on tech stack (web app vs. desktop vs. hybrid)
3. Create GitHub repo (christreadaway/sacramentalrecords)
4. Build database schema from the 4 data entities defined in spec
5. Wireframe the dashboard and register views
6. Define the cross-parish notification letter format/template
7. Build v1 prototype
8. Add sacramentalrecords directory to MCP filesystem config on Mac and PC

---

*Last updated: 2026-02-04*
