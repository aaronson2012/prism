"""Git sync service for auto-committing persona changes to a repository."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class GitSyncConfig:
    """Configuration for git sync."""

    enabled: bool = False
    repo_url: str | None = None  # e.g., https://github.com/user/repo.git
    branch: str = "personas-sync"
    token: str | None = None  # GitHub PAT for authentication
    author_name: str = "Prism Bot"
    author_email: str = "prism-bot@users.noreply.github.com"
    personas_subdir: str = "personas"  # Directory within repo to sync


class GitSyncService:
    """Service for syncing persona files to a git repository."""

    def __init__(self, config: GitSyncConfig, local_personas_dir: str) -> None:
        self.config = config
        self.local_personas_dir = local_personas_dir
        self._repo_dir: str | None = None
        self._lock = asyncio.Lock()

    @property
    def repo_dir(self) -> str:
        """Get the local clone directory."""
        if self._repo_dir is None:
            # Use a temp directory alongside the data dir
            base = os.path.dirname(self.local_personas_dir)
            self._repo_dir = os.path.join(base, ".git-sync-repo")
        return self._repo_dir

    async def _run_git(self, *args: str, cwd: str | None = None) -> tuple[int, str, str]:
        """Run a git command and return (returncode, stdout, stderr)."""
        cmd = ["git"] + list(args)
        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = self.config.author_name
        env["GIT_AUTHOR_EMAIL"] = self.config.author_email
        env["GIT_COMMITTER_NAME"] = self.config.author_name
        env["GIT_COMMITTER_EMAIL"] = self.config.author_email

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd or self.repo_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode or 0, stdout.decode(), stderr.decode()

    def _get_authenticated_url(self) -> str | None:
        """Get repo URL with authentication token embedded."""
        if not self.config.repo_url:
            return None
        url = self.config.repo_url
        if self.config.token and url.startswith("https://"):
            # Insert token into URL: https://TOKEN@github.com/...
            url = url.replace("https://", f"https://{self.config.token}@", 1)
        return url

    async def initialize(self) -> bool:
        """Clone or update the repository. Returns True if successful."""
        if not self.config.enabled or not self.config.repo_url:
            log.info("Git sync is disabled or no repo URL configured")
            return False

        async with self._lock:
            url = self._get_authenticated_url()
            if not url:
                return False

            # Check if git is available
            ret, _, _ = await self._run_git("--version", cwd="/tmp")
            if ret != 0:
                log.error("Git is not available - git sync disabled")
                return False

            if os.path.isdir(os.path.join(self.repo_dir, ".git")):
                # Repo exists, fetch and reset
                log.info("Updating existing git sync repo")
                ret, _, err = await self._run_git("fetch", "origin", self.config.branch)
                if ret != 0:
                    # Branch might not exist yet, that's okay
                    log.debug("Fetch failed (branch may not exist): %s", err)
                # Try to checkout the branch
                ret, _, _ = await self._run_git("checkout", self.config.branch)
                if ret != 0:
                    # Create the branch if it doesn't exist
                    ret, _, err = await self._run_git("checkout", "-b", self.config.branch)
                    if ret != 0:
                        log.warning("Could not checkout branch: %s", err)
            else:
                # Clone fresh
                os.makedirs(self.repo_dir, exist_ok=True)
                log.info("Cloning git sync repo to %s", self.repo_dir)
                ret, _, err = await self._run_git(
                    "clone",
                    "--depth=1",
                    "--single-branch",
                    "-b",
                    self.config.branch,
                    url,
                    self.repo_dir,
                    cwd="/tmp",
                )
                if ret != 0:
                    # Branch might not exist, clone default and create branch
                    log.info("Branch doesn't exist, cloning default branch")
                    # Remove partial clone if exists
                    if os.path.exists(self.repo_dir):
                        shutil.rmtree(self.repo_dir)
                    os.makedirs(self.repo_dir, exist_ok=True)
                    ret, _, err = await self._run_git(
                        "clone", "--depth=1", url, self.repo_dir, cwd="/tmp"
                    )
                    if ret != 0:
                        log.error("Failed to clone repo: %s", err)
                        return False
                    # Create the sync branch
                    ret, _, err = await self._run_git(
                        "checkout", "-b", self.config.branch
                    )
                    if ret != 0:
                        log.error("Failed to create branch: %s", err)
                        return False

            log.info("Git sync initialized successfully")
            return True

    async def sync_persona(
        self, filename: str, action: str, content: str | None = None
    ) -> bool:
        """Sync a single persona file change to git.

        Args:
            filename: The persona filename (e.g., "my-persona.toml")
            action: One of "create", "update", "delete"
            content: File content for create/update (not needed for delete)

        Returns:
            True if sync succeeded, False otherwise.
        """
        if not self.config.enabled:
            return False

        async with self._lock:
            try:
                personas_path = os.path.join(self.repo_dir, self.config.personas_subdir)
                os.makedirs(personas_path, exist_ok=True)
                file_path = os.path.join(personas_path, filename)

                # Validate filename to prevent path traversal
                if os.path.sep in filename or filename.startswith("."):
                    log.error("Invalid filename for git sync: %s", filename)
                    return False

                if action == "delete":
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        commit_msg = f"Delete persona: {filename}"
                    else:
                        log.debug("File already deleted: %s", filename)
                        return True
                else:
                    # create or update
                    if content is None:
                        # Read from local personas dir
                        local_path = os.path.join(self.local_personas_dir, filename)
                        if not os.path.isfile(local_path):
                            log.error("Local persona file not found: %s", local_path)
                            return False
                        with open(local_path, encoding="utf-8") as f:
                            content = f.read()

                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    commit_msg = (
                        f"{'Create' if action == 'create' else 'Update'} persona: {filename}"
                    )

                # Stage, commit, and push
                ret, _, err = await self._run_git("add", file_path)
                if ret != 0:
                    log.error("Git add failed: %s", err)
                    return False

                # Check if there are changes to commit
                ret, stdout, _ = await self._run_git("status", "--porcelain")
                if not stdout.strip():
                    log.debug("No changes to commit for %s", filename)
                    return True

                ret, _, err = await self._run_git("commit", "-m", commit_msg)
                if ret != 0:
                    log.error("Git commit failed: %s", err)
                    return False

                url = self._get_authenticated_url()
                if url:
                    ret, _, err = await self._run_git(
                        "push", "-u", url, self.config.branch
                    )
                    if ret != 0:
                        log.error("Git push failed: %s", err)
                        return False

                log.info("Git sync successful: %s %s", action, filename)
                return True

            except Exception as e:
                log.exception("Git sync error for %s: %s", filename, e)
                return False

    async def full_sync(self) -> bool:
        """Sync all persona files from local directory to git.

        This copies all .toml files from local_personas_dir to the repo
        and commits/pushes any changes.
        """
        if not self.config.enabled:
            return False

        async with self._lock:
            try:
                personas_path = os.path.join(self.repo_dir, self.config.personas_subdir)
                os.makedirs(personas_path, exist_ok=True)

                # Get local and repo files
                local_files = set()
                if os.path.isdir(self.local_personas_dir):
                    local_files = {
                        f
                        for f in os.listdir(self.local_personas_dir)
                        if f.endswith(".toml") and not f.startswith(".")
                    }

                repo_files = set()
                if os.path.isdir(personas_path):
                    repo_files = {
                        f
                        for f in os.listdir(personas_path)
                        if f.endswith(".toml") and not f.startswith(".")
                    }

                # Copy new/updated files
                for filename in local_files:
                    src = os.path.join(self.local_personas_dir, filename)
                    dst = os.path.join(personas_path, filename)
                    shutil.copy2(src, dst)

                # Remove deleted files
                for filename in repo_files - local_files:
                    dst = os.path.join(personas_path, filename)
                    if os.path.isfile(dst):
                        os.remove(dst)

                # Stage all changes
                ret, _, err = await self._run_git("add", personas_path)
                if ret != 0:
                    log.error("Git add failed: %s", err)
                    return False

                # Check if there are changes
                ret, stdout, _ = await self._run_git("status", "--porcelain")
                if not stdout.strip():
                    log.debug("No changes to sync")
                    return True

                ret, _, err = await self._run_git("commit", "-m", "Sync all personas")
                if ret != 0:
                    log.error("Git commit failed: %s", err)
                    return False

                url = self._get_authenticated_url()
                if url:
                    ret, _, err = await self._run_git(
                        "push", "-u", url, self.config.branch
                    )
                    if ret != 0:
                        log.error("Git push failed: %s", err)
                        return False

                log.info("Full git sync completed")
                return True

            except Exception as e:
                log.exception("Full git sync error: %s", e)
                return False


def load_git_sync_config() -> GitSyncConfig:
    """Load git sync configuration from environment variables."""
    enabled = os.getenv("GIT_SYNC_ENABLED", "").lower() in {"1", "true", "yes", "on"}
    return GitSyncConfig(
        enabled=enabled,
        repo_url=os.getenv("GIT_SYNC_REPO_URL") or None,
        branch=os.getenv("GIT_SYNC_BRANCH", "personas-sync"),
        token=os.getenv("GIT_SYNC_TOKEN") or None,
        author_name=os.getenv("GIT_SYNC_AUTHOR_NAME", "Prism Bot"),
        author_email=os.getenv(
            "GIT_SYNC_AUTHOR_EMAIL", "prism-bot@users.noreply.github.com"
        ),
        personas_subdir=os.getenv("GIT_SYNC_PERSONAS_SUBDIR", "personas"),
    )
