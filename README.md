# Prism Discord Bot

Prism is a Discord AI bot with persona switching, contextual memory, and intelligent emoji integration.

## Features

- **Multiple AI Personas**: Switch between different personality modes
- **Contextual Memory**: Maintains conversation history per channel
- **Emoji Intelligence**: Automatic emoji suggestion and enforcement
- **Emoji Reactions**: AI-driven reactions to messages
- **Custom Persona Creation**: AI-assisted persona generation
- **Guild-Scoped Settings**: Per-server configuration

## Requirements

- Python 3.11+
- Discord Bot Token
- OpenRouter API Key

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd prism
```

2. Install dependencies:
```bash
pip install -e .
```

For development:
```bash
pip install -e ".[dev]"
```

## Configuration

1. Copy the example environment file:
```bash
cp env.example .env
```

2. Edit `.env` and add your credentials:
```bash
# Required
DISCORD_TOKEN=your_discord_bot_token_here
OPENROUTER_API_KEY=your_openrouter_api_key_here

# Optional (with defaults shown)
DEFAULT_MODEL=google/gemini-2.5-flash
FALLBACK_MODEL=google/gemini-2.5-flash-lite
LOG_LEVEL=INFO
EMOJI_TALK_ENABLED=true
EMOJI_REACTIONS_ENABLED=false
```

See `env.example` for all available configuration options.

### Getting API Keys

- **Discord Token**: Create a bot at [Discord Developer Portal](https://discord.com/developers/applications)
  - Enable "Message Content Intent" in Bot settings
  - Copy the token from Bot → Reset Token
- **OpenRouter API Key**: Sign up at [OpenRouter](https://openrouter.ai/) and generate an API key

## Usage

Run the bot:
```bash
python -m prism
```

Or using the console script:
```bash
prism
```

## Commands

### Persona Management
- `/persona info <name>` - Show persona details
- `/persona set <name>` - Set active persona for the guild
- `/persona create <outline>` - Create a new persona (AI-assisted)
- `/persona edit <name>` - Edit an existing persona
- `/persona delete <name>` - Delete a persona

### Memory Management
- `/memory view [limit]` - View recent conversation memory
- `/memory clear` - Clear conversation memory for the channel

## Development

### Running Tests

```bash
pytest
```

With coverage:
```bash
pytest --cov=prism --cov-report=html
```

### Code Quality

Linting with ruff:
```bash
ruff check prism/
```

## Project Structure

```
prism/
├── prism/
│   ├── main.py              # Bot entry point and message handling
│   ├── config.py            # Configuration management
│   ├── logging.py           # Logging setup
│   ├── cogs/                # Discord command groups
│   │   ├── memory.py        # Memory commands
│   │   └── personas.py      # Persona commands
│   ├── services/            # Core services
│   │   ├── db.py            # Database wrapper
│   │   ├── memory.py        # Message memory service
│   │   ├── personas.py      # Persona management
│   │   ├── settings.py      # Guild settings
│   │   ├── emoji_index.py   # Emoji indexing and suggestions
│   │   ├── emoji_enforcer.py # Emoji distribution logic
│   │   ├── reaction_engine.py # AI-driven reactions
│   │   ├── rate_limit.py    # Rate limiting
│   │   └── openrouter_client.py # AI API client
│   └── storage/
│       └── schema.sql       # Database schema
├── personas/                # Persona definitions (TOML)
├── tests/                   # Test suite
└── pyproject.toml          # Project metadata and dependencies
```

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]

