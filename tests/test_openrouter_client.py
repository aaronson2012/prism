"""Tests for OpenRouter client."""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from prism.services.openrouter_client import (
    OpenRouterClient,
    OpenRouterConfig,
    OpenRouterError,
)


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    return OpenRouterConfig(
        api_key="test-key",
        default_model="test/model",
        fallback_model="test/fallback",
        timeout_seconds=10.0,
    )


@pytest.fixture
def client(mock_config):
    """Create a client instance."""
    return OpenRouterClient(mock_config)


@pytest.mark.asyncio
async def test_client_initialization(mock_config):
    """Test client initializes with correct config."""
    client = OpenRouterClient(mock_config)
    
    assert client.cfg.api_key == "test-key"
    assert client.cfg.default_model == "test/model"
    assert client._client is not None
    
    await client.aclose()


@pytest.mark.asyncio
async def test_chat_completion_success(client):
    """Test successful chat completion."""
    # Mock the HTTP response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"x-request-id": "test-123"}
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Hello! How can I help you?"
                }
            }
        ],
        "model": "test/model",
        "usage": {"prompt_tokens": 10, "completion_tokens": 7}
    }
    
    with patch.object(client._client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        messages = [{"role": "user", "content": "Hello"}]
        text, meta = await client.chat_completion(messages)
        
        assert text == "Hello! How can I help you?"
        assert meta["request_id"] == "test-123"
        assert meta["model"] == "test/model"
        assert meta["usage"]["prompt_tokens"] == 10


@pytest.mark.asyncio
async def test_chat_completion_fallback_on_error(client):
    """Test fallback model is used when primary fails."""
    # Mock first call to fail, second to succeed
    mock_error_response = MagicMock()
    mock_error_response.status_code = 500
    mock_error_response.json.return_value = {"error": {"message": "Server error"}}
    
    mock_success_response = MagicMock()
    mock_success_response.status_code = 200
    mock_success_response.headers = {"x-request-id": "fallback-123"}
    mock_success_response.json.return_value = {
        "choices": [{"message": {"content": "Fallback response"}}],
        "model": "test/fallback"
    }
    
    with patch.object(client._client, 'post', new_callable=AsyncMock) as mock_post:
        # First call fails, second succeeds
        mock_post.side_effect = [mock_error_response, mock_success_response]
        
        messages = [{"role": "user", "content": "Test"}]
        text, meta = await client.chat_completion(messages, model="test/model")
        
        assert text == "Fallback response"
        assert meta["model"] == "test/fallback"
        assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_chat_completion_raises_when_both_fail(client):
    """Test error is raised when both primary and fallback fail."""
    mock_error_response = MagicMock()
    mock_error_response.status_code = 500
    mock_error_response.json.return_value = {"error": {"message": "Server error"}}
    
    with patch.object(client._client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_error_response
        
        messages = [{"role": "user", "content": "Test"}]
        
        with pytest.raises(OpenRouterError) as exc_info:
            await client.chat_completion(messages)
        
        assert "both primary" in str(exc_info.value).lower()
        assert mock_post.call_count == 2  # Tried primary + fallback


@pytest.mark.asyncio
async def test_chat_completion_with_parameters(client):
    """Test that temperature and max_tokens are passed correctly."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {}
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Test"}}],
    }
    
    with patch.object(client._client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        messages = [{"role": "user", "content": "Test"}]
        await client.chat_completion(
            messages,
            model="custom/model",
            temperature=0.7,
            max_tokens=100
        )
        
        # Check the payload sent
        call_args = mock_post.call_args
        payload = json.loads(call_args[1]['content'])
        
        assert payload["model"] == "custom/model"
        assert payload["temperature"] == 0.7
        assert payload["max_tokens"] == 100


@pytest.mark.asyncio
async def test_client_cleanup(client):
    """Test that client cleanup works."""
    await client.aclose()
    # If this doesn't raise an exception, cleanup worked
    assert True


@pytest.mark.asyncio
async def test_chat_completion_extracts_sources(client):
    """Test that sources are extracted from API response."""
    # Mock response with sources in message object
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"x-request-id": "test-123"}
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Here's information from the web.",
                    "sources": [
                        {"url": "https://example.com/article1", "title": "Example Article 1"},
                        {"url": "https://example.com/article2", "title": "Example Article 2"},
                    ]
                }
            }
        ],
        "model": "test/model:online",
        "usage": {"prompt_tokens": 10, "completion_tokens": 7}
    }
    
    with patch.object(client._client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        messages = [{"role": "user", "content": "What's the latest news?"}]
        text, meta = await client.chat_completion(messages)
        
        assert text == "Here's information from the web."
        assert "sources" in meta
        assert len(meta["sources"]) == 2
        assert meta["sources"][0]["url"] == "https://example.com/article1"
        assert meta["sources"][0]["title"] == "Example Article 1"


@pytest.mark.asyncio
async def test_chat_completion_no_sources(client):
    """Test that sources field is empty list when not present."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"x-request-id": "test-123"}
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Regular response without web search."
                }
            }
        ],
        "model": "test/model",
    }
    
    with patch.object(client._client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        messages = [{"role": "user", "content": "Hello"}]
        text, meta = await client.chat_completion(messages)
        
        assert text == "Regular response without web search."
        assert "sources" in meta
        assert meta["sources"] == []


@pytest.mark.asyncio
async def test_chat_completion_sources_in_root(client):
    """Test extracting sources from root level of response."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"x-request-id": "test-123"}
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Response with sources at root level."
                }
            }
        ],
        "model": "test/model:online",
        "sources": [
            {"url": "https://example.com/article", "title": "Article Title"}
        ]
    }
    
    with patch.object(client._client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        messages = [{"role": "user", "content": "Test"}]
        text, meta = await client.chat_completion(messages)
        
        assert "sources" in meta
        assert len(meta["sources"]) == 1
        assert meta["sources"][0]["title"] == "Article Title"


