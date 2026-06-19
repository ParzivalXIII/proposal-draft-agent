# Proposal Draft Agent

AI-powered proposal generation system that transforms client briefs into professional technical proposals with automated critique, refinement, and client-facing brief cards.

## Overview

This application streamlines the proposal creation process by:

1. **Accepting client briefs** - Capture problem statements and rough scope from clients
2. **Generating technical proposals** - LLM drafts comprehensive solutions with feature breakdowns
3. **Auto-critique and refinement** - Multi-pass review loop improves proposal quality
4. **Creating client brief cards** - Non-technical summaries for client communication
5. **Real-time status tracking** - Live updates via HTMX polling

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend                             │
│  Jinja2 + HTMX + Alpine.js + daisyUI 5 (Tailwind CSS v4)   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────────┐  │
│  │   UI     │  │   API    │  │   LangGraph Pipeline     │  │
│  │ Routers  │  │ Routers  │  │  (Draft → Critique →     │  │
│  │          │  │          │  │   Refine → Calculate)    │  │
│  └──────────┘  └──────────┘  └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Background Workers                        │
│              ARQ (Async Redis Queue) + Redis                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Data Layer                              │
│         SQLModel + SQLite (aiosqlite) + nh3 (XSS safe)      │
└─────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | FastAPI, Uvicorn, Pydantic v2 |
| **Database** | SQLite via aiosqlite, SQLModel ORM |
| **AI/ML** | LangGraph, LangChain, OpenAI-compatible API |
| **Task Queue** | ARQ with Redis |
| **Frontend** | Jinja2 templates, HTMX, Alpine.js |
| **Styling** | daisyUI 5, Tailwind CSS v4 |
| **Security** | nh3 (HTML sanitization) |
| **Python** | 3.11+ |

## Features

### Proposal Generation Pipeline

The core LangGraph pipeline follows this flow:

```
Brief Input → Draft Proposal → Critique → Refine (if needed) → Calculate Metrics → Final Proposal
                              ↑_________↓
                              (up to 2 iterations)
```

- **Draft**: LLM generates initial proposal with client summary, technical approach, and feature breakdown
- **Critique**: LLM reviews the draft for clarity, completeness, and quality
- **Refine**: LLM improves the proposal based on critique feedback
- **Calculate**: Python computes total hours and complexity tier (Low/Medium/High/Enterprise)

### Client Brief Cards

After proposal generation, a separate worker creates a **Client Brief Card** - a non-technical, client-friendly summary that:
- Uses plain language (no jargon)
- Focuses on business value and outcomes
- Includes timeline and next steps
- Formatted as clean Markdown

### UI Features

- **Responsive design** - Works on mobile, tablet, and desktop
- **Dark mode** - Toggle with cookie persistence
- **Real-time updates** - HTMX polling (3s for list, 2s for detail)
- **Modal form** - Clean proposal creation interface
- **Expandable cards** - View details without leaving the list
- **Copy to clipboard** - One-click brief card export
- **Regenerate** - Re-run generation for failed proposals
- **Delete** - Remove proposals with confirmation
- **Toast notifications** - Feedback for user actions
- **Progressive validation** - Client-side form validation with Alpine.js

## Prerequisites

- **Python 3.11+** - Use `uv` for dependency management
- **Node.js 18+** - For Tailwind CSS compilation
- **Docker** - For Redis (or install Redis locally)
- **OpenAI API key** - Or any OpenAI-compatible API (e.g., Featherless.ai, Ollama)

## Setup

### 1. Clone and Install

```bash
git clone <repository-url>
cd proposal-draft-agent

# Install Python dependencies
uv sync

# Install Node dependencies (Tailwind CSS)
npm install
```

### 2. Configure Environment

Create a `.env` file:

```bash
# Required: OpenAI API configuration
OPENAI_API_KEY=your-api-key-here

# Optional: Custom API endpoint (e.g., local proxy, Ollama)
OPENAI_BASE_URL=https://api.openai.com/v1
# OPENAI_BASE_URL=http://localhost:11434/v1  # Ollama example

# Optional: Model selection
LLM_MODEL_NAME=gpt-4o-mini

# Redis configuration
REDIS_HOST=localhost
REDIS_PORT=6380
```

### 3. Start Redis

```bash
docker compose up -d
```

This starts Redis on port 6380 (mapped from container port 6379).

### 4. Build CSS

```bash
npm run build:css
```

For development with auto-rebuild:

```bash
npm run watch:css
```

### 5. Initialize Database

The database is created automatically on first run. No migrations needed.

## Running the Application

### Start the Web Server

```bash
uv run uvicorn backend.main:app --reload --port 8000
```

### Start the Background Worker

In a separate terminal:

```bash
uv run arq backend.workers.worker.WorkerSettings
```

### Access the Application

- **Web UI**: http://localhost:8000/ui/
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## API Endpoints

### Proposal Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/proposals` | Create a new proposal |
| `GET` | `/api/proposals/{id}` | Get proposal details |
| `POST` | `/api/proposals/{id}/regenerate` | Regenerate a failed proposal |
| `DELETE` | `/api/proposals/{id}` | Delete a proposal |

### UI Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/ui/` | Proposal list page |
| `POST` | `/ui/proposals` | Create proposal (form submission) |
| `GET` | `/ui/proposals/{id}` | Proposal detail page |
| `DELETE` | `/ui/proposals/{id}` | Delete proposal (UI action) |
| `GET` | `/ui/proposals/fragment` | HTMX fragment: proposal list |
| `GET` | `/ui/proposals/{id}/fragment` | HTMX fragment: proposal status |

### Example: Create a Proposal

```bash
curl -X POST http://localhost:8000/api/proposals \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "Acme Corp",
    "problem_description": "We need to automate our manual invoicing process",
    "rough_scope": "Build an invoicing system with PDF generation and email delivery"
  }'
```

Response:

```json
{
  "id": "abc123...",
  "status": "queued",
  "client_name": "Acme Corp",
  "created_at": "2026-06-19T12:00:00Z"
}
```

## Configuration

All configuration is managed via environment variables (see `.env`):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | - | API key for LLM provider |
| `OPENAI_BASE_URL` | No | `https://api.openai.com/v1` | Custom API endpoint |
| `LLM_MODEL_NAME` | No | `gpt-4o-mini` | Model to use for generation |
| `REDIS_HOST` | No | `localhost` | Redis host |
| `REDIS_PORT` | No | `6380` | Redis port |
| `DATABASE_URL` | No | `sqlite+aiosqlite:///./proposal_agent.db` | Database connection string |

## Project Structure

```
proposal-draft-agent/
├── backend/
│   ├── core/
│   │   ├── config.py          # Pydantic settings
│   │   └── db.py              # Database connection
│   ├── models/
│   │   ├── db_models.py       # SQLModel ORM models
│   │   └── schemas.py         # Pydantic schemas
│   ├── routers/
│   │   ├── api.py             # REST API endpoints
│   │   └── ui.py              # Web UI endpoints
│   ├── templates/
│   │   ├── base.html          # Base template
│   │   ├── index.html         # Proposal list
│   │   ├── detail.html        # Proposal detail
│   │   └── fragments/         # HTMX fragments
│   ├── workers/
│   │   └── worker.py          # ARQ background workers
│   ├── graph.py               # LangGraph pipeline
│   └── main.py                # FastAPI app entry
├── static/
│   └── css/
│       ├── input.css          # Tailwind source
│       └── output.css         # Compiled CSS
├── tests/
│   ├── test_graph.py          # LangGraph tests
│   └── test_smoke.py          # Playwright smoke tests
├── docker-compose.yml         # Redis service
├── pyproject.toml             # Python dependencies
├── package.json               # Node dependencies
└── .env                       # Environment variables
```

## Development

### Running Tests

```bash
# Unit tests
uv run pytest tests/

# Playwright smoke tests (requires running server)
uv run pytest tests/test_smoke.py --headed
```

### CSS Development

The project uses Tailwind CSS v4 with daisyUI 5. The CSS is compiled from `static/css/input.css`:

```bash
# One-time build
npm run build:css

# Watch mode (auto-rebuild on changes)
npm run watch:css
```

### Database

The application uses SQLite for simplicity. The database file is created automatically:

```bash
# Database location
./proposal_agent.db
```

To reset the database:

```bash
rm proposal_agent.db
# Restart the server to recreate tables
```

### Adding New Features

1. **New API endpoint**: Add to `backend/routers/api.py`
2. **New UI page**: Add route to `backend/routers/ui.py`, create template in `backend/templates/`
3. **New database model**: Add to `backend/models/db_models.py`, update schemas in `backend/models/schemas.py`
4. **New background task**: Add function to `backend/workers/worker.py`, register in `WorkerSettings`

## Security

- **HTML Sanitization**: All LLM-generated Markdown is sanitized with `nh3` before rendering to prevent XSS attacks
- **Input Validation**: Pydantic schemas validate all API inputs
- **No Authentication**: This is a single-user tool. Add authentication if deploying publicly.

## Troubleshooting

### Worker Not Processing Jobs

Ensure Redis is running and the worker is started:

```bash
docker compose ps  # Check Redis
uv run arq backend.workers.worker.WorkerSettings  # Start worker
```

### CSS Not Updating

Rebuild the CSS:

```bash
npm run build:css
```

### Database Errors

Delete and recreate the database:

```bash
rm proposal_agent.db
uv run uvicorn backend.main:app --reload
```

### Port Conflicts

If port 8000 or 6380 is in use, update the configuration:

```bash
# Change web server port
uv run uvicorn backend.main:app --port 8001

# Change Redis port in docker-compose.yml and .env
```

## License

This project is provided as-is for educational and demonstration purposes.

## Contributing

This is a personal project, but suggestions and feedback are welcome via issues.

---

**Built with FastAPI, LangGraph, and daisyUI 5**
