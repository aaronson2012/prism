"""Tests for channel lock manager."""
import asyncio
import time
import pytest
from prism.services.channel_locks import ChannelLockManager


def test_channel_lock_manager_creates_locks():
    """Test that lock manager creates new locks."""
    manager = ChannelLockManager()
    
    lock1 = manager.get_lock(123)
    lock2 = manager.get_lock(456)
    
    assert lock1 is not None
    assert lock2 is not None
    assert lock1 is not lock2


def test_channel_lock_manager_reuses_locks():
    """Test that same channel gets same lock."""
    manager = ChannelLockManager()
    
    lock1 = manager.get_lock(123)
    lock2 = manager.get_lock(123)
    
    assert lock1 is lock2


@pytest.mark.asyncio
async def test_channel_lock_manager_locks_work():
    """Test that returned locks actually work for synchronization."""
    manager = ChannelLockManager()
    lock = manager.get_lock(123)
    
    # Acquire lock
    async with lock:
        # Lock should be locked
        assert lock.locked()
    
    # Lock should be released
    assert not lock.locked()


def test_channel_lock_manager_cleanup():
    """Test that old locks are cleaned up."""
    # Use very short threshold for testing
    manager = ChannelLockManager(cleanup_threshold_sec=0.1)
    manager._cleanup_interval = 0.01  # Force frequent cleanup checks
    
    # Create a lock
    lock1 = manager.get_lock(123)
    assert manager.get_stats()["active_locks"] == 1
    
    # Wait for it to expire
    time.sleep(0.15)
    
    # Get another lock to trigger cleanup
    lock2 = manager.get_lock(456)
    
    # Old lock should be cleaned up, new one should exist
    stats = manager.get_stats()
    assert stats["active_locks"] == 1
    # Lock1 should have been removed (can't test directly, but stats show it)


def test_channel_lock_manager_does_not_cleanup_active():
    """Test that recently used locks are not cleaned up."""
    manager = ChannelLockManager(cleanup_threshold_sec=1.0)
    manager._cleanup_interval = 0.01
    
    # Create locks
    lock1 = manager.get_lock(123)
    lock2 = manager.get_lock(456)
    
    # Wait a bit but keep using lock1
    time.sleep(0.5)
    lock1_again = manager.get_lock(123)
    assert lock1 is lock1_again
    
    # Both should still exist
    assert manager.get_stats()["active_locks"] == 2


@pytest.mark.asyncio
async def test_channel_lock_manager_does_not_cleanup_locked():
    """Test that locked locks are not cleaned up."""
    manager = ChannelLockManager(cleanup_threshold_sec=0.1)
    manager._cleanup_interval = 0.01
    
    lock = manager.get_lock(123)
    
    # Acquire the lock
    await lock.acquire()
    
    try:
        # Wait for cleanup threshold
        time.sleep(0.15)
        
        # Trigger cleanup by getting another lock
        manager.get_lock(456)
        
        # Original lock should still exist because it's locked
        assert manager.get_stats()["active_locks"] == 2
    finally:
        lock.release()


def test_channel_lock_manager_stats():
    """Test that stats are accurate."""
    manager = ChannelLockManager()
    
    assert manager.get_stats()["active_locks"] == 0
    
    manager.get_lock(1)
    assert manager.get_stats()["active_locks"] == 1
    
    manager.get_lock(2)
    assert manager.get_stats()["active_locks"] == 2
    
    # Getting same lock doesn't increase count
    manager.get_lock(1)
    assert manager.get_stats()["active_locks"] == 2

