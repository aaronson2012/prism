"""Tests for persona service."""
import os
import tempfile
from typing import AsyncGenerator

import pytest

from prism.services.db import Database
from prism.services.personas import PersonaModel, PersonaRecord, PersonasService


@pytest.fixture
async def temp_personas_dir() -> AsyncGenerator[str, None]:
    """Create a temporary directory for personas."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
async def personas_service(db_with_schema, temp_personas_dir) -> PersonasService:
    """Create a PersonasService instance for testing."""
    return PersonasService(db=db_with_schema, defaults_dir=temp_personas_dir)


class TestPersonaModel:
    """Tests for PersonaModel."""

    def test_persona_model_required_fields(self):
        """Test PersonaModel with required fields only."""
        model = PersonaModel(name="test", system_prompt="Test prompt")
        assert model.name == "test"
        assert model.system_prompt == "Test prompt"
        assert model.display_name is None
        assert model.description == ""
        assert model.style is None
        assert model.model is None
        assert model.temperature is None

    def test_persona_model_all_fields(self):
        """Test PersonaModel with all fields."""
        model = PersonaModel(
            name="test",
            display_name="Test Persona",
            description="A test persona",
            system_prompt="Test prompt",
            style="casual",
            model="custom/model",
            temperature=0.7,
        )
        assert model.name == "test"
        assert model.display_name == "Test Persona"
        assert model.description == "A test persona"
        assert model.system_prompt == "Test prompt"
        assert model.style == "casual"
        assert model.model == "custom/model"
        assert model.temperature == 0.7

    def test_persona_model_to_dict(self):
        """Test PersonaModel.to_dict() method."""
        model = PersonaModel(
            name="test",
            display_name="Test",
            description="desc",
            system_prompt="prompt",
        )
        data = model.to_dict()
        assert data["name"] == "test"
        assert data["display_name"] == "Test"
        assert data["description"] == "desc"
        assert data["system_prompt"] == "prompt"


class TestPersonaRecord:
    """Tests for PersonaRecord dataclass."""

    def test_persona_record_builtin(self):
        """Test PersonaRecord for builtin persona."""
        model = PersonaModel(name="default", system_prompt="Default prompt")
        record = PersonaRecord(
            name="default",
            source="builtin",
            data=model,
            path="/path/to/default.toml",
        )
        assert record.name == "default"
        assert record.source == "builtin"
        assert record.data == model
        assert record.path == "/path/to/default.toml"

    def test_persona_record_path_optional(self):
        """Test PersonaRecord with no path."""
        model = PersonaModel(name="test", system_prompt="Test")
        record = PersonaRecord(name="test", source="user", data=model)
        assert record.path is None


class TestPersonasServiceSlug:
    """Tests for PersonasService._slug() static method."""

    def test_slug_basic(self):
        """Test basic slug generation."""
        assert PersonasService._slug("Hello World") == "hello-world"

    def test_slug_special_chars(self):
        """Test slug removes special characters."""
        assert PersonasService._slug("Hello, World!") == "hello-world"

    def test_slug_multiple_spaces(self):
        """Test slug collapses multiple spaces/dashes."""
        assert PersonasService._slug("Hello   World") == "hello-world"

    def test_slug_underscores(self):
        """Test slug preserves underscores."""
        assert PersonasService._slug("hello_world") == "hello_world"

    def test_slug_numbers(self):
        """Test slug preserves numbers."""
        assert PersonasService._slug("persona123") == "persona123"

    def test_slug_mixed(self):
        """Test slug with mixed input."""
        assert PersonasService._slug("My--Cool___Persona!!") == "my-cool___persona"

    def test_slug_leading_trailing_dashes(self):
        """Test slug strips leading/trailing dashes."""
        assert PersonasService._slug("---test---") == "test"

    def test_slug_empty(self):
        """Test slug fallback for empty input."""
        assert PersonasService._slug("") == "persona"
        assert PersonasService._slug("   ") == "persona"

    def test_slug_only_special_chars(self):
        """Test slug fallback for only special characters."""
        assert PersonasService._slug("!!!") == "persona"


class TestPersonasServiceTitleFromSlug:
    """Tests for PersonasService._title_from_slug() static method."""

    def test_title_basic(self):
        """Test basic title conversion."""
        assert PersonasService._title_from_slug("hello-world") == "Hello World"

    def test_title_underscores(self):
        """Test title with underscores."""
        assert PersonasService._title_from_slug("hello_world") == "Hello World"

    def test_title_mixed(self):
        """Test title with mixed separators."""
        assert PersonasService._title_from_slug("hello-world_test") == "Hello World Test"

    def test_title_empty(self):
        """Test title for empty input."""
        assert PersonasService._title_from_slug("") == ""


class TestPersonasServicePathValidation:
    """Tests for PersonasService._validate_path_safe() method."""

    def test_validate_path_safe_valid(self, personas_service, temp_personas_dir):
        """Test valid path passes validation."""
        path = os.path.join(temp_personas_dir, "test.toml")
        # Should not raise
        personas_service._validate_path_safe(path)

    def test_validate_path_safe_traversal(self, personas_service, temp_personas_dir):
        """Test path traversal is rejected."""
        path = os.path.join(temp_personas_dir, "..", "secret.toml")
        with pytest.raises(ValueError, match="traversal|Invalid"):
            personas_service._validate_path_safe(path)

    def test_validate_path_safe_dotfile(self, personas_service, temp_personas_dir):
        """Test dotfile is rejected."""
        path = os.path.join(temp_personas_dir, ".secret.toml")
        with pytest.raises(ValueError, match="Invalid filename"):
            personas_service._validate_path_safe(path)


class TestPersonasServiceCRUD:
    """Tests for PersonasService CRUD operations."""

    @pytest.mark.asyncio
    async def test_list_empty(self, personas_service):
        """Test list returns empty when no personas exist."""
        await personas_service.load_builtins()
        result = await personas_service.list()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, personas_service):
        """Test get returns None for nonexistent persona."""
        await personas_service.load_builtins()
        result = await personas_service.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_create_and_get(self, personas_service):
        """Test creating and retrieving a persona."""
        model = PersonaModel(
            name="test-persona",
            display_name="Test Persona",
            description="A test persona",
            system_prompt="You are a test persona.",
        )
        await personas_service.create(model)

        result = await personas_service.get("test-persona")
        assert result is not None
        assert result.name == "test-persona"
        assert result.data.display_name == "Test Persona"
        assert result.data.system_prompt == "You are a test persona."

    @pytest.mark.asyncio
    async def test_create_duplicate_raises(self, personas_service):
        """Test creating duplicate persona raises error."""
        model = PersonaModel(name="test", system_prompt="Test")
        await personas_service.create(model)

        with pytest.raises(ValueError, match="already exists"):
            await personas_service.create(model)

    @pytest.mark.asyncio
    async def test_create_normalizes_name(self, personas_service):
        """Test that create normalizes persona name to slug."""
        model = PersonaModel(
            name="Test Persona Name",
            system_prompt="Test",
        )
        await personas_service.create(model)

        result = await personas_service.get("test-persona-name")
        assert result is not None
        assert result.name == "test-persona-name"

    @pytest.mark.asyncio
    async def test_list_returns_sorted(self, personas_service):
        """Test list returns personas sorted by name."""
        await personas_service.create(PersonaModel(name="zebra", system_prompt="Z"))
        await personas_service.create(PersonaModel(name="alpha", system_prompt="A"))
        await personas_service.create(PersonaModel(name="middle", system_prompt="M"))

        result = await personas_service.list()
        names = [r.name for r in result]
        assert names == ["alpha", "middle", "zebra"]

    @pytest.mark.asyncio
    async def test_update_persona(self, personas_service):
        """Test updating an existing persona."""
        model = PersonaModel(
            name="test",
            description="Original",
            system_prompt="Original prompt",
        )
        await personas_service.create(model)

        await personas_service.update("test", {"description": "Updated"})

        result = await personas_service.get("test")
        assert result is not None
        assert result.data.description == "Updated"
        # Original values preserved
        assert result.data.system_prompt == "Original prompt"

    @pytest.mark.asyncio
    async def test_update_nonexistent_raises(self, personas_service):
        """Test updating nonexistent persona raises error."""
        with pytest.raises(ValueError, match="not found"):
            await personas_service.update("nonexistent", {"description": "New"})

    @pytest.mark.asyncio
    async def test_update_preserves_name(self, personas_service):
        """Test that update preserves the original name."""
        model = PersonaModel(name="original", system_prompt="Test")
        await personas_service.create(model)

        # Try to change name via update
        await personas_service.update("original", {"name": "changed"})

        # Name should still be original
        result = await personas_service.get("original")
        assert result is not None
        assert result.data.name == "original"

    @pytest.mark.asyncio
    async def test_delete_persona(self, personas_service):
        """Test deleting a persona."""
        model = PersonaModel(name="to-delete", system_prompt="Test")
        await personas_service.create(model)

        # Verify it exists
        result = await personas_service.get("to-delete")
        assert result is not None

        # Delete it
        await personas_service.delete("to-delete")

        # Verify it's gone
        result = await personas_service.get("to-delete")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_raises(self, personas_service):
        """Test deleting nonexistent persona raises error."""
        with pytest.raises(ValueError, match="not found"):
            await personas_service.delete("nonexistent")

    @pytest.mark.asyncio
    async def test_get_case_insensitive(self, personas_service):
        """Test that get is case-insensitive."""
        model = PersonaModel(name="TestPersona", system_prompt="Test")
        await personas_service.create(model)

        # Should find with different cases
        assert await personas_service.get("testpersona") is not None
        assert await personas_service.get("TESTPERSONA") is not None
        assert await personas_service.get("TestPersona") is not None


class TestPersonasServiceTOML:
    """Tests for TOML file handling."""

    @pytest.mark.asyncio
    async def test_load_builtins_missing_dir(self, db_with_schema):
        """Test load_builtins handles missing directory gracefully."""
        service = PersonasService(db=db_with_schema, defaults_dir="/nonexistent/path")
        await service.load_builtins()
        result = await service.list()
        assert result == []

    @pytest.mark.asyncio
    async def test_persona_roundtrip_special_chars(self, personas_service):
        """Test persona with special characters in system prompt."""
        model = PersonaModel(
            name="special",
            description="Has \"quotes\" and \\backslashes\\",
            system_prompt='Test with "quotes", \\backslashes\\, and\nnewlines',
        )
        await personas_service.create(model)

        result = await personas_service.get("special")
        assert result is not None
        assert '"quotes"' in result.data.system_prompt
        assert "\\backslashes\\" in result.data.system_prompt
        assert "\n" in result.data.system_prompt

    @pytest.mark.asyncio
    async def test_persona_with_model_and_temperature(self, personas_service):
        """Test persona creation with model and temperature fields.

        Note: The TOML loader currently doesn't load model/temperature back,
        but the fields are written to the file. This tests that creation works.
        """
        model = PersonaModel(
            name="custom",
            system_prompt="Custom prompt",
            model="custom/model",
            temperature=0.8,
        )
        await personas_service.create(model)

        result = await personas_service.get("custom")
        assert result is not None
        # The persona is created successfully
        assert result.data.system_prompt == "Custom prompt"
        # Note: model/temperature aren't loaded back from TOML by load_builtins
        # This is a limitation of the current implementation


class TestPersonasServiceEnsureUniqueName:
    """Tests for _ensure_unique_name helper."""

    @pytest.mark.asyncio
    async def test_ensure_unique_name_available(self, personas_service):
        """Test unique name returns as-is when available."""
        name = await personas_service._ensure_unique_name("available")
        assert name == "available"

    @pytest.mark.asyncio
    async def test_ensure_unique_name_collision(self, personas_service):
        """Test unique name adds suffix on collision."""
        # Create existing persona
        await personas_service.create(PersonaModel(name="taken", system_prompt="Test"))

        name = await personas_service._ensure_unique_name("taken")
        assert name == "taken-2"

    @pytest.mark.asyncio
    async def test_ensure_unique_name_multiple_collisions(self, personas_service):
        """Test unique name increments suffix for multiple collisions."""
        await personas_service.create(PersonaModel(name="taken", system_prompt="Test"))
        await personas_service.create(PersonaModel(name="taken-2", system_prompt="Test"))
        await personas_service.create(PersonaModel(name="taken-3", system_prompt="Test"))

        name = await personas_service._ensure_unique_name("taken")
        assert name == "taken-4"
