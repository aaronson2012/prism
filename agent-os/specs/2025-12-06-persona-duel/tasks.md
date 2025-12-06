# Task Breakdown: Persona Duel

## Overview
Total Tasks: 24

This feature enables two AI personas to engage in a timed or round-based debate on a user-specified topic with realistic pacing, emoji reactions, strategic awareness, and a neutral judge declaring the winner.

## Task List

### Core Infrastructure

#### Task Group 1: Duel State Management
**Dependencies:** None

- [x] 1.0 Complete duel state management infrastructure
  - [x] 1.1 Write 3-5 focused tests for DuelState functionality
    - Test DuelState dataclass creation with all required fields
    - Test active duels dictionary storage and retrieval by channel_id
    - Test duel state cleanup after completion
    - Test rejection of new duel when one is already active in channel
  - [x] 1.2 Create DuelState dataclass in new file `/var/home/jako/Projects/prism/prism/models/duel.py`
    - Fields: channel_id, persona1, persona2, topic, mode, duration, current_round, start_time, messages (list), used_reactions (set)
    - Import from dataclasses module
    - Add type hints for all fields
  - [x] 1.3 Create DuelMode enum for mode selection
    - Values: ROUNDS, TIME
    - Include default values: rounds=3, time=120 (seconds)
    - Include max values: rounds=10, time=300 (seconds)
  - [x] 1.4 Add helper methods to DuelState
    - `is_complete()` - check if duel has reached end condition
    - `get_elapsed_time()` - return elapsed time in seconds
    - `get_remaining_time()` - return remaining time for time mode
    - `increment_round()` - advance round counter
  - [x] 1.5 Ensure duel state tests pass
    - Run ONLY the 3-5 tests written in 1.1
    - Verify dataclass initialization works correctly
    - Do NOT run the entire test suite at this stage

**Acceptance Criteria:**
- The 3-5 tests written in 1.1 pass
- DuelState dataclass properly stores all required fields
- DuelMode enum correctly defines mode options with defaults and limits
- Helper methods accurately track duel progress

---

### Slash Command Layer

#### Task Group 2: Duel Slash Commands
**Dependencies:** Task Group 1

- [x] 2.0 Complete duel slash command implementation
  - [x] 2.1 Write 4-6 focused tests for duel commands
    - Test `/duel start` command with valid personas and topic
    - Test `/duel start` rejection when personas do not exist
    - Test `/duel start` rejection when same persona specified for both
    - Test `/duel start` rejection when duel already active in channel
    - Test `/duel stop` cancels active duel
    - Test `/duel stop` returns error when no active duel
  - [x] 2.2 Create DuelCog class in `/var/home/jako/Projects/prism/prism/cogs/duel.py`
    - Follow pattern from `/var/home/jako/Projects/prism/prism/cogs/personas.py`
    - Initialize with bot reference
    - Create SlashCommandGroup for "duel" commands
  - [x] 2.3 Implement `_persona_name_autocomplete` for persona selection
    - Reuse pattern from PersonaCog._persona_name_autocomplete
    - Return list of OptionChoice with persona names
    - Filter by query string for autocomplete
  - [x] 2.4 Implement `/duel start` subcommand
    - Options: persona1 (autocomplete), persona2 (autocomplete), topic (string), mode (choice: rounds/time), duration (int)
    - Validate both personas exist using `bot.prism_personas.get()`
    - Validate personas are different
    - Check no active duel in channel via `bot.prism_active_duels`
    - Create DuelState and store in `bot.prism_active_duels[channel_id]`
    - Respond with duel start announcement
  - [x] 2.5 Implement `/duel stop` subcommand
    - Check for active duel in current channel
    - Remove duel from `bot.prism_active_duels`
    - Post cancellation message (no judgment rendered)
    - Return error if no active duel
  - [x] 2.6 Add setup() function for cog registration
    - Follow pattern from personas.py setup()
    - Apply guild_ids scoping from config
    - Register cog with bot
  - [x] 2.7 Ensure duel command tests pass
    - Run ONLY the 4-6 tests written in 2.1
    - Verify command registration and validation
    - Do NOT run the entire test suite at this stage

**Acceptance Criteria:**
- The 4-6 tests written in 2.1 pass
- `/duel start` properly validates and initiates duels
- `/duel stop` properly cancels active duels
- Autocomplete works for persona selection
- Proper error messages for invalid inputs

---

### Duel Execution Engine

#### Task Group 3: Typing Simulation and Message Pacing
**Dependencies:** Task Group 2

- [x] 3.0 Complete typing indicator simulation
  - [x] 3.1 Write 2-4 focused tests for typing simulation
    - Test delay calculation scales with message length
    - Test delay is capped at 8 seconds maximum
    - Test base delay of 1.5 seconds for short messages
    - Test typing context manager is called before message send
  - [x] 3.2 Create typing delay calculator function
    - Base delay: 1.5 seconds
    - Additional: 0.02 seconds per character
    - Maximum cap: 8 seconds
    - Location: add to duel.py cog or create utility module
  - [x] 3.3 Implement typing simulation wrapper
    - Use `async with channel.typing()` context manager
    - Call `asyncio.sleep()` with calculated delay
    - Follow pattern from `/var/home/jako/Projects/prism/prism/main.py` lines 502-507
  - [x] 3.4 Ensure typing simulation tests pass
    - Run ONLY the 2-4 tests written in 3.1
    - Verify delay calculations are correct
    - Do NOT run the entire test suite at this stage

**Acceptance Criteria:**
- The 2-4 tests written in 3.1 pass
- Typing delay correctly scales with message length
- Delay never exceeds 8 seconds
- Typing indicator displays during delay

---

#### Task Group 4: Duel Loop and AI Communication
**Dependencies:** Task Groups 2, 3

- [x] 4.0 Complete duel execution loop
  - [x] 4.1 Write 4-6 focused tests for duel loop
    - Test rounds mode completes after configured number of rounds
    - Test time mode completes after configured duration
    - Test personas alternate correctly
    - Test strategic awareness injection into system prompt
    - Test conversation history passed to AI
  - [x] 4.2 Implement rounds mode loop
    - Iterate for configured number of rounds
    - Each round: persona1 speaks, then persona2 responds
    - Track current round in DuelState
    - Check `duel_state.is_complete()` between exchanges
  - [x] 4.3 Implement time mode loop
    - Use `time.monotonic()` or `asyncio.get_event_loop().time()` for timing
    - Alternate between personas until time expires
    - Track elapsed/remaining time in DuelState
    - Allow current speaker to finish after time expires
  - [x] 4.4 Implement strategic awareness injection
    - For rounds mode: "This is round X of Y. Pace your arguments accordingly."
    - For time mode: "Approximately X seconds remaining. Pace your arguments accordingly."
    - Inject into persona system prompt before each AI call
    - Do NOT announce in channel (prompt injection only)
  - [x] 4.5 Implement persona AI response generation
    - Load persona via `bot.prism_personas.get(persona_name)`
    - Build system prompt: persona.data.system_prompt + strategic awareness
    - Build messages list with duel conversation history
    - Call `bot.prism_orc.chat_completion()` for response
    - Use persona.data.model and persona.data.temperature if set
  - [x] 4.6 Ensure duel loop tests pass
    - Run ONLY the 4-6 tests written in 4.1
    - Verify both modes execute correctly
    - Do NOT run the entire test suite at this stage

**Acceptance Criteria:**
- The 4-6 tests written in 4.1 pass
- Rounds mode completes correct number of exchanges
- Time mode respects duration limit
- Strategic awareness properly injected
- Personas respond with appropriate personalities

---

### Emoji Reactions

#### Task Group 5: Emoji Reaction System
**Dependencies:** Task Group 4

- [x] 5.0 Complete emoji reaction system
  - [x] 5.1 Write 3-5 focused tests for emoji reactions
    - Test opposing persona adds reaction after each message
    - Test custom guild emojis preferred when available
    - Test used reactions tracked to ensure variety
    - Test fallback to Unicode when custom exhausted
  - [x] 5.2 Implement emoji suggestion integration
    - Use `EmojiIndexService.suggest_for_text()` for contextual suggestions
    - Pass guild_id and message content
    - Reference pattern from `/var/home/jako/Projects/prism/prism/services/emoji_index.py`
  - [x] 5.3 Implement reaction variety tracking
    - Store used reaction tokens in DuelState.used_reactions set
    - Filter out already-used emojis from suggestions
    - Track separately for each duel instance
  - [x] 5.4 Implement reaction adding logic
    - After persona message sent, get emoji for opposing persona's reaction
    - Use `message.add_reaction()` to add the emoji
    - Handle custom emoji format: `<:name:id>` or `<a:name:id>`
    - Fall back to Unicode emoji if no custom available or all used
  - [x] 5.5 Ensure emoji reaction tests pass
    - Run ONLY the 3-5 tests written in 5.1
    - Verify reactions are added correctly
    - Do NOT run the entire test suite at this stage

**Acceptance Criteria:**
- The 3-5 tests written in 5.1 pass
- Opposing persona reacts to each message
- Custom guild emojis preferred
- No duplicate reactions within a duel
- Graceful fallback to Unicode emojis

---

### Judge AI

#### Task Group 6: Neutral Judge AI
**Dependencies:** Task Groups 4, 5

- [x] 6.0 Complete neutral judge AI implementation
  - [x] 6.1 Write 3-4 focused tests for judge AI
    - Test judge receives complete duel transcript
    - Test judge provides reasoning and declares winner
    - Test judge uses neutral system prompt (no persona personality)
    - Test judge response formatted correctly for Discord
  - [x] 6.2 Create judge system prompt
    - Emphasize objectivity and fair evaluation
    - Instruct to review argument strength, not persona popularity
    - Request 2-3 sentences of reasoning
    - Request clear winner declaration
    - Store as constant in duel module
  - [x] 6.3 Implement judge invocation
    - Collect all messages from DuelState.messages
    - Build conversation history for judge review
    - Call `bot.prism_orc.chat_completion()` with judge system prompt
    - Do NOT use any persona personality
  - [x] 6.4 Implement judge response formatting
    - Parse judge response for reasoning and winner
    - Format as clear Discord message with bold/emphasis
    - Post as final message in channel
  - [x] 6.5 Ensure judge AI tests pass
    - Run ONLY the 3-4 tests written in 6.1
    - Verify judge evaluates correctly
    - Do NOT run the entire test suite at this stage

**Acceptance Criteria:**
- The 3-4 tests written in 6.1 pass
- Judge reviews complete duel transcript
- Judge provides objective reasoning
- Winner clearly declared
- Output formatted for Discord readability

---

### Integration and Cleanup

#### Task Group 7: Bot Integration and Cleanup
**Dependencies:** Task Groups 1-6

- [x] 7.0 Complete bot integration
  - [x] 7.1 Initialize active duels dictionary on bot
    - Add `bot.prism_active_duels = {}` in `/var/home/jako/Projects/prism/prism/main.py`
    - Add after other service attachments (around line 580)
  - [x] 7.2 Register DuelCog in main.py
    - Import setup function from duel cog
    - Call setup(bot) after other cog registrations
    - Follow pattern from personas, memory, preferences cogs
  - [x] 7.3 Implement duel state cleanup
    - Remove duel from active duels after completion
    - Remove duel from active duels after cancellation
    - Handle edge cases (channel deleted, bot disconnected)
  - [x] 7.4 Add error handling for duel execution
    - Catch AI communication errors
    - Catch Discord API errors (message send, reaction add)
    - Post error message and cleanup duel state on failure
    - Log errors for debugging

**Acceptance Criteria:**
- Bot properly initializes active duels storage
- DuelCog registered and commands available
- Duel state cleaned up in all scenarios
- Errors handled gracefully with user feedback

---

### Testing

#### Task Group 8: Test Review and Gap Analysis
**Dependencies:** Task Groups 1-7

- [x] 8.0 Review existing tests and fill critical gaps only
  - [x] 8.1 Review tests from Task Groups 1-7
    - Review the 3-5 tests from Task 1.1 (DuelState)
    - Review the 4-6 tests from Task 2.1 (slash commands)
    - Review the 2-4 tests from Task 3.1 (typing simulation)
    - Review the 4-6 tests from Task 4.1 (duel loop)
    - Review the 3-5 tests from Task 5.1 (emoji reactions)
    - Review the 3-4 tests from Task 6.1 (judge AI)
    - Total existing tests: approximately 19-30 tests
  - [x] 8.2 Analyze test coverage gaps for Persona Duel feature only
    - Identify critical end-to-end workflows lacking coverage
    - Focus ONLY on gaps related to duel feature requirements
    - Do NOT assess entire application test coverage
    - Prioritize integration between components over unit test gaps
  - [x] 8.3 Write up to 10 additional strategic tests maximum
    - Focus on end-to-end duel flow: start -> exchanges -> judge -> cleanup
    - Test error scenarios: AI failure mid-duel, persona deleted during duel
    - Test concurrent duel attempts in same channel
    - Test mode transitions and edge cases
    - Do NOT write comprehensive coverage for all scenarios
  - [x] 8.4 Run feature-specific tests only
    - Run ONLY tests related to Persona Duel feature
    - Expected total: approximately 29-40 tests maximum
    - Do NOT run the entire application test suite
    - Verify critical workflows pass

**Acceptance Criteria:**
- All feature-specific tests pass (approximately 29-40 tests total)
- Critical duel workflows covered end-to-end
- No more than 10 additional tests added when filling gaps
- Testing focused exclusively on Persona Duel feature requirements

---

## Execution Order

Recommended implementation sequence:

1. **Task Group 1: Duel State Management** - Foundation data structures
2. **Task Group 2: Duel Slash Commands** - User-facing command interface
3. **Task Group 3: Typing Simulation** - Message pacing mechanics
4. **Task Group 4: Duel Loop and AI** - Core duel execution logic
5. **Task Group 5: Emoji Reactions** - Interactive reaction system
6. **Task Group 6: Neutral Judge AI** - Winner determination
7. **Task Group 7: Bot Integration** - Wire everything together
8. **Task Group 8: Test Review** - Validate complete implementation

---

## Files to Create/Modify

### New Files
- `/var/home/jako/Projects/prism/prism/models/duel.py` - DuelState dataclass and DuelMode enum
- `/var/home/jako/Projects/prism/prism/cogs/duel.py` - DuelCog with slash commands and duel logic
- `/var/home/jako/Projects/prism/tests/test_duel.py` - Feature-specific tests

### Modified Files
- `/var/home/jako/Projects/prism/prism/main.py` - Add active duels dict and register DuelCog

---

## Existing Code to Leverage

| Component | Source File | Pattern/Function to Reuse |
|-----------|-------------|---------------------------|
| SlashCommandGroup | `/var/home/jako/Projects/prism/prism/cogs/personas.py` | Line 19, persona group definition |
| Autocomplete | `/var/home/jako/Projects/prism/prism/cogs/personas.py` | Lines 22-45, `_persona_name_autocomplete` |
| Typing indicator | `/var/home/jako/Projects/prism/prism/main.py` | Lines 502-507, `async with message.channel.typing()` |
| AI chat completion | `/var/home/jako/Projects/prism/prism/services/openrouter_client.py` | `OpenRouterClient.chat_completion()` |
| Persona loading | `/var/home/jako/Projects/prism/prism/services/personas.py` | `PersonasService.get()`, `PersonaModel` |
| Emoji suggestions | `/var/home/jako/Projects/prism/prism/services/emoji_index.py` | `EmojiIndexService.suggest_for_text()` |
| Cog setup pattern | `/var/home/jako/Projects/prism/prism/cogs/personas.py` | Lines 229-244, `setup()` function |
| Service attachment | `/var/home/jako/Projects/prism/prism/main.py` | Lines 558-581, `bot.prism_*` pattern |
