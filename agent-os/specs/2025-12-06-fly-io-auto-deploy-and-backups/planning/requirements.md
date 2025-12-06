# Spec Requirements: Fly.io Auto-Deploy and Database Backups

## Initial Description
1. Auto-deploy to fly.io on commit to main, EXCEPT on auto commit to main on persona creation
2. Decide on a way to backup the database occasionally - investigate if fly.io has anything we can use

## Requirements Discussion

### First Round Questions

**Q1:** What CI/CD system should be used?
**Answer:** GitHub Actions

**Q2:** What should trigger deployments?
**Answer:** On commit to main with tests passing

**Q3:** How should persona-related commits be identified for skipping deployment?
**Answer:** Use commit message pattern (e.g., "Create persona:", "Delete persona:", etc.)

**Q4:** How should credentials be handled?
**Answer:** Needs guidance on setting up Fly.io API token

**Q5:** What backup approach should be used?
**Answer:** Prefers backing up the database to Google Drive (not Fly.io volume snapshots)

**Q6:** What retention policy for backups?
**Answer:** N/A (using Google Drive approach - managed by Google Drive storage)

**Q7:** What level of monitoring/alerting is needed?
**Answer:** Configure and forget

**Q8:** Anything out of scope?
**Answer:** N/A

### Existing Code to Reference
No similar existing features identified for reference.

### Follow-up Questions

**Follow-up 1:** What authentication method for Google Drive?
**Answer:** Service Account

**Follow-up 2:** How often should backups run?
**Answer:** Daily

**Follow-up 3:** Where should the backup process be triggered from?
**Answer:** GitHub Actions with scheduled cron job (recommended approach)

**Follow-up 4:** Comfortable with SSH/sftp access to Fly.io machine for backup retrieval?
**Answer:** Yes

**Follow-up 5:** What level of setup documentation needed?
**Answer:** Steps only, no documentation files to be created

## Visual Assets

### Files Provided:
No visual assets provided.

### Visual Insights:
N/A

## Requirements Summary

### Functional Requirements

**Auto-Deploy:**
- GitHub Actions workflow triggered on commits to main branch
- Tests must pass before deployment proceeds
- Automatic deployment to Fly.io using flyctl
- Skip deployment for persona-related commits (pattern matching on commit message)

**Database Backups:**
- Daily automated backups of SQLite database
- Backup triggered via GitHub Actions scheduled cron job
- Use SSH/sftp to retrieve database from Fly.io machine
- Upload backup to Google Drive using Service Account authentication
- "Configure and forget" approach - minimal ongoing maintenance

### Reusability Opportunities
- Existing Fly.io deployment configuration (`fly.toml`)
- Existing test suite (pytest)

### Scope Boundaries
**In Scope:**
- GitHub Actions CI/CD workflow for auto-deploy
- Automated deployment to Fly.io
- Commit message pattern detection for skipping persona commits
- GitHub Actions scheduled workflow for daily backups
- SSH/sftp connection to Fly.io to retrieve database
- Google Drive Service Account setup and upload
- Fly.io API token setup guidance (steps provided, no docs files)

**Out of Scope:**
- None specified

### Technical Considerations
- Database is SQLite stored on Fly.io persistent volume (`data/prism.db`)
- Fly.io is already configured for deployment
- pytest is used for testing
- Commit messages for persona operations follow patterns like "Create persona:", "Delete persona:"
- Google Drive Service Account requires credentials JSON file
- SSH keys needed for Fly.io machine access from GitHub Actions
- Cron schedule for daily backup (specific time TBD during implementation)

## Final Decisions Summary

| Decision Area | Choice |
|---------------|--------|
| CI/CD Platform | GitHub Actions |
| Deploy Trigger | Commit to main with passing tests |
| Skip Deploy Logic | Commit message pattern matching |
| Backup Destination | Google Drive |
| Backup Auth | Service Account |
| Backup Frequency | Daily |
| Backup Trigger | GitHub Actions scheduled cron job |
| Database Retrieval | SSH/sftp to Fly.io machine |
| Monitoring Level | Configure and forget |
| Documentation | Steps only (no doc files) |
