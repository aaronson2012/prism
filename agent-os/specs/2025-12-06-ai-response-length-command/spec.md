# Specification: AI Response Length Command

## Goal
Add Discord slash commands to configure and view AI response length preferences at the guild level, allowing server admins to control how verbose or concise the bot's responses are.

## User Stories
- As a server admin, I want to set the AI response length for my guild so that the bot's replies match our community's communication style.
- As a server member, I want to view the current response length setting so I understand how the bot will respond.

## Specific Requirements

**`/length set` command**
- Create a slash command `/length set <option>` that accepts one of three preset values: "concise", "balanced", "detailed"
- The command must only work within a guild context (not DMs)
- Store the selected option in the guild's settings JSON using the existing SettingsService pattern
- Respond with a confirmation message indicating the new setting
- Follow the same guild-scoping pattern used by persona and memory cogs

**`/length view` command**
- Create a slash command `/length view` that displays the current response length setting for the guild
- Return "balanced" as the displayed value when no setting has been configured (the default)
- Format the response clearly to show the current setting

**Response length storage**
- Add a new key `response_length` to the guild settings JSON structure
- Default value is "balanced" when the key is not present
- Use the existing SettingsService.get() and SettingsService.set() methods for storage
- No database schema changes needed; settings table already stores JSON data

**Default settings update**
- Add `response_length: "balanced"` to the DEFAULT_SETTINGS dictionary in settings.py
- This ensures new guilds automatically have the default applied

**System prompt integration**
- Add a helper method to resolve the response length preference for a guild
- Inject length guidance into the system prompt based on the setting:
  - "concise": Brief, direct responses; 1-2 sentences when possible
  - "balanced": Standard response length; answer completely but avoid over-explaining
  - "detailed": Thorough, comprehensive responses; provide full context and explanations
- Insert the length instruction near the existing base guidelines in the system prompt

**LengthCog implementation**
- Create a new cog file `prism/cogs/length.py` following the patterns from memory.py and personas.py
- Use SlashCommandGroup("length", "Response length settings") for the command group
- Register the cog in main.py alongside existing cogs
- Apply guild_ids scoping if command_guild_ids is configured

## Existing Code to Leverage

**`/var/home/jako/Projects/prism/prism/services/settings.py` - SettingsService**
- Use SettingsService.get() to retrieve guild settings JSON
- Use SettingsService.set() to persist updated settings
- Follow the pattern of set_persona() for adding a set_response_length() method
- Add resolve_response_length() method similar to resolve_persona_name()

**`/var/home/jako/Projects/prism/prism/cogs/memory.py` - MemoryCog pattern**
- Follow the SlashCommandGroup pattern for creating the /length command group
- Replicate the guild context check pattern (if not ctx.guild: return error)
- Copy the setup() function pattern for guild_ids scoping

**`/var/home/jako/Projects/prism/prism/main.py` - System prompt construction**
- The system prompt is built around line 319 combining base_rules and persona prompt
- Insert length preference guidance after base_rules using the resolved setting
- Load the cog using the same pattern as setup_personas and setup_memory

**`/var/home/jako/Projects/prism/prism/cogs/personas.py` - Command options pattern**
- Use the @option decorator pattern for the preset choices
- Follow the same response formatting style for user feedback

## Out of Scope
- User-specific response length overrides (setting is guild-wide only)
- Channel-specific response length settings
- Custom or numeric response length values beyond the three presets
- Character count limits or token limits
- Response length enforcement at generation time (only prompt guidance)
- Admin permission checks for setting the length (any guild member can set it)
- Slash command autocomplete for the preset options (use choices instead)
- Response length analytics or logging
- Migration from any previous settings format
- Unit tests for the new functionality
