from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .db import Database


log = logging.getLogger(__name__)


@dataclass
class BackfillConfig:
    batch_size: int = 100
    sleep_between_batches: float = 1.0
    max_messages_per_run: Optional[int] = None  # None means unlimited
    # Concurrency controls
    channel_concurrency: int = 1  # how many channels to process in parallel for guild-wide runs
    message_concurrency: int = 1  # how many LLM extractions to run in parallel within a channel batch


class FactsBackfillService:
    def __init__(self, db: Database, learning_service, backfill_model: Optional[str] = None) -> None:
        self.db = db
        self.learning = learning_service
        self.cfg = BackfillConfig()
        self._tasks: Dict[str, asyncio.Task] = {}
        self._guild_tasks: Dict[int, asyncio.Task] = {}
        self.backfill_model_default: Optional[str] = backfill_model
        # Global shutdown flag for graceful termination (Ctrl-C / SIGTERM)
        self._shutdown_event: asyncio.Event = asyncio.Event()

    def _key(self, guild_id: int, channel_id: int) -> str:
        return f"{guild_id}:{channel_id}"

    async def get_status(self, guild_id: int, channel_id: int) -> Dict[str, Any]:
        row = await self.db.fetchone(
            "SELECT last_message_id, processed_count, status, updated_at FROM facts_backfill WHERE guild_id = ? AND channel_id = ?",
            (str(guild_id), str(channel_id)),
        )
        if not row:
            return {"status": "idle", "processed": 0, "last_message_id": None}
        return {
            "status": str(row[2] or "idle"),
            "processed": int(row[1] or 0),
            "last_message_id": row[0],
            "updated_at": row[3],
        }

    async def start(self, bot: Any, orc: Any, guild_id: int, channel_id: int) -> None:
        key = self._key(guild_id, channel_id)
        if key in self._tasks and not self._tasks[key].done():
            return
        await self._ensure_row(guild_id, channel_id, status="running")
        task = asyncio.create_task(self._run_channel(bot, orc, guild_id, channel_id))
        self._tasks[key] = task

    async def stop(self, guild_id: int, channel_id: int) -> None:
        key = self._key(guild_id, channel_id)
        t = self._tasks.get(key)
        if t and not t.done():
            t.cancel()
        await self._ensure_row(guild_id, channel_id, status="stopped")

    # --------------- Guild-wide operations ---------------
    async def start_guild(self, bot: Any, orc: Any, guild_id: int, model: Optional[str] = None) -> None:
        if guild_id in self._guild_tasks and not self._guild_tasks[guild_id].done():
            return
        task = asyncio.create_task(self._run_guild(bot, orc, guild_id, model or self.backfill_model_default))
        self._guild_tasks[guild_id] = task

    async def stop_guild(self, guild_id: int) -> None:
        t = self._guild_tasks.get(guild_id)
        if t and not t.done():
            t.cancel()
        # Also cancel any direct channel tasks under this guild
        for key, task in list(self._tasks.items()):
            try:
                gs, cs = key.split(":", 1)
                if int(gs) == int(guild_id) and task and not task.done():
                    task.cancel()
            except Exception:
                pass
        # Mark any running rows for this guild as stopped so resume can pick up later
        try:
            await self.db.execute(
                "UPDATE facts_backfill SET status = 'stopped', updated_at = CURRENT_TIMESTAMP WHERE guild_id = ? AND status = 'running'",
                (str(guild_id),),
            )
        except Exception:
            pass

    async def request_stop_all(self) -> None:
        """Request all backfill tasks to stop gracefully and mark progress.

        Sets a shutdown flag that loops check between batches, cancels known tasks,
        and marks any running rows as stopped so that resume can continue later.
        """
        try:
            self._shutdown_event.set()
        except Exception:
            pass
        # Cancel channel tasks
        for key, task in list(self._tasks.items()):
            try:
                if task and not task.done():
                    task.cancel()
            except Exception:
                pass
            # Persist stopped status for the channel
            try:
                gs, cs = key.split(":", 1)
                await self._ensure_row(int(gs), int(cs), status="stopped")
            except Exception:
                pass
        # Cancel guild tasks and mark running rows as stopped
        for gid, task in list(self._guild_tasks.items()):
            try:
                if task and not task.done():
                    task.cancel()
            except Exception:
                pass
            try:
                await self.db.execute(
                    "UPDATE facts_backfill SET status = 'stopped', updated_at = CURRENT_TIMESTAMP WHERE guild_id = ? AND status = 'running'",
                    (str(gid),),
                )
            except Exception:
                pass

    async def get_guild_status(self, bot: Any, guild_id: int) -> Dict[str, Any]:
        """Aggregate status across all text channels in the guild."""
        try:
            guild = getattr(bot, "get_guild")(guild_id)
        except Exception:
            guild = None
        total_channels = 0
        try:
            import discord  # type: ignore

            if guild:
                # Only scan text channels
                total_channels = len([c for c in getattr(guild, "channels", []) if isinstance(c, discord.TextChannel)])
        except Exception:
            pass

        rows = await self.db.fetchall(
            "SELECT channel_id, status, processed_count FROM facts_backfill WHERE guild_id = ?",
            (str(guild_id),),
        )
        status_counts: Dict[str, int] = {}
        processed_total = 0
        channels_with_rows = set()
        for r in rows or []:
            ch_status = str(r[1] or "idle")
            status_counts[ch_status] = status_counts.get(ch_status, 0) + 1
            try:
                processed_total += int(r[2] or 0)
            except Exception:
                pass
            channels_with_rows.add(str(r[0]))

        # Infer pending channels (no row yet)
        pending_channels = max(0, total_channels - len(channels_with_rows)) if total_channels else 0

        # Determine overall status
        overall_status = "idle"
        if status_counts.get("running"):
            overall_status = "running"
        elif total_channels and status_counts.get("completed", 0) >= total_channels:
            overall_status = "completed"
        elif rows:
            # Some progress but not running now
            overall_status = "stopped"

        return {
            "status": overall_status,
            "channels_total": total_channels,
            "channels_completed": status_counts.get("completed", 0),
            "channels_running": status_counts.get("running", 0),
            "channels_stopped": status_counts.get("stopped", 0),
            "channels_error": status_counts.get("error", 0),
            "channels_pending": pending_channels,
            "processed_total": processed_total,
        }

    async def _ensure_row(self, guild_id: int, channel_id: int, **updates) -> None:
        row = await self.db.fetchone(
            "SELECT id FROM facts_backfill WHERE guild_id = ? AND channel_id = ?",
            (str(guild_id), str(channel_id)),
        )
        if row:
            sets = ", ".join([f"{k} = ?" for k in updates.keys()])
            params = list(updates.values()) + [int(row[0])]
            await self.db.execute(f"UPDATE facts_backfill SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", params)
        else:
            await self.db.execute(
                "INSERT INTO facts_backfill (guild_id, channel_id, status, processed_count) VALUES (?, ?, ?, 0)",
                (str(guild_id), str(channel_id), str(updates.get("status", "idle"))),
            )

    async def _run_channel(self, bot: Any, orc: Any, guild_id: int, channel_id: int, model: Optional[str] = None) -> None:
        try:
            await self._ensure_row(guild_id, channel_id, status="running")
            guild = getattr(bot, "get_guild")(guild_id)
            if not guild:
                log.debug("backfill: guild not found %s", guild_id)
                await self._ensure_row(guild_id, channel_id, status="error")
                return
            channel = getattr(guild, "get_channel")(channel_id)
            if not channel:
                log.debug("backfill: channel not found %s", channel_id)
                await self._ensure_row(guild_id, channel_id, status="error")
                return

            import discord  # type: ignore

            # Load last position
            st = await self.get_status(guild_id, channel_id)
            last_id = st.get("last_message_id")
            processed = int(st.get("processed", 0))
            total_processed = 0

            while True:
                # Respect global shutdown requests
                if self._shutdown_event.is_set():
                    await self._ensure_row(guild_id, channel_id, status="stopped")
                    break
                after = discord.Object(id=int(last_id)) if last_id else None
                batch = []
                try:
                    async for msg in channel.history(limit=self.cfg.batch_size, after=after, oldest_first=True):
                        batch.append(msg)
                except Exception as e:  # noqa: BLE001
                    log.debug("backfill history fetch failed: %s", e)
                    await asyncio.sleep(2.0)
                    continue

                if not batch:
                    await self._ensure_row(guild_id, channel_id, status="completed")
                    break

                # Process this batch, optionally with message-level concurrency
                sem = asyncio.Semaphore(max(1, int(self.cfg.message_concurrency)))

                # Pre-filter messages to avoid unnecessary LLM calls
                # Only keep non-bot, non-webhook, non-empty messages that pass the learner's gate
                prefiltered: list = []
                for m in batch:
                    try:
                        if getattr(m.author, "bot", False) or getattr(m, "webhook_id", None):
                            continue
                        content = (m.content or "").strip()
                        if not content:
                            continue
                        # Use the learner's gate to skip irrelevant messages quickly
                        gate_fn = getattr(self.learning, "_gate_message", None)
                        if callable(gate_fn) and gate_fn(content):
                            continue
                        prefiltered.append(m)
                    except Exception:
                        # If anything goes wrong, be conservative and include the message
                        prefiltered.append(m)

                async def _process_message(m) -> bool:
                    # Returns True if counted as processed (human message); False otherwise
                    try:
                        content = (m.content or "").strip()
                        if not content:
                            return False
                        async with sem:
                            await self.learning.learn_from_message(
                                orc,
                                guild_id,
                                m.author.id,
                                content,
                                message_id=m.id,
                                model=model or self.backfill_model_default,
                            )
                        return True
                    except Exception as e:  # noqa: BLE001
                        log.debug("backfill learn failed for %s: %s", m.id, e)
                        return True  # still count as a human attempt

                # Run LLM extractions with batched DB transaction for fewer commits
                tasks = [asyncio.create_task(_process_message(m)) for m in prefiltered]
                try:
                    # Start a transaction so individual DB writes avoid per-statement commits
                    try:
                        await self.db.conn.execute("BEGIN")
                    except Exception:
                        pass
                    results = await asyncio.gather(*tasks, return_exceptions=False)

                    # Update counters: count human messages attempted
                    human_count = sum(1 for r in results if r is True)
                    processed += human_count
                    total_processed += human_count
                    # Set last_id to last message in batch, since history pagination uses it
                    try:
                        last_id = batch[-1].id
                    except Exception:
                        pass

                    # Persist backfill progress within the same transaction
                    await self.db.execute(
                        "UPDATE facts_backfill SET last_message_id = ?, processed_count = ?, updated_at = CURRENT_TIMESTAMP WHERE guild_id = ? AND channel_id = ?",
                        (str(last_id) if last_id else None, int(processed), str(guild_id), str(channel_id)),
                    )

                    # Commit the whole batch as a unit
                    try:
                        await self.db.conn.commit()
                    except Exception:
                        pass
                except Exception as e:  # noqa: BLE001
                    log.debug("batch processing gather failed: %s", e)
                    try:
                        await self.db.conn.rollback()
                    except Exception:
                        pass
                    results = []

                if self.cfg.max_messages_per_run and total_processed >= self.cfg.max_messages_per_run:
                    await self._ensure_row(guild_id, channel_id, status="stopped")
                    break

                if self.cfg.sleep_between_batches > 0:
                    await asyncio.sleep(self.cfg.sleep_between_batches)
                # Check shutdown between batches
                if self._shutdown_event.is_set():
                    await self._ensure_row(guild_id, channel_id, status="stopped")
                    break

        except asyncio.CancelledError:
            await self._ensure_row(guild_id, channel_id, status="stopped")
        except Exception as e:  # noqa: BLE001
            log.debug("backfill run error: %s", e)
            await self._ensure_row(guild_id, channel_id, status="error")

    async def _run_guild(self, bot: Any, orc: Any, guild_id: int, model: Optional[str] = None) -> None:
        try:
            import discord  # type: ignore

            guild = getattr(bot, "get_guild")(guild_id)
            if not guild:
                log.debug("backfill: guild not found %s", guild_id)
                return

            # Get all text channels
            channels = [c for c in getattr(guild, "channels", []) if isinstance(c, discord.TextChannel)]

            sem = asyncio.Semaphore(max(1, int(self.cfg.channel_concurrency)))

            async def _run_one(ch):
                async with sem:
                    key = self._key(guild_id, ch.id)
                    # Skip if a dedicated channel task is already running
                    if key in self._tasks and not self._tasks[key].done():
                        return
                    # Skip if already completed
                    st = await self.get_status(guild_id, ch.id)
                    if st.get("status") == "completed":
                        return
                    # Respect shutdown
                    if self._shutdown_event.is_set():
                        return
                    await self._run_channel(bot, orc, guild_id, ch.id, model=model)

            await asyncio.gather(*[_run_one(ch) for ch in channels])
        except asyncio.CancelledError:
            # Cancellation requested for guild-wide run; nothing else to mark here
            pass
        except Exception as e:  # noqa: BLE001
            log.debug("backfill guild run error: %s", e)
