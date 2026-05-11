<p align="center">
  <img src="Pictures/Logo.png" width="200" alt="NSU Audit Logo" />
</p>

<h1 align="center">NSU Audit</h1>

<p align="center">
  <strong>Degree Audit System for North South University</strong><br/>
  A full-stack platform that parses student transcripts, evaluates graduation eligibility against official program requirements, and delivers detailed audit reports — through a web app, a native iOS app, a CLI, or directly inside an AI assistant via MCP.
</p>

<p align="center">
  <code>FastAPI</code> &middot; <code>React</code> &middot; <code>PostgreSQL</code> &middot; <code>SwiftUI</code> &middot; <code>MCP (Model Context Protocol)</code> &middot; <code>Docker</code>
</p>

---

## Table of Contents

- [What It Does](#what-it-does)
- [Architecture](#architecture)
- [Screenshots](#screenshots)
  - [Web Application](#web-application)
  - [iOS Application](#ios-application)
  - [MCP Integration (Claude)](#mcp-integration-claude)
- [Tech Stack](#tech-stack)
- [MCP Server](#mcp-server)
  - [Hosted MCP (Streamable HTTP)](#hosted-mcp-streamable-http)
  - [Available MCP Tools](#available-mcp-tools)
  - [Claude Skill](#claude-skill)
- [Audit Engine](#audit-engine)
- [API Endpoints](#api-endpoints)

---

## What It Does

North South University students can upload their official transcript (PDF or CSV), and the system will:

1. **Parse the transcript** using OCR (Tesseract + OpenCV) or direct CSV ingestion.
2. **Run a multi-layered audit** against the official CSE (130 cr) and MIC (120 cr) program requirements, including prerequisite checks, elective trail validation, waiver handling, GPA classification, and retake policy enforcement.
3. **Determine graduation eligibility** and produce a detailed breakdown: credits completed vs. required, CGPA with class standing, course-by-course analysis, deficiency lists, and waiver notes.
4. **Export results** as CSV, printable PDF, or a structured Excel report emailed directly to the student.

All of this is accessible from four different interfaces, each backed by the same audit engine and API:

| Interface | Description |
|-----------|-------------|
| **Web App** | React SPA with Google OAuth, dark-themed UI, step-by-step audit wizard, history, and admin dashboard |
| **iOS App** | Native SwiftUI client with the same feature set, built for iPhone |
| **CLI** | Terminal-based client using Typer and Rich for interactive audits |
| **MCP Server** | Exposes the audit engine as tools for AI assistants (Claude, etc.) with Google Drive and Gmail integration |

---

## Architecture

```
                           +------------------+
                           |   PostgreSQL 16  |
                           +--------+---------+
                                    |
              +---------------------+---------------------+
              |                                           |
    +---------+---------+                     +-----------+----------+
    |   FastAPI Backend |-------- MCP --------|  MCP Server (FastMCP)|
    |  (Audit Engine +  |   /mcp/mcp          |  Google Drive, Gmail |
    |   Auth + Admin)   |   Streamable HTTP   |  Audit Tools         |
    +---------+---------+                     +----------------------+
              |
    +---------+---------+-----------+
    |                   |           |
+---+----+       +------+---+  +---+---+
| React  |       | iOS App  |  |  CLI  |
| (Nginx)|       | (SwiftUI)|  |(Typer)|
+--------+       +----------+  +-------+
```

The entire stack (API + frontend + database) runs as a single `docker compose up` command. An ngrok tunnel can expose it publicly so the hosted MCP endpoint is reachable by cloud-based AI clients like Claude.

---

## Screenshots

### Web Application

<table>
  <tr>
    <td width="50%">
      <img src="Screenshots/website%20sign%20in%20page.png" alt="Sign In Page" />
      <p align="center"><em>Sign in with your @northsouth.edu Google account</em></p>
    </td>
    <td width="50%">
      <img src="Screenshots/website%20dashboard.png" alt="Dashboard" />
      <p align="center"><em>Dashboard with recent audit runs and quick navigation</em></p>
    </td>
  </tr>
  <tr>
    <td colspan="2">
      <img src="Screenshots/website%20audit%20result%20preview.png" alt="Audit Result" />
      <p align="center"><em>Audit report: eligibility status, CGPA, credit breakdown, waivers, and export options</em></p>
    </td>
  </tr>
</table>

### iOS Application

<table>
  <tr>
    <td width="33%">
      <img src="Screenshots/ios%20sign%20in%20page.png" alt="iOS Sign In" />
      <p align="center"><em>Native sign-in with North South account</em></p>
    </td>
    <td width="33%">
      <img src="Screenshots/ios%20dashboard.png" alt="iOS Dashboard" />
      <p align="center"><em>Dashboard on iPhone</em></p>
    </td>
    <td width="33%">
      <img src="Screenshots/ios%20aduit%20result%20preview.png" alt="iOS Audit Result" />
      <p align="center"><em>Audit result with full summary</em></p>
    </td>
  </tr>
</table>

### MCP Integration (Claude)

The MCP server allows AI assistants to perform audits conversationally. A single prompt like *"Locate the most recent transcript in my Google Drive, perform an audit on it, and email the findings"* triggers a multi-step orchestration: authenticate, search Drive, download the file, run the audit, and send the report via Gmail.

<table>
  <tr>
    <td width="50%">
      <img src="Screenshots/mcp%20prompt%20example.png" alt="MCP Prompt" />
      <p align="center"><em>Natural language prompt triggers multi-service orchestration</em></p>
    </td>
    <td width="50%">
      <img src="Screenshots/mcp%20result%20example.png" alt="MCP Result" />
      <p align="center"><em>Full audit results delivered inline with email report sent</em></p>
    </td>
  </tr>
  <tr>
    <td colspan="2">
      <img src="Screenshots/SKILL%20for%20MCP.png" alt="Claude Skill" />
      <p align="center"><em>Claude Skill with NSU program knowledge for context-aware auditing</em></p>
    </td>
  </tr>
</table>

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend API** | Python 3.12, FastAPI, SQLAlchemy (async), Alembic, Uvicorn |
| **Audit Engine** | Custom Python pipeline (`audit_l1.py`, `audit_l2.py`, `audit_l3.py`) |
| **Transcript OCR** | Tesseract, Poppler, OpenCV, Pillow, pdf2image |
| **Database** | PostgreSQL 16 (Alpine) |
| **Frontend** | React 18, TypeScript, Material UI 5, Zustand, Vite, Nginx |
| **iOS App** | SwiftUI, native Google Sign-In (PKCE) |
| **CLI** | Typer, Rich, Questionary, HTTPX |
| **MCP Server** | FastMCP 2.x, Streamable HTTP transport |
| **Auth** | Google OAuth 2.0 (web, CLI device-flow, iOS PKCE), session cookies, JWT |
| **Containerization** | Docker multi-stage builds, Docker Compose |
| **Tunneling** | ngrok (for exposing MCP to cloud AI clients) |

---

## MCP Server

The audit system exposes a full set of MCP tools that any compatible AI client can use. The server supports both hosted (HTTP) and local (stdio) transports.

**Important:** This project is not deployed on a permanent server. The entire stack runs locally via Docker Compose and is exposed through an ngrok tunnel. It is only live when the developer is actively running it. There is no 24/7 hosted instance.

**Google OAuth restriction:** Because the Google Cloud project is in development/testing mode, only pre-approved Google accounts can authenticate. If you want to use the MCP server or web app, you need to provide your Google email address so it can be added to the authorized test users list in the Google Cloud Console.

### Hosted MCP (Streamable HTTP)

The MCP server is mounted directly into the FastAPI app at `/mcp/mcp`. When the Docker stack is running behind ngrok, any MCP client can connect:

```json
{
  "mcpServers": {
    "nsu-audit": {
      "url": "https://your-subdomain.ngrok-free.dev/mcp/mcp"
    }
  }
}
```

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `nsu_oauth_start` | Initiate Google OAuth device-flow login |
| `nsu_oauth_exchange` | Complete the OAuth exchange |
| `run_audit` | Parse a transcript and run the full graduation audit |
| `lookup_course` | Query the NSU course catalog |
| `gdrive_authorize` | Authorize read-only Google Drive access |
| `gdrive_list_files` | Search and list files in the user's Drive |
| `gdrive_download` | Download a file from Drive |
| `gmail_authorize` | Authorize Gmail send access |
| `gmail_send_report` | Email an Excel audit report to any address |

### Claude Skill

The `nsu-audit-skill/` directory contains a Claude Skill that bundles NSU program requirements (CSE and MIC), the grading policy, and the course catalog. When installed alongside the MCP server, Claude can answer questions about graduation requirements and run audits with full institutional context.

---

## Audit Engine

The audit runs through a three-level pipeline:

| Level | File | Responsibility |
|-------|------|---------------|
| **L1** | `audit_l1.py` | Core credit counting, GPA calculation, grade classification, credit-hour validation against program minimums |
| **L2** | `audit_l2.py` | Elective trail verification, major/open elective mapping, waiver application, 1-credit slot handling |
| **L3** | `audit_l3.py` | Prerequisite chain validation, retake policy enforcement, final eligibility determination |

The pipeline is orchestrated by `run_pipeline.py`, which chains the three levels and produces a single JSON result object consumed by all interfaces.

Transcript parsing (`transcript_to_csv.py`) handles PDF-to-CSV conversion using Tesseract OCR with OpenCV preprocessing for accurate text extraction from scanned documents.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/auth/callback` | Google OAuth callback (web) |
| `POST` | `/api/auth/device/start` | Start device-flow auth (CLI/MCP) |
| `POST` | `/api/auth/device/exchange` | Exchange device code for session |
| `GET` | `/api/auth/me` | Current user info |
| `POST` | `/api/auth/logout` | End session |
| `POST` | `/api/audit/run` | Upload transcript and run audit |
| `GET` | `/api/history/` | List past audits (paginated) |
| `GET` | `/api/history/:id` | Get a specific audit result |
| `GET` | `/api/admin/stats` | Platform-wide statistics |
| `GET` | `/api/gdrive/authorize/start` | Start Google Drive OAuth |
| `GET` | `/api/gdrive/files` | Search user's Drive files |
| `GET` | `/api/gdrive/files/:id/download` | Download a Drive file |
| `GET` | `/api/gmail/authorize/start` | Start Gmail OAuth |
| `POST` | `/api/gmail/send-report` | Email an audit report |
| `POST` | `/mcp/mcp` | MCP Streamable HTTP endpoint |

Full interactive documentation is available at `/api/docs` (Swagger UI) when the server is running.
