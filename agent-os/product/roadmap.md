# Product Roadmap

## Current State (Stable)

The following features are implemented and working:

- [x] Multiple AI personas with distinct personalities
- [x] Persona switching via slash commands
- [x] AI-assisted custom persona creation
- [x] Persona editing and deletion
- [x] Per-channel contextual memory with 30-day retention
- [x] Memory view and clear commands
- [x] Smart emoji suggestions based on context
- [x] Automatic emoji enforcement in responses
- [x] Guild-scoped configuration
- [x] OpenRouter AI integration with fallback model support
- [x] Fly.io deployment

---

## Planned Features

1. [x] **User Preferences Storage** - Store per-user preferences in the database (preferred persona, response style, etc.) that persist across sessions `S`

2. [x] **User Preference Commands** - Slash commands for users to view and update their personal preferences (`/preferences view`, `/preferences set`) `S`

3. [x] **Per-User Response Customization** - Apply stored user preferences when generating responses (e.g., verbosity level, formality, emoji density) `M`

4. [ ] **Model Configuration Schema** - Define a configuration schema for multiple AI models with their capabilities, costs, and use cases `S`

5. [ ] **Model Selection Logic** - Implement logic to select appropriate models based on task type, user preference, or admin configuration `M`

6. [ ] **Model Switching Commands** - Add commands to view available models and switch between them (`/model list`, `/model set`) `S`

7. [ ] **Web Dashboard Backend** - Create a simple web API (Flask/FastAPI) that exposes bot configuration and status endpoints `L`

8. [ ] **Dashboard Authentication** - Implement Discord OAuth2 authentication to secure the dashboard and identify users `M`

9. [ ] **Dashboard Frontend** - Build a web interface for viewing bot status, managing personas, and configuring settings `L`

10. [ ] **Dashboard Persona Management** - Add persona CRUD operations to the dashboard with a visual editor `M`

> Notes
> - Items 1-3 complete the user preferences system
> - Items 4-6 enable multi-model support
> - Items 7-10 deliver the web dashboard
> - Each item represents a complete, testable feature
> - Order reflects technical dependencies (storage before commands, backend before frontend)
