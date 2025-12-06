# Spec Requirements: Persona Duel

## Initial Description
Two personas argue about a user-suggested topic with slow message pacing to simulate real conversation, emoji reactions to each other's messages, configurable argument length/rounds, AI awareness of remaining time for strategic arguments, and a judge AI that declares a winner.

This is for a Discord bot with multiple AI personas. The bot already has:
- Multiple AI personas with distinct personalities
- Persona switching via slash commands
- AI-assisted custom persona creation
- Persona editing and deletion
- Per-channel contextual memory with 30-day retention
- Smart emoji suggestions based on context
- Automatic emoji enforcement in responses
- Guild-scoped configuration
- OpenRouter AI integration with fallback model support

## Requirements Discussion

### First Round Questions

**Q1:** How should the duel be triggered - slash command with persona selection, or user specifies both personas in the command?
**Answer:** User specifies both personas in the slash command (e.g., `/duel persona1:Gizmo persona2:Luna topic:"pineapple on pizza"`)

**Q2:** What simulates "slow message pacing" - typing indicators with delay?
**Answer:** Typing indicators with delay that scales with message length

**Q3:** Should the feature support both rounds mode and time mode for duration?
**Answer:** Support BOTH rounds mode and time mode

**Q4:** What are the default and maximum limits for rounds and time?
**Answer:**
- Rounds mode: Default 3 rounds, Max 10 rounds
- Time mode: Default 2 minutes, Max 5 minutes

**Q5:** How should emoji reactions work - should personas react to every message?
**Answer:** Personas react to every message, use custom guild emojis when available, ensure variety in reactions

**Q6:** Who is the judge - one of the personas, a neutral AI, or something else?
**Answer:** A neutral "Judge AI" with no persona personality that explains reasoning AND declares winner

**Q7:** How should the AI know about remaining time - explicit announcements or implicit awareness?
**Answer:** AI implicitly knows rules and remaining time for strategic arguments (no explicit "final round" message)

**Q8:** Should there be a way to stop a duel early?
**Answer:** Command to cancel, no judgment when stopped early

**Q9:** What features are explicitly out of scope?
**Answer:** No audience voting, betting systems, persistent leaderboards, or spectator reactions

### Existing Code to Reference

No similar existing features identified for reference. However, the existing codebase has:
- Persona switching via slash commands (pattern for command structure)
- Smart emoji suggestions (can be leveraged for reaction variety)
- Automatic emoji enforcement (existing emoji handling logic)
- OpenRouter AI integration (AI communication patterns)

### Follow-up Questions

No additional follow-up questions were needed.

## Visual Assets

### Files Provided:
No visual assets provided.

### Visual Insights:
N/A

## Requirements Summary

### Functional Requirements
- Slash command trigger: `/duel persona1:[name] persona2:[name] topic:"[topic]"`
- Two personas engage in a debate/argument about the specified topic
- Typing indicators shown before each message with delay scaling by message length
- Support two duration modes:
  - Rounds mode: configurable number of back-and-forth exchanges
  - Time mode: configurable duration limit
- Both personas react with emojis to every message from the other
- Prefer custom guild emojis when available
- Ensure variety in emoji reactions (avoid repetition)
- AI personas implicitly aware of debate progress for strategic argument pacing
- Neutral Judge AI (without persona personality) concludes the duel
- Judge explains reasoning and declares a winner
- Early stop command available to cancel duel (no judgment issued)

### Reusability Opportunities
- Existing slash command patterns from persona switching
- Smart emoji suggestion system for reaction variety
- Automatic emoji enforcement logic
- OpenRouter AI integration for all AI communications
- Guild-scoped configuration patterns

### Scope Boundaries

**In Scope:**
- Slash command to initiate duel with persona and topic selection
- Typing indicator simulation with length-based delays
- Rounds mode (default 3, max 10)
- Time mode (default 2 min, max 5 min)
- Emoji reactions from both personas to each message
- Guild emoji preference with variety enforcement
- Neutral Judge AI with reasoning and winner declaration
- Implicit strategic awareness of remaining time/rounds
- Early stop/cancel command

**Out of Scope:**
- Audience voting system
- Betting systems
- Persistent leaderboards
- Spectator reactions
- Explicit "final round" announcements

### Technical Considerations
- Integration with existing persona system for loading persona personalities
- Integration with OpenRouter for AI responses
- Use of Discord typing indicators API
- Access to guild custom emoji collection
- Timing/scheduling for message delays and time-based mode
- State management for tracking active duels
- Command handling for early stop functionality
