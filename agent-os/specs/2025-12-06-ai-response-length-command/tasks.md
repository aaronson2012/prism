# Task Breakdown: AI Response Length Command

## Overview
Total Tasks: 10

This feature adds Discord slash commands (`/length set` and `/length view`) to configure AI response length preferences at the guild level. The implementation leverages existing patterns from the persona and memory cogs.

## Task List

### Settings Layer

#### Task Group 1: SettingsService Updates
**Dependencies:** None

- [x] 1.0 Complete settings layer updates
  - [x] 1.1 Add `response_length` to DEFAULT_SETTINGS dictionary
    - File: `/var/home/jako/Projects/prism/prism/services/settings.py`
    - Add key `"response_length": "balanced"` to the `DEFAULT_SETTINGS` dict
    - This ensures new guilds automatically receive the default value
  - [x] 1.2 Add `set_response_length()` method to SettingsService
    - Follow the pattern from `set_persona()` method
    - Accept `guild_id: int` and `length: str` parameters
    - Validate that `length` is one of: "concise", "balanced", "detailed"
    - Update the guild settings JSON with the new `response_length` value
  - [x] 1.3 Add `resolve_response_length()` method to SettingsService
    - Follow the pattern from `resolve_persona_name()` method
    - Accept `guild_id: int` parameter
    - Return the stored `response_length` value or default to "balanced"
  - [x] 1.4 Verify settings methods work correctly
    - Manually test by importing and calling the new methods
    - Confirm values persist to and retrieve from database

**Acceptance Criteria:**
- DEFAULT_SETTINGS includes `response_length: "balanced"`
- `set_response_length()` persists valid values to guild settings
- `set_response_length()` rejects invalid length values
- `resolve_response_length()` returns stored value or default

### Cog Implementation

#### Task Group 2: LengthCog Creation
**Dependencies:** Task Group 1

- [x] 2.0 Complete LengthCog implementation
  - [x] 2.1 Create `/var/home/jako/Projects/prism/prism/cogs/length.py`
    - Follow the structure from `memory.py` and `personas.py`
    - Import discord, logging, SlashCommandGroup, option
    - Create `LengthCog` class extending `discord.Cog`
    - Define `length = SlashCommandGroup("length", "Response length settings")`
  - [x] 2.2 Implement `/length set` command
    - Use `@length.command(name="set", description="Set AI response length for this guild")`
    - Use `@option("length", str, description="Response length preference", required=True, choices=["concise", "balanced", "detailed"])`
    - Check guild context: `if not ctx.guild: return error`
    - Call `bot.prism_settings.set_response_length(guild_id, length)`
    - Respond with confirmation: "Response length set to '[length]' for this guild."
  - [x] 2.3 Implement `/length view` command
    - Use `@length.command(name="view", description="View current AI response length setting")`
    - Check guild context: `if not ctx.guild: return error`
    - Call `bot.prism_settings.resolve_response_length(guild_id)`
    - Respond with: "Current response length: [length]"
  - [x] 2.4 Implement `setup()` function with guild_ids scoping
    - Follow pattern from `memory.py` setup function
    - Get `gids` from `bot.prism_cfg.command_guild_ids`
    - Apply `guild_ids` to command group and subcommands if configured
    - Call `bot.add_cog(LengthCog(bot))`

**Acceptance Criteria:**
- LengthCog follows established cog patterns
- `/length set` accepts only valid preset choices
- `/length set` persists selection to guild settings
- `/length view` displays current setting or default
- Both commands require guild context (no DMs)
- Guild_ids scoping applies when configured

### System Prompt Integration

#### Task Group 3: Response Length Prompt Injection
**Dependencies:** Task Group 1

- [x] 3.0 Complete system prompt integration
  - [x] 3.1 Create length guidance text mapping
    - Define mapping in `main.py` near the `_generate_and_reply()` function:
      - "concise": "Keep responses brief and direct; aim for 1-2 sentences when possible."
      - "balanced": "Provide complete answers but avoid over-explaining; use standard response length."
      - "detailed": "Give thorough, comprehensive responses with full context and explanations."
  - [x] 3.2 Resolve response length preference in `_generate_and_reply()`
    - After resolving persona, call `bot.prism_settings.resolve_response_length(guild_id)`
    - Look up the corresponding guidance text from the mapping
  - [x] 3.3 Inject length guidance into system prompt
    - Insert the length guidance text after `base_rules` and before persona prompt
    - Format: `system_prompt = base_rules + "\n\n" + length_guidance + "\n\n" + persona_prompt`
    - Alternatively, append after the persona prompt if cleaner

**Acceptance Criteria:**
- Response length preference is resolved for each message
- Appropriate guidance text is injected into system prompt
- Default "balanced" guidance applies when no preference is set
- Guidance appears in system prompt alongside existing rules

### Registration

#### Task Group 4: Cog Registration
**Dependencies:** Task Groups 2, 3

- [x] 4.0 Complete cog registration
  - [x] 4.1 Import LengthCog setup in main.py
    - Add import: `from .cogs.length import setup as setup_length`
    - Place alongside existing cog imports (personas, memory)
  - [x] 4.2 Register LengthCog in amain()
    - Call `setup_length(bot)` after `setup_memory(bot)`
    - Follow the established cog loading pattern
  - [x] 4.3 End-to-end verification
    - Start the bot and verify cog loads without errors
    - Test `/length set concise` in a guild channel
    - Test `/length view` shows the updated setting
    - Verify the setting persists across bot restart
    - Confirm response length guidance appears in AI responses

**Acceptance Criteria:**
- LengthCog loads successfully on bot startup
- Commands appear in Discord slash command list
- Setting persists across bot restarts
- AI responses reflect the configured length preference

## Execution Order

Recommended implementation sequence:

1. **Settings Layer (Task Group 1)** - Add default setting and service methods
2. **Cog Implementation (Task Group 2)** - Create the length cog with commands
3. **System Prompt Integration (Task Group 3)** - Inject length guidance into prompts
4. **Registration (Task Group 4)** - Wire up the cog and verify end-to-end

Note: Task Groups 2 and 3 can be developed in parallel as they only share a dependency on Task Group 1. Task Group 4 requires both to be complete for integration testing.

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `/var/home/jako/Projects/prism/prism/services/settings.py` | Modify | Add DEFAULT_SETTINGS key, set/resolve methods |
| `/var/home/jako/Projects/prism/prism/cogs/length.py` | Create | New cog with /length commands |
| `/var/home/jako/Projects/prism/prism/main.py` | Modify | Import cog, register cog, inject prompt guidance |

## Reference Patterns

- **SettingsService methods:** Follow `set_persona()` and `resolve_persona_name()` in `settings.py`
- **Cog structure:** Follow `MemoryCog` in `memory.py` for minimal cog template
- **Command options:** Follow `PersonaCog` in `personas.py` for `@option` decorator usage
- **System prompt:** See line 319 in `main.py` where `base_rules` and persona prompt combine
- **Cog registration:** See lines 540-544 in `main.py` for import and setup pattern
