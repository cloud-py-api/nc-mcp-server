"""Tests for global state management."""

import pytest

import nextcloud_mcp.state as state_module
from nextcloud_mcp.state import get_client, get_config


class TestStateNotInitialized:
    def test_get_client_before_init_raises(self) -> None:
        original = state_module._client
        state_module._client = None
        try:
            with pytest.raises(RuntimeError, match="Server not initialized"):
                get_client()
        finally:
            state_module._client = original

    def test_get_config_before_init_raises(self) -> None:
        original = state_module._config
        state_module._config = None
        try:
            with pytest.raises(RuntimeError, match="Server not initialized"):
                get_config()
        finally:
            state_module._config = original
