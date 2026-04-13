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
2. `nsu-audit:send_audit_report(run_id, to)`

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

## Interpreting audit results

The `deficiency` object in audit output:

| Field | Meaning |
|-------|---------|
| `eligible` | `true` = meets all graduation requirements |
| `credit_shortfall` | Credits still needed (0 if eligible) |
| `probation` | CGPA < 2.0 — ineligible regardless of credits |
| `missing_mandatory` | List of unfulfilled required course categories |
| `prereq_failures_list` | Courses taken without completing prerequisites |

Use [cse.md](cse.md) or [mic.md](mic.md) to explain what each missing category means to the student.
