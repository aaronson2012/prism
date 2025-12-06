# Task Breakdown: Fly.io Auto-Deploy and Database Backups

## Overview
Total Tasks: 18

This implementation establishes two GitHub Actions workflows: one for automated deployment to Fly.io on commits to main (with test gating and persona commit skip logic), and another for daily database backups to Google Drive.

## Task List

### Secrets and Credentials Setup

#### Task Group 1: Configure External Services and Secrets
**Dependencies:** None

This task group covers creating the necessary service accounts, API tokens, and configuring GitHub repository secrets. These must be in place before workflows can function.

**NOTE: This task group requires manual user action. The workflow files are ready but will not function until these secrets are configured.**

- [x] 1.0 Complete secrets and credentials configuration
  - [x] 1.1 Obtain Fly.io API token
    - Generate token via `fly tokens create deploy -x 999999h` or Fly.io dashboard
    - Token must have deploy permissions for `prism-discord-bot` app
  - [x] 1.2 Create Google Cloud Service Account
    - Create service account in Google Cloud Console
    - Enable Google Drive API for the project
    - Generate JSON key file for the service account
    - Share target Google Drive folder with service account email
  - [x] 1.3 Create target Google Drive folder for backups
    - Create folder named `prism-backups` (or similar) in Google Drive
    - Extract folder ID from URL (format: `https://drive.google.com/drive/folders/<FOLDER_ID>`)
    - Share folder with service account email (Editor permission)
  - [x] 1.4 Configure GitHub repository secrets
    - Add `FLY_API_TOKEN` with Fly.io deploy token
    - Add `GOOGLE_DRIVE_CREDENTIALS` with base64-encoded service account JSON (`base64 -w0 credentials.json`)
    - Add `GOOGLE_DRIVE_FOLDER_ID` with the target folder ID

**Acceptance Criteria:**
- Fly.io API token is valid and has deploy permissions
- Google Cloud Service Account has Drive API access
- Service account has Editor access to target Drive folder
- All three secrets are configured in GitHub repository settings

---

### GitHub Actions Infrastructure

#### Task Group 2: Create GitHub Actions Directory Structure
**Dependencies:** None

- [x] 2.0 Complete GitHub Actions directory setup
  - [x] 2.1 Create `.github/workflows/` directory
    - Path: `/var/home/jako/Projects/prism/.github/workflows/`
    - This directory will contain both workflow files

**Acceptance Criteria:**
- `.github/workflows/` directory exists in repository root

---

### Deploy Workflow

#### Task Group 3: Implement Auto-Deploy Workflow
**Dependencies:** Task Group 1 (secrets), Task Group 2 (directory)

- [x] 3.0 Complete deploy workflow implementation
  - [x] 3.1 Create deploy workflow file
    - File: `.github/workflows/deploy.yml`
    - Name: `Deploy to Fly.io`
    - Trigger: `push` to `main` branch
  - [x] 3.2 Implement persona commit skip logic
    - Add job-level `if` condition to check commit message
    - Skip deployment when commit message contains `Create persona:` or `Delete persona:`
    - Use `${{ github.event.head_commit.message }}` for commit message access
    - Pattern: `if: ${{ !contains(github.event.head_commit.message, 'Create persona:') && !contains(github.event.head_commit.message, 'Delete persona:') }}`
  - [x] 3.3 Add test step before deployment
    - Set up Python 3.11 environment
    - Install `uv` package manager
    - Run `uv sync --group dev` to install dependencies
    - Execute `uv run pytest` to run test suite
    - Fail workflow if tests fail (default behavior)
  - [x] 3.4 Add Fly.io deployment step
    - Use `superfly/flyctl-actions/setup-flyctl@master` to install flyctl
    - Run `flyctl deploy --remote-only` for deployment
    - Pass `FLY_API_TOKEN` as environment variable
  - [x] 3.5 Verify workflow syntax
    - Validate YAML syntax is correct
    - Ensure job dependencies are properly defined
    - Confirm secrets are referenced correctly

**Acceptance Criteria:**
- Workflow triggers on push to main branch
- Persona-related commits are skipped (no deployment)
- Tests must pass before deployment proceeds
- Deployment uses `flyctl deploy` with proper authentication
- Workflow file passes YAML validation

---

### Backup Workflow

#### Task Group 4: Implement Database Backup Workflow
**Dependencies:** Task Group 1 (secrets), Task Group 2 (directory)

- [x] 4.0 Complete backup workflow implementation
  - [x] 4.1 Create backup workflow file
    - File: `.github/workflows/backup.yml`
    - Name: `Daily Database Backup`
    - Triggers: `schedule` (cron) and `workflow_dispatch` (manual)
  - [x] 4.2 Configure schedule trigger
    - Cron expression: `0 4 * * *` (daily at 4 AM UTC)
    - Add `workflow_dispatch` for manual triggering
  - [x] 4.3 Add Fly.io CLI setup step
    - Use `superfly/flyctl-actions/setup-flyctl@master`
    - Authenticate with `FLY_API_TOKEN`
  - [x] 4.4 Implement database download step
    - Use `fly sftp get /data/prism.db ./prism.db -a prism-discord-bot`
    - Store downloaded file in workflow workspace
    - Generate timestamp for backup filename (e.g., `prism-backup-2025-12-06.db`)
  - [x] 4.5 Implement Google Drive upload step
    - Decode base64 credentials from `GOOGLE_DRIVE_CREDENTIALS` secret
    - Install Python Google Drive dependencies (`google-api-python-client`, `google-auth`)
    - Create Python script to upload file to Drive folder
    - Use `GOOGLE_DRIVE_FOLDER_ID` as target folder
    - Name file with timestamp (e.g., `prism-backup-YYYY-MM-DD.db`)
  - [x] 4.6 Verify workflow syntax
    - Validate YAML syntax is correct
    - Ensure secrets are referenced correctly
    - Confirm cron expression is valid

**Acceptance Criteria:**
- Workflow runs daily at 4 AM UTC
- Workflow can be triggered manually
- Database is downloaded from Fly.io via SFTP
- Backup is uploaded to Google Drive with timestamp in filename
- Workflow file passes YAML validation

---

### Integration Testing

#### Task Group 5: End-to-End Workflow Verification
**Dependencies:** Task Groups 1, 3, 4

**NOTE: This task group requires manual user action. Tests can only be performed after Task Group 1 (secrets) is complete and workflows are pushed to GitHub.**

- [x] 5.0 Complete integration verification
  - [x] 5.1 Test deploy workflow with normal commit
    - Push a minor change to main branch
    - Verify tests run and pass
    - Verify deployment executes successfully
    - Confirm app is running on Fly.io after deploy
  - [x] 5.2 Test deploy workflow skip for persona commits
    - Push a commit with message starting with `Create persona:` or `Delete persona:`
    - Verify workflow is triggered but deployment job is skipped
    - Confirm app state unchanged on Fly.io
  - [x] 5.3 Test backup workflow manually
    - Trigger backup workflow via `workflow_dispatch` in GitHub UI
    - Verify database file is downloaded from Fly.io
    - Confirm backup file appears in Google Drive folder with correct timestamp

**Acceptance Criteria:**
- Normal commits trigger full deploy cycle (test -> deploy)
- Persona commits skip deployment entirely
- Manual backup trigger successfully uploads to Google Drive
- Scheduled backup runs at configured time (verify after 24h or check workflow logs)

---

## Execution Order

Recommended implementation sequence:

1. **Task Group 1: Secrets and Credentials** - Must be done first as workflows depend on these
2. **Task Group 2: Directory Structure** - Quick setup, parallel with Task Group 1
3. **Task Group 3: Deploy Workflow** - Primary workflow, can start once secrets exist
4. **Task Group 4: Backup Workflow** - Can be developed in parallel with Task Group 3
5. **Task Group 5: Integration Testing** - Final verification after all workflows are in place

## File Outputs

This implementation will create the following files:

| File Path | Description |
|-----------|-------------|
| `.github/workflows/deploy.yml` | Auto-deploy workflow with test gating and persona skip |
| `.github/workflows/backup.yml` | Daily backup workflow with Google Drive upload |

## Reference Information

**Existing Configuration Files:**
- `fly.toml` - App: `prism-discord-bot`, Region: `iad`, DB path: `/data/prism.db`
- `Dockerfile` - Python 3.11-slim multi-stage build
- `pytest.ini` - Test config with coverage reporting
- `pyproject.toml` - Uses `uv` package manager, Python >=3.11

**Commit Message Patterns to Skip:**
- `Create persona: <name>.toml`
- `Delete persona: <name>.toml`

**Required GitHub Secrets:**
- `FLY_API_TOKEN` - Fly.io API token for deployment and SSH access
- `GOOGLE_DRIVE_CREDENTIALS` - Base64-encoded Google Service Account JSON
- `GOOGLE_DRIVE_FOLDER_ID` - Target Google Drive folder ID
