# Specification: Persona Duel

## Goal
Enable two AI personas to engage in a timed or round-based debate on a user-specified topic with realistic pacing, emoji reactions, strategic awareness, and a neutral judge declaring the winner.

## User Stories
- As a Discord user, I want to start a duel between two personas so that I can watch them argue about a topic for entertainment.
- As a Discord user, I want to cancel an ongoing duel so that I can stop it if needed without a judgment being rendered.

## Specific Requirements

**Slash Command: `/duel`**
- Command signature: `/duel persona1:[name] persona2:[name] topic:"[topic]" mode:[rounds|time] duration:[number]`
- `persona1` and `persona2` options use autocomplete from existing personas (reuse `_persona_name_autocomplete` pattern)
- `mode` option defaults to "rounds" with choices: "rounds" or "time"
- `duration` option: for rounds mode (default 3, max 10), for time mode (default 2 minutes, max 5 minutes)
- Validate both personas exist before starting; respond with error if not found
- Validate personas are different; do not allow dueling the same persona against itself
- Only one duel per channel at a time; reject new duels if one is active

**Typing Indicator Simulation**
- Show typing indicator before each persona message using `channel.typing()` context manager
- Delay duration scales with message length: base 1.5 seconds + 0.02 seconds per character (capped at 8 seconds)
- Use `asyncio.sleep()` during typing to simulate natural composition time
- Typing indicator provides visual feedback that a response is being prepared

**Rounds Mode Behavior**
- Each round consists of persona1 speaking, then persona2 responding
- Continue for the configured number of rounds (default 3, max 10)
- Track current round and total rounds for strategic awareness injection

**Time Mode Behavior**
- Personas alternate messages until the time limit expires
- Track elapsed time and remaining time for strategic awareness injection
- After time expires, current speaker finishes their message before judging
- Use `asyncio.get_event_loop().time()` or `time.monotonic()` for timing

**Emoji Reactions**
- After each persona message, the opposing persona reacts with an emoji
- Use `message.add_reaction()` to add the emoji reaction
- Prefer custom guild emojis when available (use `EmojiIndexService.suggest_for_text()`)
- Track used reactions per duel to ensure variety; avoid repeating the same emoji
- Fall back to Unicode emojis if no custom emojis available or all have been used

**Strategic Awareness Injection**
- Inject round/time context into each persona's system prompt during the duel
- For rounds mode: "This is round X of Y. Pace your arguments accordingly."
- For time mode: "Approximately X seconds remaining. Pace your arguments accordingly."
- Do NOT announce "final round" explicitly in the channel; only inject context into AI prompt

**Neutral Judge AI**
- After the duel concludes, invoke a neutral Judge AI (not using any persona personality)
- Judge reviews all messages exchanged and evaluates argument strength
- Judge provides 2-3 sentences of reasoning followed by declaring a winner
- Use a dedicated system prompt for the judge that emphasizes objectivity and fair evaluation
- Post judgment as a final message in the channel with clear formatting

**Early Stop Command**
- Implement `/duel stop` subcommand to cancel an active duel in the current channel
- When stopped early, post a message indicating the duel was cancelled
- No judgment is rendered when a duel is cancelled early
- Only allow stopping duels in the channel where the command is issued

**Duel State Management**
- Create a `DuelState` dataclass to track: channel_id, persona1, persona2, topic, mode, duration, current_round, start_time, messages, used_reactions
- Store active duels in a dictionary keyed by channel_id on the bot instance (e.g., `bot.prism_active_duels`)
- Clean up duel state after completion or cancellation

## Visual Design
No visual assets provided.

## Existing Code to Leverage

**`/var/home/jako/Projects/prism/prism/cogs/personas.py` - Slash Command Patterns**
- Reuse `SlashCommandGroup` pattern for `/duel` command group
- Reuse `_persona_name_autocomplete` static method for persona selection options
- Follow `ctx.defer()` and `ctx.respond()` patterns for command responses
- Use `setup()` function pattern with guild_ids scoping for command registration

**`/var/home/jako/Projects/prism/prism/services/openrouter_client.py` - AI Communication**
- Use `OpenRouterClient.chat_completion()` for all persona and judge AI responses
- Pass messages list with system prompt and conversation history
- Handle errors with fallback model support already built-in

**`/var/home/jako/Projects/prism/prism/services/personas.py` - Persona Loading**
- Use `PersonasService.get()` to load persona data by name
- Access `PersonaModel.system_prompt` for persona personality injection
- Access `PersonaModel.model` and `PersonaModel.temperature` for model configuration

**`/var/home/jako/Projects/prism/prism/services/emoji_index.py` - Emoji Suggestions**
- Use `EmojiIndexService.suggest_for_text()` to get contextual emoji suggestions
- Returns list of emoji tokens (custom format `<:name:id>` or Unicode characters)
- Pass guild_id and message content to get relevant suggestions

**`/var/home/jako/Projects/prism/prism/main.py` - Typing Indicator Pattern**
- Reuse `async with message.channel.typing()` pattern for typing indicators
- Follow `_clip_reply_to_limit()` for Discord message length enforcement
- Use existing bot service attachment pattern (e.g., `bot.prism_personas`, `bot.prism_emoji`)

## Out of Scope
- Audience voting system for determining winners
- Betting or wagering systems on duel outcomes
- Persistent leaderboards tracking wins/losses per persona
- Spectator reactions or audience participation during duels
- Explicit "final round" announcements visible in the channel
- Multi-channel duels or duels spanning multiple servers
- Saving duel transcripts or replay functionality
- Configurable judge persona (always uses neutral judge)
- Tournament brackets or multi-round elimination systems
- Voice channel integration or TTS for duel messages
