"""Pagination integration tests — verify limit/offset behavior with bulk data."""

import contextlib
import json
from collections.abc import AsyncGenerator

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from tests.integration.conftest import McpTestHelper

pytestmark = pytest.mark.integration

PAGINATION_DIR = "mcp-pagination-data"
ITEM_COUNT = 55
DEFAULT_LIMIT = 50


async def _ensure_pagination_files(nc_mcp: McpTestHelper) -> None:
    """Create pagination test files if they don't already exist (CI seeds them)."""
    try:
        result = json.loads(await nc_mcp.call("list_directory", path=PAGINATION_DIR, limit=200))
        if result["pagination"]["count"] >= ITEM_COUNT:
            return
    except (ToolError, KeyError):
        pass
    with contextlib.suppress(Exception):
        await nc_mcp.client.dav_mkcol(PAGINATION_DIR)
    for i in range(1, ITEM_COUNT + 1):
        await nc_mcp.client.dav_put(
            f"{PAGINATION_DIR}/pagtest-{i:03d}.txt",
            f"Pagination test file {i:03d}".encode(),
            content_type="text/plain",
        )


async def _ensure_pagination_shares(nc_mcp: McpTestHelper) -> None:
    """Create link shares for pagination test files if they don't exist."""
    result = json.loads(await nc_mcp.call("list_shares", path=f"/{PAGINATION_DIR}", subfiles=True, limit=200))
    if result["pagination"]["count"] >= ITEM_COUNT:
        return
    existing = result["pagination"]["count"]
    for i in range(existing + 1, ITEM_COUNT + 1):
        await nc_mcp.call(
            "create_share",
            path=f"/{PAGINATION_DIR}/pagtest-{i:03d}.txt",
            share_type=3,
        )


async def _cleanup_pagination_shares(nc_mcp: McpTestHelper) -> None:
    """Remove all shares on pagination test files."""
    result = json.loads(await nc_mcp.call("list_shares", path=f"/{PAGINATION_DIR}", subfiles=True, limit=200))
    for share in result["data"]:
        with contextlib.suppress(ToolError):
            await nc_mcp.call("delete_share", share_id=int(share["id"]))


class TestListDirectoryPagination:
    @pytest.fixture(autouse=True)
    async def _setup(self, nc_mcp: McpTestHelper) -> None:
        await _ensure_pagination_files(nc_mcp)

    @pytest.mark.asyncio
    async def test_default_limit_caps_results(self, nc_mcp: McpTestHelper) -> None:
        result = json.loads(await nc_mcp.call("list_directory", path=PAGINATION_DIR))
        assert result["pagination"]["count"] == DEFAULT_LIMIT
        assert result["pagination"]["limit"] == DEFAULT_LIMIT
        assert result["pagination"]["offset"] == 0
        assert result["pagination"]["has_more"] is True
        assert len(result["data"]) == DEFAULT_LIMIT

    @pytest.mark.asyncio
    async def test_offset_returns_remaining(self, nc_mcp: McpTestHelper) -> None:
        result = json.loads(await nc_mcp.call("list_directory", path=PAGINATION_DIR, offset=DEFAULT_LIMIT))
        remaining = ITEM_COUNT - DEFAULT_LIMIT
        assert result["pagination"]["count"] == remaining
        assert result["pagination"]["offset"] == DEFAULT_LIMIT
        assert result["pagination"]["has_more"] is False

    @pytest.mark.asyncio
    async def test_custom_limit(self, nc_mcp: McpTestHelper) -> None:
        result = json.loads(await nc_mcp.call("list_directory", path=PAGINATION_DIR, limit=10))
        assert result["pagination"]["count"] == 10
        assert result["pagination"]["limit"] == 10
        assert result["pagination"]["has_more"] is True

    @pytest.mark.asyncio
    async def test_offset_beyond_total_returns_empty(self, nc_mcp: McpTestHelper) -> None:
        result = json.loads(await nc_mcp.call("list_directory", path=PAGINATION_DIR, offset=1000))
        assert result["data"] == []
        assert result["pagination"]["count"] == 0
        assert result["pagination"]["has_more"] is False

    @pytest.mark.asyncio
    async def test_full_traversal_no_duplicates(self, nc_mcp: McpTestHelper) -> None:
        all_paths: list[str] = []
        offset = 0
        while True:
            result = json.loads(await nc_mcp.call("list_directory", path=PAGINATION_DIR, limit=20, offset=offset))
            all_paths.extend(e["path"] for e in result["data"])
            if not result["pagination"]["has_more"]:
                break
            offset += 20
        assert len(all_paths) == ITEM_COUNT
        assert len(set(all_paths)) == ITEM_COUNT

    @pytest.mark.asyncio
    async def test_limit_one(self, nc_mcp: McpTestHelper) -> None:
        result = json.loads(await nc_mcp.call("list_directory", path=PAGINATION_DIR, limit=1))
        assert result["pagination"]["count"] == 1
        assert result["pagination"]["has_more"] is True
        assert len(result["data"]) == 1


class TestListNotificationsPagination:
    # Nextcloud caps notification API responses at 25 items server-side,
    # so we test client pagination within that constraint.
    NC_NOTIF_LIMIT = 25

    @pytest.mark.asyncio
    async def test_limit_and_offset(self, nc_mcp: McpTestHelper) -> None:
        for i in range(self.NC_NOTIF_LIMIT):
            await nc_mcp.generate_notification(subject=f"pagtest-{i:03d}")

        result = json.loads(await nc_mcp.call("list_notifications", limit=10))
        assert result["pagination"]["count"] == 10
        assert result["pagination"]["limit"] == 10
        assert result["pagination"]["has_more"] is True

        result2 = json.loads(await nc_mcp.call("list_notifications", limit=10, offset=20))
        assert result2["pagination"]["count"] == self.NC_NOTIF_LIMIT - 20
        assert result2["pagination"]["has_more"] is False

    @pytest.mark.asyncio
    async def test_full_traversal(self, nc_mcp: McpTestHelper) -> None:
        for i in range(self.NC_NOTIF_LIMIT):
            await nc_mcp.generate_notification(subject=f"pagtest-trav-{i:03d}")

        all_subjects: list[str] = []
        offset = 0
        while True:
            result = json.loads(await nc_mcp.call("list_notifications", limit=10, offset=offset))
            all_subjects.extend(n["subject"] for n in result["data"])
            if not result["pagination"]["has_more"]:
                break
            offset += 10
        assert len(all_subjects) == self.NC_NOTIF_LIMIT
        assert len(set(all_subjects)) == self.NC_NOTIF_LIMIT

    @pytest.mark.asyncio
    async def test_formatted_fields(self, nc_mcp: McpTestHelper) -> None:
        """Verify _format_notification strips noisy fields."""
        await nc_mcp.generate_notification(subject="format-check", message="body-check")
        result = json.loads(await nc_mcp.call("list_notifications"))
        notif = result["data"][0]
        assert "notification_id" in notif
        assert "subject" in notif
        assert "message" in notif
        assert "subjectRich" not in notif
        assert "messageRich" not in notif
        assert "icon" not in notif
        assert "shouldNotify" not in notif


class TestListSharesPagination:
    @pytest.fixture(autouse=True)
    async def _setup(self, nc_mcp: McpTestHelper) -> AsyncGenerator[None]:
        await _ensure_pagination_files(nc_mcp)
        await _ensure_pagination_shares(nc_mcp)
        yield
        await _cleanup_pagination_shares(nc_mcp)

    @pytest.mark.asyncio
    async def test_default_limit_and_offset(self, nc_mcp: McpTestHelper) -> None:
        result = json.loads(await nc_mcp.call("list_shares", path=f"/{PAGINATION_DIR}", subfiles=True))
        assert result["pagination"]["count"] == DEFAULT_LIMIT
        assert result["pagination"]["has_more"] is True

        result2 = json.loads(
            await nc_mcp.call("list_shares", path=f"/{PAGINATION_DIR}", subfiles=True, offset=DEFAULT_LIMIT)
        )
        assert result2["pagination"]["count"] == ITEM_COUNT - DEFAULT_LIMIT
        assert result2["pagination"]["has_more"] is False

    @pytest.mark.asyncio
    async def test_full_traversal_no_duplicates(self, nc_mcp: McpTestHelper) -> None:
        all_ids: list[object] = []
        offset = 0
        while True:
            result = json.loads(
                await nc_mcp.call("list_shares", path=f"/{PAGINATION_DIR}", subfiles=True, limit=20, offset=offset)
            )
            all_ids.extend(s["id"] for s in result["data"])
            if not result["pagination"]["has_more"]:
                break
            offset += 20
        assert len(all_ids) >= ITEM_COUNT
        assert len(set(all_ids)) == len(all_ids)
