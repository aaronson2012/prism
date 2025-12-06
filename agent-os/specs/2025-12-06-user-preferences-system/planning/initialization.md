# User Preferences System

## Feature Name
User Preferences System

## Description from Roadmap

This feature combines three related items:

1. **User Preferences Storage** (Size: S) - Store per-user preferences in the database (preferred persona, response style, etc.) that persist across sessions

2. **User Preference Commands** (Size: S) - Slash commands for users to view and update their personal preferences (`/preferences view`, `/preferences set`)

3. **Per-User Response Customization** (Size: M) - Apply stored user preferences when generating responses (e.g., verbosity level, formality, emoji density)

## Context

This is a Discord bot (Prism) that uses AI personas to interact with users. The bot already has:
- Multiple AI personas with distinct personalities
- Per-channel contextual memory with 30-day retention
- Guild-scoped configuration
- OpenRouter AI integration

The User Preferences System will allow individual users to customize how the bot responds to them specifically.

## Raw Idea

Create a system that allows individual Discord users to set and store their personal preferences for how the AI bot responds to them. This includes:

- Storing preferences in the database that persist across sessions
- Slash commands to view and modify preferences
- Applying those preferences when generating AI responses

This enables personalization at the user level, complementing the existing guild-level configuration.
