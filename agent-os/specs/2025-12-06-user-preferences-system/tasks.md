# Task Breakdown: User Preferences System

## Overview
Total Tasks: 28

This feature enables individual Discord users to personalize AI responses through user-level preferences (response length, emoji density, preferred persona) that persist across sessions and guilds.

## Task List

### Database Layer

#### Task Group 1: User Preferences Data Model and Migration
**Dependencies:** None

- [x] 1.0 Complete database layer for user preferences
  - [x] 1.1 Write 4-6 focused tests for UserPreferencesService
    - Test `get()` returns defaults for new user
    - Test `set()` persists preferences correctly
    - Test `resolve_response_length()` returns user preference when set
    - Test `resolve_preferred_persona()` returns None when unset
    - Test atomic INSERT OR IGNORE behavior for race conditions
    - Test invalid preference values are rejected
  - [x] 1.2 Create migration v3 in `/var/home/jako/Projects/prism/prism/storage/migrations.py`
    - Add `_migration_v3_create_user_preferences` function following v2 pattern (lines 27-37)
    - Create `user_preferences` table with:
      - `user_id TEXT PRIMARY KEY` (Discord snowflake)
      - `data_json TEXT NOT NULL`
      - `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
    - Append to `MIGRATIONS` list after v2 (line 42)
  - [x] 1.3 Create UserPreferencesService at `/var/home/jako/Projects/prism/prism/services/user_preferences.py`
    - Follow SettingsService pattern from `/var/home/jako/Projects/prism/prism/services/settings.py`
    - Define constants:
      - `DEFAULT_USER_PREFERENCES = {"response_length": "balanced", "emoji_density": "normal", "preferred_persona": None}`
      - `VALID_RESPONSE_LENGTHS = ("concise", "balanced", "detailed")` (reuse from settings.py line 19)
      - `VALID_EMOJI_DENSITIES = ("none", "minimal", "normal", "lots")`
    - Implement `get(user_id: int) -> dict[str, Any]` using INSERT OR IGNORE pattern (settings.py lines 27-31)
    - Implement `set(user_id: int, data: dict[str, Any])` with ON CONFLICT DO UPDATE (settings.py lines 54-59)
  - [x] 1.4 Add preference-specific getter/setter methods to UserPreferencesService
    - `set_response_length(user_id, length)` with validation against VALID_RESPONSE_LENGTHS
    - `set_emoji_density(user_id, density)` with validation against VALID_EMOJI_DENSITIES
    - `set_preferred_persona(user_id, persona_name)` (accepts None to clear)
    - `resolve_response_length(user_id) -> str` returns preference or "balanced"
    - `resolve_emoji_density(user_id) -> str` returns preference or "normal"
    - `resolve_preferred_persona(user_id) -> str | None` returns preference or None
  - [x] 1.5 Add `reset(user_id: int)` method to clear user back to defaults
    - Delete row from user_preferences table for user_id
  - [x] 1.6 Ensure database layer tests pass
    - Run ONLY the 4-6 tests written in 1.1
    - Verify migration v3 runs successfully
    - Do NOT run the entire test suite at this stage

**Acceptance Criteria:**
- The 4-6 tests written in 1.1 pass
- Migration v3 creates user_preferences table
- UserPreferencesService follows SettingsService patterns
- INSERT OR IGNORE prevents race conditions
- Validation rejects invalid preference values

---

### Service Layer

#### Task Group 2: Service Registration and Integration Points
**Dependencies:** Task Group 1

- [x] 2.0 Complete service registration and integration
  - [x] 2.1 Write 4-6 focused tests for integration logic
    - Test emoji density guidance text mapping returns correct strings
    - Test response length resolution prefers user preference over guild setting
    - Test persona resolution prefers user preference over guild default
    - Test emoji enforcement skipped when density is "none"
    - Test max_tokens passed correctly based on user response_length
  - [x] 2.2 Register UserPreferencesService in main.py
    - Add import: `from .services.user_preferences import UserPreferencesService`
    - Add `bot.prism_user_prefs = UserPreferencesService(db)` after line 540 (after prism_settings)
  - [x] 2.3 Define emoji density guidance mapping in main.py
    - Add `EMOJI_DENSITY_GUIDANCE` dict after `RESPONSE_LENGTH_MAX_TOKENS` (around line 45):
      ```python
      EMOJI_DENSITY_GUIDANCE = {
          "none": "Do not use any emojis.",
          "minimal": "Use emojis sparingly, only 1-2 per message.",
          "normal": "Use emojis naturally.",
          "lots": "Be generous with emojis, include many throughout.",
      }
      ```
  - [x] 2.4 Modify response length resolution in `_generate_and_reply` (main.py line 334)
    - Replace `await bot.prism_settings.resolve_response_length(message.guild.id)`
    - With `await bot.prism_user_prefs.resolve_response_length(message.author.id)`
  - [x] 2.5 Modify persona resolution in `_generate_and_reply` (main.py line 328)
    - First check: `user_persona = await bot.prism_user_prefs.resolve_preferred_persona(message.author.id)`
    - If user_persona is not None, use it; otherwise fall back to existing guild resolution
    - Preserve existing fallback to "default" persona if persona not found
  - [x] 2.6 Add emoji density to system prompt (main.py around line 342)
    - Resolve user's emoji density: `emoji_density = await bot.prism_user_prefs.resolve_emoji_density(message.author.id)`
    - Get guidance text: `density_guidance = EMOJI_DENSITY_GUIDANCE.get(emoji_density, EMOJI_DENSITY_GUIDANCE["normal"])`
    - Inject into system prompt alongside length_guidance
  - [x] 2.7 Skip emoji enforcement when density is "none" (main.py lines 445-456)
    - Add condition: `if emoji_density != "none"` before emoji enforcement block
    - When "none", skip both fallback_add_custom_emoji and enforce_emoji_distribution
  - [x] 2.8 Ensure integration tests pass
    - Run ONLY the 4-6 tests written in 2.1
    - Verify user preferences take precedence
    - Do NOT run the entire test suite at this stage

**Acceptance Criteria:**
- The 4-6 tests written in 2.1 pass
- UserPreferencesService registered on bot instance
- Response length uses user preference
- Persona resolution checks user preference first
- Emoji density affects system prompt and enforcement pipeline

---

### Command Layer

#### Task Group 3: PreferencesCog Slash Commands
**Dependencies:** Task Groups 1, 2

- [x] 3.0 Complete slash command implementation
  - [x] 3.1 Write 4-6 focused tests for PreferencesCog commands
    - Test `/preferences view` returns current preferences
    - Test `/preferences set response_length concise` updates preference
    - Test `/preferences set preferred_persona <name>` validates persona exists
    - Test `/preferences reset` clears all preferences
    - Test autocomplete returns valid options for each preference type
  - [x] 3.2 Create PreferencesCog at `/var/home/jako/Projects/prism/prism/cogs/preferences.py`
    - Follow LengthCog structure from `/var/home/jako/Projects/prism/prism/cogs/length.py`
    - Import SlashCommandGroup, option from discord.commands
    - Import basic_autocomplete from discord.utils
    - Create `preferences = SlashCommandGroup("preferences", "User preference settings")`
  - [x] 3.3 Implement `/preferences view` subcommand
    - Call `bot.prism_user_prefs.get(ctx.author.id)`
    - Format and display: response_length, emoji_density, preferred_persona
    - Use `await ctx.respond(...)` (PUBLIC, not ephemeral)
    - Show "Not set" or default values when appropriate
  - [x] 3.4 Implement static autocomplete for preference names
    - Create `_preference_name_autocomplete` returning: ["response_length", "emoji_density", "preferred_persona"]
  - [x] 3.5 Implement dynamic autocomplete for preference values
    - Create `_preference_value_autocomplete(ctx: AutocompleteContext)`
    - Check `ctx.options.get("preference")` to determine which preference is selected
    - For response_length: return ["concise", "balanced", "detailed"]
    - For emoji_density: return ["none", "minimal", "normal", "lots"]
    - For preferred_persona: reuse `_persona_name_autocomplete` pattern from personas.py (lines 22-45)
  - [x] 3.6 Implement `/preferences set <preference> <value>` subcommand
    - Two parameters with autocomplete
    - Validate preference name is one of the three valid options
    - For response_length: call `bot.prism_user_prefs.set_response_length()`
    - For emoji_density: call `bot.prism_user_prefs.set_emoji_density()`
    - For preferred_persona: validate persona exists via `bot.prism_personas.get(value)`, then call `set_preferred_persona()`
    - Allow "none" or empty for preferred_persona to clear it
    - Respond with confirmation message
  - [x] 3.7 Implement `/preferences reset` subcommand
    - Call `bot.prism_user_prefs.reset(ctx.author.id)`
    - Respond with "Preferences reset to defaults."
  - [x] 3.8 Create setup function with guild scoping
    - Follow pattern from length.py lines 36-51
    - Get `gids` from `bot.prism_cfg.command_guild_ids`
    - Scope command group and subcommands to guilds if configured
    - Call `bot.add_cog(PreferencesCog(bot))`
  - [x] 3.9 Load PreferencesCog in main.py
    - Add import: `from .cogs.preferences import setup as setup_preferences`
    - Call `setup_preferences(bot)` after other cog setups (after line 570)
  - [x] 3.10 Ensure command tests pass
    - Run ONLY the 4-6 tests written in 3.1
    - Verify commands respond correctly
    - Do NOT run the entire test suite at this stage

**Acceptance Criteria:**
- The 4-6 tests written in 3.1 pass
- `/preferences view` shows user's current settings publicly
- `/preferences set` updates preferences with validation
- `/preferences reset` clears all preferences
- Autocomplete works for both preference names and values

---

### Cleanup Layer

#### Task Group 4: Deprecation and Code Cleanup
**Dependencies:** Task Groups 1, 2, 3

- [x] 4.0 Complete deprecation of /length command
  - [x] 4.1 Write 2-4 focused tests for cleanup verification
    - Test LengthCog is not loaded
    - Test `/length` command no longer registered
    - Test SettingsService response_length methods still exist (for migration compatibility)
  - [x] 4.2 Remove LengthCog loading from main.py
    - Remove import: `from .cogs.length import setup as setup_length` (line 566)
    - Remove call: `setup_length(bot)` (line 570)
  - [x] 4.3 Delete length.py cog file
    - Remove `/var/home/jako/Projects/prism/prism/cogs/length.py`
  - [x] 4.4 Keep response_length in SettingsService for migration compatibility
    - Do NOT remove `set_response_length` and `resolve_response_length` from settings.py yet
    - Keep `response_length` in `DEFAULT_SETTINGS`
    - Add deprecation comment: `# DEPRECATED: Use UserPreferencesService for user-level response_length`
  - [x] 4.5 Ensure cleanup tests pass
    - Run ONLY the 2-4 tests written in 4.1
    - Verify /length command is gone
    - Do NOT run the entire test suite at this stage

**Acceptance Criteria:**
- The 2-4 tests written in 4.1 pass
- LengthCog no longer loaded
- length.py file deleted
- SettingsService maintains backward compatibility

---

### Testing Layer

#### Task Group 5: Test Review and Gap Analysis
**Dependencies:** Task Groups 1, 2, 3, 4

- [x] 5.0 Review existing tests and fill critical gaps only
  - [x] 5.1 Review tests from Task Groups 1-4
    - Review 4-6 tests from database layer (Task 1.1)
    - Review 4-6 tests from integration layer (Task 2.1)
    - Review 4-6 tests from command layer (Task 3.1)
    - Review 2-4 tests from cleanup layer (Task 4.1)
    - Total existing tests: approximately 14-22 tests
  - [x] 5.2 Analyze test coverage gaps for User Preferences System
    - Identify critical user workflows that lack coverage
    - Focus ONLY on gaps related to this feature
    - Prioritize end-to-end workflows:
      - User sets preference -> Bot uses preference in response
      - User resets preferences -> Bot falls back to defaults
      - User with preference interacts in multiple guilds
  - [x] 5.3 Write up to 8 additional strategic tests maximum
    - End-to-end: User sets response_length="concise" -> Response uses correct max_tokens
    - End-to-end: User sets emoji_density="none" -> Response has no emojis
    - End-to-end: User sets preferred_persona -> Response uses that persona
    - Integration: Persona autocomplete includes all available personas
    - Integration: Invalid preference value rejected with clear error
    - Edge case: User clears preferred_persona -> Falls back to guild persona
    - Edge case: Preferred persona deleted -> Graceful fallback
    - Migration: Database upgrades cleanly from v2 to v3
  - [x] 5.4 Run feature-specific tests only
    - Run ONLY tests related to User Preferences System
    - Expected total: approximately 22-30 tests maximum
    - Do NOT run the entire application test suite
    - Verify all critical workflows pass

**Acceptance Criteria:**
- All feature-specific tests pass (approximately 22-30 tests total)
- Critical user workflows covered
- No more than 8 additional tests added
- Testing focused exclusively on User Preferences System

---

## Execution Order

Recommended implementation sequence:

1. **Database Layer (Task Group 1)** - Create user_preferences table and UserPreferencesService
   - No dependencies
   - Establishes data foundation

2. **Service Layer (Task Group 2)** - Register service and integrate with response generation
   - Depends on Task Group 1
   - Connects preferences to bot behavior

3. **Command Layer (Task Group 3)** - Create /preferences slash commands
   - Depends on Task Groups 1, 2
   - Provides user interface for managing preferences

4. **Cleanup Layer (Task Group 4)** - Remove deprecated /length command
   - Depends on Task Groups 1, 2, 3
   - Must complete after new system is functional

5. **Testing Layer (Task Group 5)** - Review and fill test gaps
   - Depends on Task Groups 1, 2, 3, 4
   - Final validation of complete feature

---

## Key Files Reference

| File | Action | Purpose |
|------|--------|---------|
| `/var/home/jako/Projects/prism/prism/storage/migrations.py` | Modify | Add v3 migration |
| `/var/home/jako/Projects/prism/prism/services/user_preferences.py` | Create | New service |
| `/var/home/jako/Projects/prism/prism/services/settings.py` | Modify | Add deprecation comments |
| `/var/home/jako/Projects/prism/prism/cogs/preferences.py` | Create | New cog |
| `/var/home/jako/Projects/prism/prism/cogs/length.py` | Delete | Deprecated |
| `/var/home/jako/Projects/prism/prism/main.py` | Modify | Service registration, integration points |

## Pattern References

| Pattern | Source File | Lines |
|---------|-------------|-------|
| INSERT OR IGNORE atomic default creation | settings.py | 27-31 |
| ON CONFLICT DO UPDATE upsert | settings.py | 54-59 |
| SlashCommandGroup with subcommands | length.py | 16-33 |
| Guild scoping in setup function | length.py | 36-51 |
| Persona autocomplete | personas.py | 22-45 |
| Migration function structure | migrations.py | 27-37 |
