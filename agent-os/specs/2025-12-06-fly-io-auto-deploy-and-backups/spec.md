# Specification: Fly.io Auto-Deploy and Database Backups

## Goal
Implement automated deployment to Fly.io on commits to main branch (with passing tests), and establish daily database backups to Google Drive using GitHub Actions.

## User Stories
- As a developer, I want code merged to main to automatically deploy so that production stays current without manual intervention
- As an operator, I want daily database backups stored in Google Drive so that data is recoverable without ongoing maintenance

## Specific Requirements

**GitHub Actions Deploy Workflow**
- Trigger on push to `main` branch
- Run pytest test suite before deployment proceeds
- Fail fast if tests do not pass (do not deploy)
- Use `flyctl deploy` command for deployment
- Store `FLY_API_TOKEN` as GitHub Actions secret
- Use official `superfly/flyctl-actions` for Fly.io CLI setup

**Persona Commit Skip Logic**
- Parse commit message to detect persona-related operations
- Skip deployment for commits matching patterns: `Create persona:`, `Delete persona:`
- Use `if` conditional in GitHub Actions job step to check commit message
- Commit message available via `${{ github.event.head_commit.message }}`

**GitHub Actions Backup Workflow**
- Schedule via cron expression (daily, e.g., `0 4 * * *` for 4 AM UTC)
- Allow manual trigger via `workflow_dispatch`
- Separate workflow file from deploy workflow for clarity

**SSH/SFTP Database Retrieval**
- Use Fly.io SSH proxy to access the machine (`fly ssh console` or `fly sftp`)
- Database located at `/data/prism.db` on Fly.io persistent volume
- Generate SSH key pair for GitHub Actions to use
- Store private key as GitHub Actions secret
- Use `fly ssh sftp get /data/prism.db ./prism.db` to download database file

**Google Drive Upload via Service Account**
- Create Google Cloud Service Account with Drive API access
- Store Service Account JSON credentials as GitHub Actions secret (base64 encoded)
- Use Python script or `gdrive` CLI tool for upload
- Name backup files with timestamp (e.g., `prism-backup-2025-12-06.db`)
- Target a specific Google Drive folder (folder ID stored as secret)

**Secrets Configuration**
- `FLY_API_TOKEN` - Fly.io API token for deployments
- `GOOGLE_DRIVE_CREDENTIALS` - Base64-encoded Service Account JSON
- `GOOGLE_DRIVE_FOLDER_ID` - Target folder ID for backups
- Fly.io SSH access uses `fly ssh` which authenticates via `FLY_API_TOKEN`

## Visual Design
No visual assets provided.

## Existing Code to Leverage

**`/var/home/jako/Projects/prism/fly.toml`**
- App name: `prism-discord-bot`, region: `iad`
- Database path configured as `PRISM_DB_PATH = "/data/prism.db"`
- Volume mount: `prism_data` at `/data`
- Already configured for deployment with `flyctl deploy`

**`/var/home/jako/Projects/prism/Dockerfile`**
- Multi-stage build with Python 3.11-slim
- Git installed for persona sync feature
- Copies `prism/` and `personas/` directories
- Entry point: `python -m prism`

**`/var/home/jako/Projects/prism/pytest.ini`**
- Test directory: `tests/`
- Uses pytest-asyncio with auto mode
- Coverage configured for `prism` package
- Run command: `pytest` or `uv run pytest`

**Existing Commit Message Patterns (from git history)**
- `Create persona: <name>.toml` - used when creating personas via Discord
- `Delete persona: <name>.toml` - used when deleting personas via Discord
- These patterns should be matched to skip deployment

**`/var/home/jako/Projects/prism/pyproject.toml`**
- Project uses `uv` as package manager (uv.lock present)
- pytest and dev dependencies defined in `[dependency-groups]`
- Python version: `>=3.11`

## Out of Scope
- Fly.io volume snapshots (using Google Drive instead)
- Backup retention policy management (Google Drive handles storage)
- Monitoring or alerting dashboards
- Rollback automation on failed deploys
- Multi-environment deployments (staging/production)
- Backup encryption beyond Google Drive's built-in security
- Database restoration automation (manual restore acceptable)
- Slack/Discord notifications for deploy/backup status
- Creating documentation markdown files (steps provided inline only)
- Backup verification or integrity checks
