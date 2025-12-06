# Tech Stack

## Runtime

### Python 3.11+

**Role:** Primary programming language

**Rationale:** Modern Python with excellent async/await support, type hints, and a mature ecosystem for Discord bot development. The 3.11+ requirement ensures access to performance improvements and language features like exception groups.

## Discord Integration

### Pycord

**Role:** Discord API wrapper

**Rationale:** Modern, actively maintained Discord library with native slash command support, good async patterns, and comprehensive Discord API coverage. Chosen over discord.py for its continued development and feature parity.

## Data Storage

### SQLite

**Role:** Primary database

**Rationale:** Zero-configuration, file-based database ideal for a single-instance personal project. Provides ACID compliance, good performance for the expected scale, and simple deployment (no separate database server). Data stored in `data/prism.db`.

### TOML Files

**Role:** Persona definitions

**Rationale:** Human-readable configuration format for persona files. Easy to edit manually, version control friendly, and well-supported in Python via the standard library (Python 3.11+).

## HTTP & AI

### httpx

**Role:** HTTP client for API calls

**Rationale:** Modern async HTTP client with excellent API design, HTTP/2 support, and better async patterns than requests. Used for all OpenRouter API communication.

### OpenRouter

**Role:** AI model provider

**Rationale:** Provides access to multiple AI models through a single API, allowing flexibility in model selection. Default model is `google/gemini-2.5-flash` with `google/gemini-2.5-flash-lite` as fallback.

## Deployment

### Fly.io

**Role:** Production hosting

**Rationale:** Simple container-based deployment with good free tier for personal projects. Provides persistent volumes for SQLite database storage, easy secrets management, and straightforward scaling if needed.

### Docker

**Role:** Containerization

**Rationale:** Ensures consistent environment between development and production. Dockerfile defines the runtime environment for Fly.io deployment.

## Development Tools

### pytest

**Role:** Testing framework

**Rationale:** Industry-standard Python testing framework with excellent plugin ecosystem. Used with pytest-asyncio for async test support and pytest-cov for coverage reporting.

### ruff

**Role:** Linting and formatting

**Rationale:** Fast, modern Python linter that combines functionality of multiple tools (flake8, isort, etc.) into a single, performant package.

---

## Future Additions

When implementing the web dashboard (roadmap items 7-10), the following will be added:

- **Flask or FastAPI** - Lightweight web framework for dashboard backend
- **Discord OAuth2** - Authentication via Discord for dashboard access
- **HTML/CSS/JS or htmx** - Frontend for dashboard interface (keeping it simple, no heavy frameworks)
