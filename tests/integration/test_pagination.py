"""Pagination integration tests — verify limit/offset behavior with bulk data.

Requires seed data created by scripts/seed_pagination_data.py (run in CI).
For local development, the test fixtures create data on demand.
"""

import contextlib
import json
import uuid
from collections.abc import AsyncGenerator

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from tests.integration.conftest import McpTestHelper

pytestmark = pytest.mark.integration

PAGINATION_DIR = "mcp-pagination-data"
PREFIX = "mcp-pagtest"
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


async def _ensure_pagination_conversations(nc_mcp: McpTestHelper) -> None:
    """Create Talk conversations if they don't already exist."""
    result = json.loads(await nc_mcp.call("list_conversations", limit=200))
    existing = {c["name"] for c in result["data"]}
    for i in range(1, ITEM_COUNT + 1):
        name = f"{PREFIX}-conv-{i:03d}"
        if name not in existing:
            await nc_mcp.call("create_conversation", room_type=2, name=name)


async def _ensure_pagination_events(nc_mcp: McpTestHelper) -> None:
    """Create calendar events if they don't already exist."""
    result = json.loads(
        await nc_mcp.call(
            "get_events",
            calendar_id="personal",
            start="2027-06-01T00:00:00Z",
            end="2027-06-30T23:59:59Z",
            limit=200,
        )
    )
    existing_uids = {e["uid"] for e in result["data"]}
    for i in range(1, ITEM_COUNT + 1):
        uid = f"{PREFIX}-event-{i:03d}"
        if uid not in existing_uids:
            hour = i % 24
            await nc_mcp.call(
                "create_event",
                calendar_id="personal",
                summary=f"Pagination Test Event {i:03d}",
                start=f"2027-06-01T{hour:02d}:00:00Z",
                end=f"2027-06-01T{hour:02d}:30:00Z",
            )


async def _ensure_pagination_trash(nc_mcp: McpTestHelper) -> None:
    """Populate trash with items if not enough exist."""
    result = json.loads(await nc_mcp.call("list_trash", limit=200))
    existing = result["pagination"]["count"]
    if existing >= ITEM_COUNT:
        return
    need = ITEM_COUNT - existing
    tag = uuid.uuid4().hex[:6]
    for i in range(need):
        path = f"{PREFIX}-trash-{tag}-{i:03d}.txt"
        await nc_mcp.client.dav_put(path, b"trash item", content_type="text/plain")
        await nc_mcp.client.dav_delete(path)


async def _ensure_pagination_collective_pages(nc_mcp: McpTestHelper) -> int:
    """Create a collective with many pages. Returns collective_id."""
    coll_name = f"{PREFIX}-collective"
    result = json.loads(await nc_mcp.call("list_collectives", limit=200))
    coll = next((c for c in result["data"] if c["name"] == coll_name), None)
    if not coll:
        coll = json.loads(await nc_mcp.call("create_collective", name=coll_name))
    coll_id = coll["id"]

    pages_result = json.loads(await nc_mcp.call("get_collective_pages", collective_id=coll_id, limit=200))
    pages = pages_result["data"]
    if len(pages) > ITEM_COUNT:
        return coll_id

    landing_id = pages[0]["id"]
    existing_titles = {p["title"] for p in pages}
    for i in range(1, ITEM_COUNT + 1):
        title = f"pagtest-page-{i:03d}"
        if title not in existing_titles:
            await nc_mcp.call("create_collective_page", collective_id=coll_id, parent_id=landing_id, title=title)
    return coll_id


async def _ensure_pagination_comments(nc_mcp: McpTestHelper) -> int:
    """Create a file with many comments. Returns file_id."""
    await _ensure_pagination_files(nc_mcp)
    comment_file = f"{PAGINATION_DIR}/comment-target.txt"
    with contextlib.suppress(Exception):
        await nc_mcp.client.dav_put(comment_file, b"File with many comments", content_type="text/plain")

    result = json.loads(await nc_mcp.call("list_directory", path=PAGINATION_DIR, limit=200))
    file_id = None
    for entry in result["data"]:
        if "comment-target" in entry["path"]:
            file_id = int(entry["file_id"])
            break
    if file_id is None:
        pytest.skip("Could not find comment-target.txt file ID")

    comments = json.loads(await nc_mcp.call("list_comments", file_id=file_id, limit=100))
    existing = comments["pagination"]["count"]
    for i in range(existing + 1, ITEM_COUNT + 1):
        await nc_mcp.call("add_comment", file_id=file_id, message=f"Pagination test comment {i:03d}")
    return file_id


async def _ensure_pagination_shares(nc_mcp: McpTestHelper) -> None:
    """Create link shares for pagination test files."""
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
        result = json.loads(await nc_mcp.call("list_directory", path=PAGINATION_DIR, limit=500))
        self.total = result["pagination"]["count"]

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
        assert result["pagination"]["count"] == self.total - DEFAULT_LIMIT
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
        result = json.loads(await nc_mcp.call("list_directory", path=PAGINATION_DIR, offset=10000))
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
        assert len(all_paths) == self.total
        assert len(set(all_paths)) == self.total

    @pytest.mark.asyncio
    async def test_limit_one(self, nc_mcp: McpTestHelper) -> None:
        result = json.loads(await nc_mcp.call("list_directory", path=PAGINATION_DIR, limit=1))
        assert result["pagination"]["count"] == 1
        assert result["pagination"]["has_more"] is True
        assert len(result["data"]) == 1


class TestListConversationsPagination:
    @pytest.fixture(autouse=True)
    async def _setup(self, nc_mcp: McpTestHelper) -> None:
        await _ensure_pagination_conversations(nc_mcp)
        result = json.loads(await nc_mcp.call("list_conversations", limit=200))
        self.total = result["pagination"]["count"]

    @pytest.mark.asyncio
    async def test_default_limit_caps_results(self, nc_mcp: McpTestHelper) -> None:
        result = json.loads(await nc_mcp.call("list_conversations"))
        assert result["pagination"]["count"] == DEFAULT_LIMIT
        assert result["pagination"]["has_more"] is True

    @pytest.mark.asyncio
    async def test_offset_returns_remaining(self, nc_mcp: McpTestHelper) -> None:
        result = json.loads(await nc_mcp.call("list_conversations", offset=DEFAULT_LIMIT))
        assert result["pagination"]["count"] == self.total - DEFAULT_LIMIT
        assert result["pagination"]["has_more"] is False

    @pytest.mark.asyncio
    async def test_custom_limit(self, nc_mcp: McpTestHelper) -> None:
        result = json.loads(await nc_mcp.call("list_conversations", limit=10))
        assert result["pagination"]["count"] == 10
        assert result["pagination"]["has_more"] is True

    @pytest.mark.asyncio
    async def test_full_traversal_no_duplicates(self, nc_mcp: McpTestHelper) -> None:
        all_tokens: list[str] = []
        offset = 0
        while True:
            result = json.loads(await nc_mcp.call("list_conversations", limit=20, offset=offset))
            all_tokens.extend(c["token"] for c in result["data"])
            if not result["pagination"]["has_more"]:
                break
            offset += 20
        assert len(all_tokens) == self.total
        assert len(set(all_tokens)) == self.total


class TestGetEventsPagination:
    RANGE_START = "2027-06-01T00:00:00Z"
    RANGE_END = "2027-06-30T23:59:59Z"

    @pytest.fixture(autouse=True)
    async def _setup(self, nc_mcp: McpTestHelper) -> None:
        await _ensure_pagination_events(nc_mcp)
        result = json.loads(
            await nc_mcp.call(
                "get_events",
                calendar_id="personal",
                start=self.RANGE_START,
                end=self.RANGE_END,
                limit=200,
            )
        )
        self.total = result["pagination"]["count"]

    @pytest.mark.asyncio
    async def test_default_limit_caps_results(self, nc_mcp: McpTestHelper) -> None:
        result = json.loads(
            await nc_mcp.call("get_events", calendar_id="personal", start=self.RANGE_START, end=self.RANGE_END)
        )
        assert result["pagination"]["count"] == DEFAULT_LIMIT
        assert result["pagination"]["has_more"] is True

    @pytest.mark.asyncio
    async def test_offset_returns_remaining(self, nc_mcp: McpTestHelper) -> None:
        result = json.loads(
            await nc_mcp.call(
                "get_events",
                calendar_id="personal",
                start=self.RANGE_START,
                end=self.RANGE_END,
                offset=DEFAULT_LIMIT,
            )
        )
        assert result["pagination"]["count"] == self.total - DEFAULT_LIMIT
        assert result["pagination"]["has_more"] is False

    @pytest.mark.asyncio
    async def test_full_traversal_no_duplicates(self, nc_mcp: McpTestHelper) -> None:
        all_uids: list[str] = []
        offset = 0
        while True:
            result = json.loads(
                await nc_mcp.call(
                    "get_events",
                    calendar_id="personal",
                    start=self.RANGE_START,
                    end=self.RANGE_END,
                    limit=20,
                    offset=offset,
                )
            )
            all_uids.extend(e["uid"] for e in result["data"])
            if not result["pagination"]["has_more"]:
                break
            offset += 20
        assert len(all_uids) == self.total
        assert len(set(all_uids)) == self.total


class TestListSharesPagination:
    @pytest.fixture(autouse=True)
    async def _setup(self, nc_mcp: McpTestHelper) -> AsyncGenerator[None]:
        await _ensure_pagination_files(nc_mcp)
        await _ensure_pagination_shares(nc_mcp)
        result = json.loads(await nc_mcp.call("list_shares", path=f"/{PAGINATION_DIR}", subfiles=True, limit=200))
        self.total = result["pagination"]["count"]
        yield
        await _cleanup_pagination_shares(nc_mcp)

    @pytest.mark.asyncio
    async def test_default_limit_caps_results(self, nc_mcp: McpTestHelper) -> None:
        result = json.loads(await nc_mcp.call("list_shares", path=f"/{PAGINATION_DIR}", subfiles=True))
        assert result["pagination"]["count"] == DEFAULT_LIMIT
        assert result["pagination"]["has_more"] is True

    @pytest.mark.asyncio
    async def test_offset_returns_remaining(self, nc_mcp: McpTestHelper) -> None:
        result = json.loads(
            await nc_mcp.call("list_shares", path=f"/{PAGINATION_DIR}", subfiles=True, offset=DEFAULT_LIMIT)
        )
        assert result["pagination"]["count"] == self.total - DEFAULT_LIMIT
        assert result["pagination"]["has_more"] is False

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
        assert len(all_ids) == self.total
        assert len(set(all_ids)) == self.total


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


class TestListTrashPagination:
    # Trash accumulates across seed runs and other tests, so we can't
    # predict the exact total. Tests verify pagination mechanics without
    # relying on a specific count.

    @pytest.fixture(autouse=True)
    async def _setup(self, nc_mcp: McpTestHelper) -> None:
        await _ensure_pagination_trash(nc_mcp)

    @pytest.mark.asyncio
    async def test_default_limit_caps_results(self, nc_mcp: McpTestHelper) -> None:
        result = json.loads(await nc_mcp.call("list_trash"))
        assert result["pagination"]["count"] == DEFAULT_LIMIT
        assert result["pagination"]["has_more"] is True

    @pytest.mark.asyncio
    async def test_offset_returns_next_page(self, nc_mcp: McpTestHelper) -> None:
        result = json.loads(await nc_mcp.call("list_trash", offset=DEFAULT_LIMIT))
        assert result["pagination"]["count"] > 0
        assert result["pagination"]["offset"] == DEFAULT_LIMIT

    @pytest.mark.asyncio
    async def test_full_traversal_no_duplicates(self, nc_mcp: McpTestHelper) -> None:
        all_paths: list[str] = []
        offset = 0
        while True:
            result = json.loads(await nc_mcp.call("list_trash", limit=20, offset=offset))
            all_paths.extend(item["trash_path"] for item in result["data"])
            if not result["pagination"]["has_more"]:
                break
            offset += 20
        assert len(all_paths) >= ITEM_COUNT
        assert len(set(all_paths)) == len(all_paths)


class TestGetCollectivePagesPagination:
    @pytest.fixture(autouse=True)
    async def _setup(self, nc_mcp: McpTestHelper) -> None:
        self.coll_id = await _ensure_pagination_collective_pages(nc_mcp)
        result = json.loads(await nc_mcp.call("get_collective_pages", collective_id=self.coll_id, limit=200))
        self.total = result["pagination"]["count"]

    @pytest.mark.asyncio
    async def test_default_limit_caps_results(self, nc_mcp: McpTestHelper) -> None:
        result = json.loads(await nc_mcp.call("get_collective_pages", collective_id=self.coll_id))
        assert result["pagination"]["count"] == DEFAULT_LIMIT
        assert result["pagination"]["has_more"] is True

    @pytest.mark.asyncio
    async def test_offset_returns_remaining(self, nc_mcp: McpTestHelper) -> None:
        result = json.loads(await nc_mcp.call("get_collective_pages", collective_id=self.coll_id, offset=DEFAULT_LIMIT))
        assert result["pagination"]["count"] == self.total - DEFAULT_LIMIT
        assert result["pagination"]["has_more"] is False

    @pytest.mark.asyncio
    async def test_full_traversal_no_duplicates(self, nc_mcp: McpTestHelper) -> None:
        all_ids: list[int] = []
        offset = 0
        while True:
            result = json.loads(
                await nc_mcp.call("get_collective_pages", collective_id=self.coll_id, limit=20, offset=offset)
            )
            all_ids.extend(p["id"] for p in result["data"])
            if not result["pagination"]["has_more"]:
                break
            offset += 20
        assert len(all_ids) == self.total
        assert len(set(all_ids)) == self.total


class TestListCommentsPagination:
    @pytest.fixture(autouse=True)
    async def _setup(self, nc_mcp: McpTestHelper) -> None:
        self.file_id = await _ensure_pagination_comments(nc_mcp)
        result = json.loads(await nc_mcp.call("list_comments", file_id=self.file_id, limit=100))
        self.total = result["pagination"]["count"]

    @pytest.mark.asyncio
    async def test_default_limit_caps_results(self, nc_mcp: McpTestHelper) -> None:
        result = json.loads(await nc_mcp.call("list_comments", file_id=self.file_id))
        assert result["pagination"]["count"] == 20  # default limit for comments is 20
        assert result["pagination"]["has_more"] is True

    @pytest.mark.asyncio
    async def test_offset_returns_next_page(self, nc_mcp: McpTestHelper) -> None:
        result = json.loads(await nc_mcp.call("list_comments", file_id=self.file_id, offset=20))
        assert result["pagination"]["count"] == 20
        assert result["pagination"]["offset"] == 20

    @pytest.mark.asyncio
    async def test_full_traversal_no_duplicates(self, nc_mcp: McpTestHelper) -> None:
        all_ids: list[int] = []
        offset = 0
        while True:
            result = json.loads(await nc_mcp.call("list_comments", file_id=self.file_id, limit=15, offset=offset))
            all_ids.extend(c["id"] for c in result["data"])
            if not result["pagination"]["has_more"]:
                break
            offset += 15
        assert len(all_ids) == self.total
        assert len(set(all_ids)) == self.total
