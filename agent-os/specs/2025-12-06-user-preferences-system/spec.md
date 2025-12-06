# Specification: User Preferences System

## Goal
Enable individual Discord users to personalize how the AI bot responds to them by storing and applying user-level preferences (response length, emoji density, preferred persona) that persist across sessions and guilds.

## User Stories
- As a Discord user, I want to set my preferred response length so the bot gives me answers in my preferred verbosity level regardless of which server I'm in
- As a Discord user, I want to choose a preferred persona that applies whenever I interact with the bot, without affecting other users' experiences

## Specific Requirements

**User Preferences Database Table**
- Create `user_preferences` table with `user_id` (TEXT) as primary key (Discord snowflake)
- Store preferences as JSON in `data_json` column (following existing `settings` table pattern)
- Include `updated_at` timestamp column with DEFAULT CURRENT_TIMESTAMP
- Add migration v3 to create this table via the existing migrations system in `/var/home/jako/Projects/prism/prism/storage/migrations.py`

**UserPreferencesService**
- Create new service at `/var/home/jako/Projects/prism/prism/services/user_preferences.py`
- Follow `SettingsService` pattern: `get(user_id)`, `set(user_id, data)`, plus specific getters/setters
- Define `DEFAULT_USER_PREFERENCES = {"response_length": "balanced", "emoji_density": "normal", "preferred_persona": None}`
- Implement `resolve_response_length(user_id)`, `resolve_emoji_density(user_id)`, `resolve_preferred_persona(user_id)`
- Use `INSERT OR IGNORE` pattern for atomic default creation (see `settings.py` lines 27-31)

**PreferencesCog Slash Commands**
- Create `/preferences` SlashCommandGroup at `/var/home/jako/Projects/prism/prism/cogs/preferences.py`
- `/preferences view` - Display current user settings publicly (not ephemeral)
- `/preferences set <preference> <value>` - Set preference with autocomplete; valid preferences: response_length, emoji_density, preferred_persona
- `/preferences reset` - Clear all preferences back to defaults
- Follow guild scoping pattern from `length.py` setup function (lines 36-51)

**Preference Value Validation**
- Response length: "concise", "balanced", "detailed" (reuse `VALID_RESPONSE_LENGTHS` from settings.py)
- Emoji density: "none", "minimal", "normal", "lots" - define as `VALID_EMOJI_DENSITIES`
- Preferred persona: Validate against available personas via `prism_personas.get(name)`, allow None to clear

**Autocomplete for /preferences set**
- First parameter `preference`: Static choices ["response_length", "emoji_density", "preferred_persona"]
- Second parameter `value`: Dynamic autocomplete based on selected preference type
- For preferred_persona, reuse `_persona_name_autocomplete` pattern from personas.py (lines 22-45)

**Response Length Integration**
- Modify `main.py` line 334 to call `bot.prism_user_prefs.resolve_response_length(message.author.id)` instead of guild settings
- Keep existing `RESPONSE_LENGTH_GUIDANCE` and `RESPONSE_LENGTH_MAX_TOKENS` mappings in main.py
- Pass resolved `max_tokens` to `orc.chat_completion()` as already implemented (line 441)

**Emoji Density Integration**
- Add emoji density guidance text mapping similar to `RESPONSE_LENGTH_GUIDANCE` in main.py
- Inject density guidance into system prompt alongside length guidance (around line 342)
- Density levels: none="Do not use any emojis", minimal="Use emojis sparingly, only 1-2 per message", normal="Use emojis naturally", lots="Be generous with emojis, include many throughout"
- When density is "none", skip emoji enforcement pipeline entirely (main.py lines 445-456)

**Preferred Persona Integration**
- Modify `resolve_persona_name` flow in main.py (line 328): check user preference first, then fall back to guild default
- If user has preferred_persona set, use it; otherwise use existing `prism_settings.resolve_persona_name()`
- Persona files remain in `/var/home/jako/Projects/prism/personas/` directory, accessible globally

**Deprecate /length Command**
- Remove `LengthCog` from `/var/home/jako/Projects/prism/prism/cogs/length.py`
- Remove `setup_length` import and call from main.py (lines 566, 570)
- Remove `set_response_length` and `resolve_response_length` from `SettingsService`
- Keep `response_length` in `DEFAULT_SETTINGS` temporarily for migration compatibility

**Bot Service Registration**
- Add `bot.prism_user_prefs = UserPreferencesService(db)` in `main.py` after line 540
- Import `UserPreferencesService` from services module
- Load `PreferencesCog` via setup function pattern after other cogs

## Existing Code to Leverage

**SettingsService (`/var/home/jako/Projects/prism/prism/services/settings.py`)**
- Reuse JSON storage pattern with `INSERT OR IGNORE` for atomic initialization (lines 28-39)
- Follow `DEFAULT_SETTINGS` + `resolve_*` method pattern for preference resolution
- Copy `ON CONFLICT DO UPDATE` upsert pattern (lines 54-59)
- Copy validation approach for preference values (e.g., `VALID_RESPONSE_LENGTHS` check)

**LengthCog (`/var/home/jako/Projects/prism/prism/cogs/length.py`)**
- Use `SlashCommandGroup` pattern with subcommands
- Follow guild_ids scoping in setup function for command registration (lines 37-51)
- This cog will be removed; its functionality moves to PreferencesCog

**PersonaCog (`/var/home/jako/Projects/prism/prism/cogs/personas.py`)**
- Reuse `_persona_name_autocomplete` pattern for preferred_persona value autocomplete (lines 22-45)
- Follow `basic_autocomplete` decorator usage for dynamic option choices
- Reference persona validation via `bot.prism_personas.get(name)`

**Database Migrations (`/var/home/jako/Projects/prism/prism/storage/migrations.py`)**
- Add `_migration_v3_create_user_preferences` function following existing pattern (lines 27-37)
- Append to `MIGRATIONS` list after v2

**main.py Response Generation**
- Integration points: lines 328-342 for persona/length resolution, line 441 for max_tokens
- Service attachment pattern at lines 538-560 for adding `prism_user_prefs` to bot
- Modify `_generate_and_reply` inner function to use user preferences

## Out of Scope
- Formality preference (this is handled by persona selection)
- Guild-level preference overrides or defaults (user preferences are user-global only)
- Per-channel preferences
- Web dashboard for preference management
- Migration of existing guild-level response_length settings to user preferences
- Automatic persona creation from user preferences
- Preference sync across multiple bot instances
- Preference export/import functionality
- Admin commands to view/modify other users' preferences
- Rate limiting on preference changes
