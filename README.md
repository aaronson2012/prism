# Prism Discord Bot

Prism is an intelligent Discord AI bot powered by OpenRouter that brings personality-driven conversations, contextual memory, and engaging emoji integration to your Discord server.

## ✨ Features

### 🎭 Multiple AI Personas
Switch between different AI personalities to match the mood and context of your server. Each persona has unique traits, communication styles, and behavior patterns.

### 🧠 Contextual Memory
Maintains conversation history per channel with automatic message pruning (30-day retention). The bot remembers recent context to provide more relevant and coherent responses.

### 😊 Emoji Intelligence
- **Smart Emoji Suggestions**: AI suggests relevant custom server emojis and Unicode emojis based on message context
- **Automatic Emoji Enforcement**: Ensures engaging responses with at least one emoji per sentence (configurable)
- **Emoji Deduplication**: Prevents repetitive emoji usage in responses
- **Custom Emoji Descriptions**: Automatically generates descriptive metadata for server emojis

### 🛠️ Custom Persona Creation
Create new personas using AI assistance - just provide a brief description and let the bot generate a complete personality profile with system prompts.

### 🌍 Guild-Scoped Configuration
Each Discord server maintains its own settings and active persona selection.

## 📋 Requirements

- **Python**: 3.11 or higher
- **Discord Bot Token**: From Discord Developer Portal
- **OpenRouter API Key**: For AI model access
- **Message Content Intent**: Must be enabled in Discord bot settings

## 🚀 Installation

### 1. Clone the Repository
```bash
git clone <repository-url>
cd prism
```

### 2. Install Dependencies

This project uses [uv](https://docs.astral.sh/uv/) for fast, reliable dependency management.

For basic usage:
```bash
uv sync
```

For development (includes pytest, ruff, coverage):
```bash
uv sync --group dev
```

## ⚙️ Configuration

### 1. Create Configuration File
```bash
cp .env.example .env
```

### 2. Configure Required Settings
Edit `.env` and add your credentials:

```bash
# Required Configuration
DISCORD_TOKEN=your_discord_bot_token_here
OPENROUTER_API_KEY=your_openrouter_api_key_here

# AI Model Configuration (Optional - defaults shown)
DEFAULT_MODEL=google/gemini-3-flash-preview:online
FALLBACK_MODEL=google/gemini-2.5-flash:online

# Feature Toggles (Optional - defaults shown)
EMOJI_TALK_ENABLED=true          # Enable emoji suggestions in responses

# Logging (Optional)
LOG_LEVEL=INFO                    # Options: DEBUG, INFO, WARNING, ERROR

# Database (Optional)
PRISM_DB_PATH=data/prism.db      # SQLite database location
```

For all available configuration options, see `.env.example`.

### 🔑 Getting API Keys

#### Discord Bot Token
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application or select an existing one
3. Navigate to the "Bot" section
4. **Important**: Enable "Message Content Intent" under Privileged Gateway Intents
5. Click "Reset Token" to generate a new token
6. Copy the token to your `.env` file

#### OpenRouter API Key
1. Sign up at [OpenRouter](https://openrouter.ai/)
2. Navigate to your API Keys section
3. Generate a new API key
4. Copy the key to your `.env` file

## 🎮 Usage

### Starting the Bot

Using Python module:
```bash
python -m prism
```

Or using the console entry point:
```bash
prism
```

### Interacting with the Bot

The bot responds when mentioned in a channel:
```
@PrismBot Hello! How can you help me today?
```

The bot will reply with context-aware responses using the active persona and relevant emojis.

## 💬 Commands

All commands are slash commands and work guild-wide.

### Persona Management

| Command | Description |
|---------|-------------|
| `/persona info <name>` | Display detailed information about a specific persona |
| `/persona set <name>` | Set the active persona for this server |
| `/persona create <outline> [name]` | Create a new persona using AI assistance |
| `/persona edit <name>` | Edit an existing persona's properties |
| `/persona delete <name>` | Delete a persona from the filesystem |

**Example:**
```
/persona set helpful-assistant
/persona create A friendly coding mentor who explains things clearly
```

### Memory Management

| Command | Description |
|---------|-------------|
| `/memory view [limit]` | View recent conversation history for this channel (default: 10 messages) |
| `/memory clear` | Clear all conversation history for this channel |

**Example:**
```
/memory view 20
/memory clear
```

### User Preferences

| Command | Description |
|---------|-------------|
| `/preferences view` | View your current preference settings |
| `/preferences set <preference> <value>` | Set a preference value |
| `/preferences reset` | Reset all preferences to defaults |

**Available Preferences:**
- `response_length`: `concise`, `balanced`, `detailed`
- `emoji_density`: `none`, `minimal`, `normal`, `lots`
- `preferred_persona`: Any persona name or `none` to clear

**Example:**
```
/preferences view
/preferences set response_length concise
/preferences set emoji_density minimal
/preferences set preferred_persona helpful-assistant
/preferences reset
```

## 🧪 Development

### Running Tests

Run all tests:
```bash
uv run pytest
```

Run tests with verbose output:
```bash
uv run pytest -v
```

Run tests with coverage report:
```bash
uv run pytest --cov=prism --cov-report=html
```

View coverage in browser:
```bash
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Code Quality

Lint the codebase:
```bash
uv run ruff check prism/
```

Auto-fix linting issues:
```bash
uv run ruff check prism/ --fix
```

### Test Coverage

The project maintains comprehensive test coverage:
- Channel lock management
- Database operations
- Emoji enforcement and distribution
- Memory service operations
- OpenRouter API client
- All service layers are tested

## 📁 Project Structure

```
prism/
├── prism/                          # Main package
│   ├── __init__.py                 # Package initialization
│   ├── __main__.py                 # Entry point for python -m prism
│   ├── main.py                     # Bot initialization and message handling
│   ├── config.py                   # Configuration management
│   ├── logging.py                  # Logging setup with file rotation
│   │
│   ├── cogs/                       # Discord command groups (slash commands)
│   │   ├── memory.py               # Memory view/clear commands
│   │   ├── personas.py             # Persona management commands
│   │   └── preferences.py          # User preferences commands
│   │
│   ├── services/                   # Core business logic
│   │   ├── db.py                   # SQLite database wrapper
│   │   ├── memory.py               # Conversation memory service
│   │   ├── personas.py             # Persona CRUD operations
│   │   ├── settings.py             # Guild settings management
│   │   ├── user_preferences.py     # User-level preference management
│   │   ├── emoji_index.py          # Emoji indexing and suggestions
│   │   ├── emoji_enforcer.py       # Emoji distribution logic
│   │   ├── channel_locks.py        # Per-channel lock management
│   │   ├── openrouter_client.py    # OpenRouter API client
│   │   └── git_sync.py             # Git sync for persona changes
│   │
│   └── storage/                    # Data persistence
│       ├── schema.sql              # Database schema
│       └── migrations.py           # Database migration system
│
├── personas/                       # Persona definitions (TOML files)
│   ├── _base_guidelines.toml       # Shared guidelines for all personas
│   ├── default.toml
│   └── ...                         # Additional persona files
│
├── tests/                          # Test suite
│   ├── conftest.py                 # Pytest fixtures
│   ├── test_channel_locks.py
│   ├── test_config.py
│   ├── test_database.py
│   ├── test_emoji_enforcer.py
│   ├── test_emoji_index.py
│   ├── test_length_deprecation.py
│   ├── test_logging.py
│   ├── test_memory_service.py
│   ├── test_message_truncation.py
│   ├── test_openrouter_client.py
│   ├── test_personas.py
│   ├── test_preferences_cog.py
│   ├── test_settings.py
│   ├── test_shutdown.py
│   └── test_user_preferences.py
│
├── .env.example                    # Example configuration
├── Dockerfile                      # Container image definition
├── fly.toml                        # Fly.io deployment configuration
├── pyproject.toml                  # Package metadata and dependencies
├── pytest.ini                      # Pytest configuration
└── README.md                       # This file
```

### Architecture Highlights

- **Modular Design**: Services are cleanly separated for testing and maintainability
- **Async/Await**: Built on asyncio for concurrent operations
- **SQLite Database**: Lightweight persistence with automatic schema migrations
- **TOML Personas**: File-based persona definitions for easy customization
- **Rate Limiting**: Built-in rate limiting to prevent API abuse
- **Memory Management**: Automatic cleanup of old messages (30-day retention)

## 🚢 Deployment

### Fly.io

The project includes configuration for deploying to [Fly.io](https://fly.io/):

1. **Install Fly CLI**:
```bash
curl -L https://fly.io/install.sh | sh
```

2. **Login and launch**:
```bash
fly auth login
fly launch
```

3. **Set secrets**:
```bash
fly secrets set DISCORD_TOKEN=your_token_here
fly secrets set OPENROUTER_API_KEY=your_key_here
```

4. **Deploy**:
```bash
fly deploy
```

The deployment uses:
- A persistent volume mounted at `/data` for the SQLite database
- Shared CPU (1x) with 512MB memory
- Primary region: `iad` (US East)

### Docker

Build and run locally with Docker:

```bash
docker build -t prism-bot .
docker run -d \
  -e DISCORD_TOKEN=your_token \
  -e OPENROUTER_API_KEY=your_key \
  -v prism_data:/data \
  prism-bot
```

## 🔧 Advanced Configuration

### Guild-Specific Command Sync

For faster command registration during development, you can limit command sync to specific guilds:

```bash
COMMAND_GUILD_IDS=123456789,987654321
```

### Performance Tuning

- **Channel Lock Cleanup**: Automatically cleans up locks for inactive channels (default: 1 hour threshold)
- **Message Pruning**: Runs daily to remove messages older than 30 days

### Logging

Logs are written with automatic rotation. The log directory is auto-detected in this order:
1. `PRISM_LOG_DIR` environment variable (if set)
2. `./logs` (if writable)
3. `$XDG_STATE_HOME/prism/logs`
4. `~/.local/state/prism/logs`

Log files:
- `prism.log`: General logs (INFO, DEBUG, WARNING)
- `errors.log`: Errors and critical issues only
- `discord-YYYY-MM-DD.log`: Discord library logs
- `console-YYYY-MM-DD.log`: Console output capture

Log retention defaults:
- General logs: 14 days
- Error logs: 90 days
- Discord logs: 14 days
- Console logs: 14 days

Configure logging:
```bash
LOG_LEVEL=DEBUG              # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL
DISCORD_LOG_LEVEL=INFO       # Discord.py library log level
PRISM_LOG_DIR=/path/to/logs  # Custom log directory
```

## 🤝 Contributing

Contributions are welcome! Here's how you can help:

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Make your changes** and ensure tests pass: `uv run pytest`
4. **Lint your code**: `uv run ruff check prism/`
5. **Commit your changes**: `git commit -m 'Add amazing feature'`
6. **Push to the branch**: `git push origin feature/amazing-feature`
7. **Open a Pull Request**

### Development Guidelines

- Write tests for new features
- Follow existing code style (enforced by ruff)
- Update documentation as needed
- Keep commits focused and descriptive

## 📝 License

MIT

## 🙏 Acknowledgments

- Built with [Pycord](https://pycord.dev/) for Discord integration
- Powered by [OpenRouter](https://openrouter.ai/) for AI model access
- Uses [emoji](https://pypi.org/project/emoji/) library for Unicode emoji support

## 📞 Support

If you encounter issues or have questions:
- Check existing issues on GitHub
- Review the `.env.example` for configuration examples
- Ensure Message Content Intent is enabled in Discord settings
- Verify your OpenRouter API key has sufficient credits

