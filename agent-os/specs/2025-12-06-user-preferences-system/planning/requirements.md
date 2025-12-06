# Spec Requirements: User Preferences System

## Initial Description

This feature combines three related items:

1. **User Preferences Storage** (Size: S) - Store per-user preferences in the database (preferred persona, response style, etc.) that persist across sessions

2. **User Preference Commands** (Size: S) - Slash commands for users to view and update their personal preferences (`/preferences view`, `/preferences set`)

3. **Per-User Response Customization** (Size: M) - Apply stored user preferences when generating responses (e.g., verbosity level, formality, emoji density)

The User Preferences System will allow individual Discord users to customize how the AI bot responds to them specifically, enabling personalization at the user level.

## Requirements Discussion

### First Round Questions

**Q1:** I assume response length will support three levels: concise, balanced, and detailed (like the current guild-level setting). Should these map to specific token limits, or just serve as guidance to the AI?
**Answer:** Yes, three levels with hard token limits enforced via the API (max_tokens parameter). This is already implemented in the codebase.

**Q2:** For emoji density preference, I'm thinking: none, minimal, normal, lots. Does that cover the range you want?
**Answer:** Yes, those four levels are correct.

**Q3:** Should formality be a user preference (casual/neutral/formal), or is that better handled by persona selection?
**Answer:** Formality should NOT be a user preference - that's persona territory.

**Q4:** For "preferred persona," should this override the guild's active persona, or just be a suggestion?
**Answer:** User's preferred persona should apply. All personas should exist in all guilds (not guild-scoped). User's preferred persona applies across ALL guilds.

**Q5:** Should `/preferences view` show settings publicly or as an ephemeral message only the user sees?
**Answer:** Public (not ephemeral).

**Q6:** What happens when a user hasn't set preferences? I assume we fall back to sensible defaults (balanced length, normal emojis, etc.)?
**Answer:** Yes, fall back to defaults: balanced length, normal emoji density, no preferred persona (use guild default).

**Q7:** Should there be a `/preferences reset` command to clear all preferences back to defaults?
**Answer:** Yes, include `/preferences reset`.

**Q8:** Is there anything you specifically want to exclude from user preferences at this stage?
**Answer:** Exclude formality (that's persona territory).

### Follow-up Questions

**Follow-up 1:** For the `/length` command, should we: (a) Deprecate `/length` entirely and migrate to `/preferences set response_length <value>`, or (b) Keep `/length` as a guild-wide default but have user preferences override it?
**Answer:** Option (a) - Deprecate `/length` entirely and migrate to `/preferences set response_length <value>`.

**Follow-up 2:** For persona scope: Currently personas are guild-scoped via settings. With user-level preferred persona, should personas be global (same set available in all guilds) or remain per-guild?
**Answer:** Yes, all personas should exist in all guilds. User's preferred persona applies across ALL guilds.

**Follow-up 3:** Are there existing features in your codebase with similar patterns we should reference?
**Answer:** User says "you decide" - use research to identify the best patterns.

### Existing Code to Reference

Based on codebase analysis, the following files contain relevant patterns for the spec-writer:

**Similar Features Identified:**
- Feature: Length Cog (to be deprecated) - Path: `/var/home/jako/Projects/prism/prism/cogs/length.py`
  - Shows SlashCommandGroup pattern with subcommands
  - Will be removed/deprecated as part of this work

- Feature: Personas Cog - Path: `/var/home/jako/Projects/prism/prism/cogs/personas.py`
  - Shows autocomplete pattern for option choices
  - Shows guild-scoped command registration
  - Current persona selection will shift from guild to user level

- Feature: Settings Service - Path: `/var/home/jako/Projects/prism/prism/services/settings.py`
  - Shows JSON-based settings storage pattern (guild-scoped)
  - Shows `DEFAULT_SETTINGS` pattern with fallback
  - Shows `resolve_*` pattern for looking up effective values
  - Current guild-scoped approach will be replaced with user-scoped approach

- Feature: Database Service - Path: `/var/home/jako/Projects/prism/prism/services/db.py`
  - Shows SQLite patterns with aiosqlite
  - Shows retry logic for database locks
  - New user_preferences table will follow similar patterns

- Feature: OpenRouter Client - Path: `/var/home/jako/Projects/prism/prism/services/openrouter_client.py`
  - Shows where `max_tokens` is passed (response length enforcement point)
  - This is where user preferences will be applied during response generation

## Visual Assets

### Files Provided:
No visual assets provided.

### Visual Insights:
N/A - No visual files found in `/var/home/jako/Projects/prism/agent-os/specs/2025-12-06-user-preferences-system/planning/visuals/`

## Requirements Summary

### Functional Requirements

**Preferences to Support:**
- **Response Length** (concise/balanced/detailed) - with hard token limits via API
- **Emoji Density** (none/minimal/normal/lots)
- **Preferred Persona** (user's default persona across all guilds)

**Commands:**
- `/preferences view` - Shows current user settings (PUBLIC, not ephemeral)
- `/preferences set <preference> <value>` - Set a preference with autocomplete for options
- `/preferences reset` - Clear all preferences back to defaults

**Preference Resolution:**
- User preference takes precedence when set
- Fall back to global defaults when user hasn't set a preference
- No guild layer for preferences (user-global only)

**Defaults:**
- Response length: balanced
- Emoji density: normal
- Preferred persona: none (use guild's active persona)

### Reusability Opportunities

**Patterns to Follow:**
- `SlashCommandGroup` pattern from `length.py` and `personas.py`
- Autocomplete pattern from `personas.py` (`_persona_name_autocomplete`)
- JSON-based settings storage from `settings.py`
- `DEFAULT_SETTINGS` and `resolve_*` patterns from `settings.py`
- Database retry logic from `db.py`

**Components to Create:**
- New `UserPreferencesService` (similar to `SettingsService` but user-scoped)
- New `PreferencesCog` (similar to `LengthCog` but more comprehensive)
- New `user_preferences` database table

**Integration Points:**
- `openrouter_client.py` - Apply response length (max_tokens) from user preferences
- Response generation - Apply emoji density from user preferences
- Persona resolution - Check user's preferred persona before guild default

### Scope Boundaries

**In Scope:**
- User preferences database storage (user_id keyed, not guild-scoped)
- Three slash commands: view, set, reset
- Preference types: response_length, emoji_density, preferred_persona
- Deprecation and removal of `/length` command
- Migration of response_length from guild-level to user-level
- Migration of persona selection from guild-level to user-level preference
- Making personas globally available (not guild-scoped)

**Out of Scope:**
- Formality preference (handled by persona selection)
- Guild-level preference overrides (user-global only)
- Per-channel preferences
- Web dashboard integration (future roadmap item)

### Technical Considerations

**Database:**
- New `user_preferences` table with `user_id` as primary key (Discord snowflake as TEXT)
- JSON storage for preferences (following existing `settings` table pattern)
- Schema migration needed

**Architecture:**
- User preferences are USER-GLOBAL (same across all guilds)
- DEPRECATE guild-wide settings for response_length
- Persona selection moves from guild-level (`/persona set`) to user-level (`/preferences set preferred_persona`)
- Priority order: User preference > Global default (no guild layer)

**Migration Path:**
1. Create new `user_preferences` table
2. Create `UserPreferencesService`
3. Create `PreferencesCog` with `/preferences` command group
4. Modify persona resolution to check user preference first
5. Modify response generation to apply user's emoji density
6. Deprecate and remove `LengthCog` (`/length` command)
7. Update `SettingsService` to remove response_length (or deprecate entirely)

**Tech Stack Alignment:**
- Python 3.11+ with async/await
- Pycord for Discord integration
- SQLite via aiosqlite for storage
- Follows existing codebase patterns
