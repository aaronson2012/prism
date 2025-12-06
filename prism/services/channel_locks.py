"""Channel lock manager with automatic cleanup to prevent memory leaks."""
from __future__ import annotations

import asyncio
import time


class ChannelLockManager:
    """Manages per-channel locks with automatic cleanup of unused locks.
    
    This prevents unbounded memory growth from channels that are no longer active.
    """
    
    def __init__(self, cleanup_threshold_sec: float = 3600.0) -> None:
        """Initialize the lock manager.
        
        Args:
            cleanup_threshold_sec: Time in seconds after which unused locks are removed.
                                   Default is 1 hour.
        """
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_used: dict[str, float] = {}
        self._cleanup_threshold = cleanup_threshold_sec
        self._last_cleanup = time.monotonic()
        self._cleanup_interval = 600.0  # Run cleanup every 10 minutes
    
    def get_lock(self, channel_id: int) -> asyncio.Lock:
        """Get or create a lock for the given channel.
        
        Args:
            channel_id: Discord channel ID
            
        Returns:
            asyncio.Lock for the channel
        """
        key = str(channel_id)
        
        # Periodic cleanup
        now = time.monotonic()
        if now - self._last_cleanup >= self._cleanup_interval:
            self._cleanup_old_locks(now)
            self._last_cleanup = now
        
        # Get or create lock
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        
        self._last_used[key] = now
        return self._locks[key]
    
    def _cleanup_old_locks(self, now: float) -> None:
        """Remove locks that haven't been used recently.

        Args:
            now: Current monotonic time
        """
        to_remove = []

        for key, last_used in list(self._last_used.items()):
            if now - last_used >= self._cleanup_threshold:
                to_remove.append(key)

        for key in to_remove:
            # Only remove if not currently locked and still in dict
            # Use pop with default to handle concurrent modifications safely
            lock = self._locks.get(key)
            if lock is not None and not lock.locked():
                # Double-check last_used hasn't been updated since we started cleanup
                # This prevents removing a lock that was just accessed
                current_last_used = self._last_used.get(key)
                if current_last_used is not None and now - current_last_used >= self._cleanup_threshold:
                    # Use pop to avoid KeyError if another coroutine removed it
                    self._locks.pop(key, None)
                    self._last_used.pop(key, None)
    
    def get_stats(self) -> dict[str, int]:
        """Get current statistics about lock usage.
        
        Returns:
            Dictionary with 'active_locks' count
        """
        return {
            "active_locks": len(self._locks),
        }

