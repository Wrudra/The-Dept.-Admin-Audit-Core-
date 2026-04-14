---
name: nsu-audit-advisor
description: Knows NSU (North South University) graduation requirements for CSE (130cr) and MIC (120cr) undergraduate programs. Use for questions about credits, course requirements, grading policy, graduation eligibility, audit result interpretation, or running a graduation audit via the nsu-audit MCP server. Also use when a student asks "can I graduate?", "what courses do I still need?", "how many credits do I have left?", "am I eligible for graduation?", or pastes their transcript.
---

# NSU Graduation Audit Advisor

## What this Skill covers

- NSU grading scale, GPA calculation, and class equivalence
- CSE (Computer Science & Engineering) program requirements → see [cse.md](cse.md)
- MIC (Microbiology) program requirements → see [mic.md](mic.md)
- Course catalog lookup (Spring 2026) → `catalog.json` or `nsu-audit:lookup_course`
- Running a live audit via the **nsu-audit** MCP server

---

## Grading policy (key facts)

| Grade | Points | Notes |
|-------|--------|-------|
| A | 4.0 | 93+ |
| A- | 3.7 | 90–92 |
| B+ | 3.3 | 87–89 |
| B | 3.0 | 83–86 |
| F | 0.0 | Below 60; must retake |
| W / I | 0.0 | Not counted in GPA |

**CGPA class equivalence:** First Class ≥ 3.0 · Second Class 2.5–2.99 · Third Class 2.0–2.49 · Below Standard < 2.0 (ineligible)

Minimum CGPA for graduation: **2.0** (both CSE and MIC).

Retaking: only the **best grade** counts toward CGPA; F stays until replaced.

---

## Course catalog lookup

**If the nsu-audit MCP server is connected**, prefer the MCP tool — it is authoritative and needs no file access:

```
nsu-audit:lookup_course(course_code)
```

**If the MCP server is not connected**, read `catalog.json` directly and search for the course code. The file is a JSON array of valid course code strings (e.g. `"CSE445"`, `"MAT250"`).

---

## Program requirements

For credit breakdowns, course lists, and waiver rules:

- **CSE** (130 credits): see [cse.md](cse.md)
- **MIC** (120 credits): see [mic.md](mic.md)

### Waiver impact on required credits (both programs)

| ENG102 waived | MAT112 waived | CSE required | MIC required |
|---|---|---|---|
| Yes | Yes | 130 | 120 |
| One only | — | 133 | 123 |
| No | No | 136 | 126 |

Waived course credits count in **Credit Completed** but NOT in Credit Counted or CGPA.

---

## Live audit via MCP (nsu-audit server)

When the **nsu-audit** MCP server is connected, use these tools in exact order.

### Supported transcript formats

| Format | Notes |
|--------|-------|
| CSV | Used directly — expected columns: `Course_Code`, `Credits`, `Grade`, `Semester` |
| PDF | Automatically OCR'd server-side (pytesseract + pdf2image) |
| JPEG / PNG / images | Same OCR pipeline as PDF |

**Max file size:** 10 MB. OCR conversion is transparent — the user uploads any supported format and the server converts non-CSV files to CSV before auditing. The same formats work for local file paths (`discover_choices`, `run_audit`) and Google Drive files.

### Local transcript audit

Copy this checklist and check off each step as you complete it:

```
Audit Progress:
- [ ] Step 1: OAuth authenticated (nsu_oauth_start → nsu_oauth_complete)
- [ ] Step 2: discover_choices completed — all questions asked one at a time, answers collected
- [ ] Step 3: run_audit executed with collected answers
- [ ] Step 4: Results interpreted using cse.md or mic.md
```

1. `nsu-audit:nsu_oauth_start` — show `user_code` + `verification_url` to user
2. `nsu-audit:nsu_oauth_complete` — call after user approves in browser
3. `nsu-audit:discover_choices(transcript_path, program)` — ask user EVERY question one at a time
4. `nsu-audit:run_audit(transcript_path, program, answers)` — final audit

### Google Drive transcript audit

Copy this checklist and check off each step as you complete it:

```
Drive Audit Progress:
- [ ] Step 1: OAuth authenticated (nsu_oauth_start → nsu_oauth_complete)
- [ ] Step 2: Drive authorized (gdrive_authorize → gdrive_authorize_complete)
- [ ] Step 3: File selected from gdrive_list_files
- [ ] Step 4: gdrive_discover_choices completed — all questions answered one at a time
- [ ] Step 5: gdrive_download_and_audit executed
- [ ] Step 6: Results interpreted using cse.md or mic.md
```

1. `nsu-audit:nsu_oauth_start` → `nsu-audit:nsu_oauth_complete`
2. `nsu-audit:gdrive_authorize` → open auth_url → `nsu-audit:gdrive_authorize_complete`
3. `nsu-audit:gdrive_list_files` → pick file_id
4. `nsu-audit:gdrive_discover_choices(file_id, program)` → ask questions one at a time
5. `nsu-audit:gdrive_download_and_audit(file_id, program, answers)`

### Email the report (after audit)

1. `nsu-audit:gmail_authorize` → `nsu-audit:gmail_authorize_complete`
2. `nsu-audit:send_audit_report(run_id, to, subject=None)` — `subject` is optional; omit to use the backend's default email subject

### Session management

- `nsu-audit:nsu_current_user` — check who is currently logged in (`GET /api/auth/me`)
- `nsu-audit:nsu_sign_out` — clear the JWT session and log out

### History and past runs

- `nsu-audit:list_audit_history(limit, offset)` — list the user's past audit runs (paginated; `limit` 1–100, default 20)
- `nsu-audit:get_history_run(run_id)` — full details of one historical audit run
- `nsu-audit:get_audit_run(run_id)` — retrieve a specific audit result by its UUID

### Admin (requires admin role)

- `nsu-audit:get_admin_stats` — aggregate stats: total runs, total users, runs by program, average CGPA, average credits, recent runs with user info. Returns **403** for non-admin users.

### No login needed

- `nsu-audit:lookup_course` — validate a course code against the catalog
- `nsu-audit:list_program_requirements` — return structured requirements for CSE or MIC

### Rules — never violate

- Always call `discover_choices` before `run_audit`. Never skip it.
- Ask user questions **one at a time**, in order. Never present all as a bulk list.
- The `selected` field in each choice is the engine's **auto-default**, not the user's answer.
- Never guess or auto-fill answers.
- If any tool raises "Not authenticated", call `nsu-audit:nsu_oauth_start` immediately.

---

## Choice system reference

`discover_choices` and `gdrive_discover_choices` return a `choices` array. Each element has:

| Field | Type | Meaning |
|-------|------|---------|
| `type` | `"yes_no"` or `"pick"` | Waiver toggle vs course selection |
| `key` | string | Answer key — `yn_0`, `yn_1` for waivers; `pick_0`, `pick_1`, … for picks |
| `prompt` | string | Human-readable question text |
| `options` | list of strings | Valid answer values (course codes, `"yes"`/`"no"`, etc.) |
| `display` | list of strings | Formatted display text per option (same order as `options`) |
| `group` | string | Semantic grouping — see table below |
| `label` | string | Short label for the choice |
| `selected` | string | Engine auto-default — **not** the user's answer |

### Answer keys

When passing `answers` to `run_audit` / `gdrive_download_and_audit`, use the exact `key` from each choice:

```
{ "yn_0": "yes", "yn_1": "no", "pick_0": "CSE445", "pick_1": "CSE419", ... }
```

### Choice groups by program

| Group | Program | What it asks |
|-------|---------|--------------|
| `ged_core` | CSE only | POL101/POL104, ECO101/ECO104, SOC101/ENV203/GEO205/ANT101 — one per group |
| `mic_core` | MIC only | Language (BEN205/ENG111), Humanities, Social Science, Science pair (BIO103+L or PHY107+L) |
| `trail` | CSE only | Which of the 6 trails to select from |
| `trail_course` | CSE only | Specific courses from the chosen trails |
| `bio_internship` | CSE only | BIO103L vs CSE498R/CSE498I (1-credit slot) |
| `major_elective` | Both | Major elective course picks |
| `open_elective` | CSE only | One 3-credit open elective slot |
| `free_elective` | MIC only | Three 3-credit free elective slots (any NSU course) |
| `minor_declare` | CSE only | Minor program declaration |

### Rediscovery (CSE trail changes)

When the user changes a **trail** answer, downstream `trail_course` and `open_elective` options become stale. Call `discover_choices` again with **only the trail answers** to refresh those options. The WEB and CLI both do this automatically; in MCP, you must re-call `discover_choices` with partial `answers` containing only the `trail`-group keys.

---

## CSE vs MIC during audit

Both programs share the same transcript upload and OCR pipeline — differences are entirely in the audit engine and what choices/results appear.

| Aspect | CSE | MIC |
|--------|-----|-----|
| Total credits | 130 | 120 |
| Elective structure | 6 named trails; pick 2 from one trail + 1 from another (9cr) + 1 open elective (3cr) | Flat list; pick 3 major electives (9cr) + 3 free electives from any NSU course (9cr) |
| Choice groups seen | `ged_core`, `trail`, `trail_course`, `bio_internship`, `open_elective`, `major_elective`, `minor_declare` | `mic_core`, `major_elective`, `free_elective` |
| Minor programs | Detected automatically from transcript; reported in `minor_programs` | Not applicable — `minor_programs` is always empty |
| BIO103L / Internship slot | 1-credit slot: BIO103L **or** CSE498R / CSE498I | No equivalent slot |
| CGPA exclusions | MAT116 excluded (0-credit, prereq only) | None |
| Core choice resolution | GED choice groups — 3 one-of pairs (POL, ECO, SOC/ENV/GEO/ANT) | MIC core choices (language, humanities, social, science pair) + SHLS alias pairs (BIO201↔MIC110, BIO202↔MIC101, etc.) |
| Elective label in results | "Open Elective" for the single open slot | "Free Elective" for all three free slots |

---

## Interpreting audit results

The `result` object returned by `run_audit` / `gdrive_download_and_audit` contains:

### Top-level fields

| Field | Type | Meaning |
|-------|------|---------|
| `credit_completed` | number | Total credits including waivers |
| `credit_counted` | number | Credits counted toward graduation (excludes waived, excluded, not-counted) |
| `credit_passed` | number | Credits with a passing grade |
| `required_credits` | number | Program requirement (130 CSE / 120 MIC, adjusted for waivers) |
| `cgpa` | number | Cumulative GPA |
| `academic_standing` | string | "First Class", "Second Class", "Third Class", or "Below Standard" |
| `grade_points` | number | Total grade points earned |
| `waived_courses` | list | Course codes that were waived (e.g. `["ENG102", "MAT112"]`) |
| `waiver_notes` | list | Explanatory notes about each waiver |
| `major_electives` | list | Selected major/trail elective course codes |
| `open_elective` | string or null | The single open elective (CSE) or first free elective (MIC) |
| `free_electives` | list | Additional free elective codes (MIC: up to 2 more; CSE: empty) |
| `minor_programs` | list | CSE only — detected minor programs (see below); empty for MIC |
| `per_course_detail` | list | Per-course breakdown (see below) |

### `per_course_detail` entries

Each entry in `per_course_detail`:

| Field | Meaning |
|-------|---------|
| `course` | Course code |
| `credits` | Credit value |
| `grade` | Letter grade |
| `status` | `"Counted"`, `"Counted  [Open Elective]"`, `"Counted  [Free Elective]"`, `"Counted  [Major Elective]"`, or `"Not Counted"` |
| `reason` | Why not counted (e.g. "Retake – lower grade", "Not in curriculum", "Prerequisite not met") — only for not-counted courses |

### `minor_programs` entries (CSE only)

| Field | Meaning |
|-------|---------|
| `name` | Minor program name |
| `credits` | Total credits in the minor |
| `complete` | `true` if all minor requirements are met |
| `core_courses` | Courses counted as minor core |
| `declared_courses` | Courses declared toward the minor |
| `choice_slot` | Optional choice slot within the minor |
| `open_elective` | Open elective course allocated to the minor |

### `deficiency` object

| Field | Meaning |
|-------|---------|
| `eligible` | `true` = meets all graduation requirements |
| `credit_shortfall` | Credits still needed (0 if eligible) |
| `probation` | CGPA < 2.0 — ineligible regardless of credits |
| `missing_mandatory` | List of unfulfilled required course categories |
| `prereq_failures_list` | Courses taken without completing prerequisites |
| `retake_note` | Note about courses that need retaking (F grades) |

Use [cse.md](cse.md) or [mic.md](mic.md) to explain what each missing category means to the student.

---

## Limits and operational notes

- **Rate limit:** 5 saved audit runs per 60 seconds per user. Preview/discover calls (`save=false`) do not count against this limit.
- **`save` parameter:** `discover_choices` always uses `save=false` (preview only). `run_audit` defaults to `save=true` (persists the run to history).
- **`source` field:** Each audit run is tagged with its origin — `web`, `mcp`, `cli`, or `ios`. This appears in history and admin stats.
