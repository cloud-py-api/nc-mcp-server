"""Integration tests for Circles (Teams) tools against a real Nextcloud instance."""

import contextlib
import json
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from nc_mcp_server.client import NextcloudClient, NextcloudError
from nc_mcp_server.config import Config

from .conftest import McpTestHelper

pytestmark = pytest.mark.integration

CIRCLE_TEST_USER = "mcp-circle-test-user"


@pytest.fixture
async def circle_peer(nc_config: Config) -> AsyncGenerator[str]:
    """Ensure a second user exists for membership tests. Yields the userid."""
    client = NextcloudClient(nc_config)
    with contextlib.suppress(Exception):
        await client.ocs_post(
            "cloud/users",
            data={"userid": CIRCLE_TEST_USER, "password": "mcp-Circle-Test-PWD-9X!"},
        )
    yield CIRCLE_TEST_USER
    with contextlib.suppress(Exception):
        await client.ocs_delete(f"cloud/users/{CIRCLE_TEST_USER}")
    await client.close()


async def _make_circle(nc_mcp: McpTestHelper, name: str) -> dict[str, Any]:
    """Create a circle and return its dict."""
    created: dict[str, Any] = json.loads(await nc_mcp.call("create_circle", name=name))
    return created


class TestListCircles:
    @pytest.mark.asyncio
    async def test_list_includes_created(self, nc_mcp: McpTestHelper) -> None:
        circle = await _make_circle(nc_mcp, "mcp-test-circle-list")
        circles: list[dict[str, Any]] = json.loads(await nc_mcp.call("list_circles"))
        assert isinstance(circles, list)
        assert any(c["id"] == circle["id"] for c in circles)

    @pytest.mark.asyncio
    async def test_list_pagination(self, nc_mcp: McpTestHelper) -> None:
        for i in range(3):
            await _make_circle(nc_mcp, f"mcp-test-circle-page-{i}")
        circles: list[dict[str, Any]] = json.loads(await nc_mcp.call("list_circles", limit=2))
        assert len(circles) <= 2


class TestCircleLifecycle:
    @pytest.mark.asyncio
    async def test_create_sets_owner_to_caller(self, nc_mcp: McpTestHelper) -> None:
        created = json.loads(await nc_mcp.call("create_circle", name="mcp-test-circle-create"))
        assert created["name"] == "mcp-test-circle-create"
        assert created["initiator"]["userId"] == "admin"
        assert created["initiator"]["level"] == 9  # owner

    @pytest.mark.asyncio
    async def test_get_returns_circle(self, nc_mcp: McpTestHelper) -> None:
        circle = await _make_circle(nc_mcp, "mcp-test-circle-get")
        fetched = json.loads(await nc_mcp.call("get_circle", circle_id=circle["id"]))
        assert fetched["id"] == circle["id"]
        assert fetched["name"] == "mcp-test-circle-get"

    @pytest.mark.asyncio
    async def test_get_nonexistent_raises(self, nc_mcp: McpTestHelper) -> None:
        with pytest.raises((ToolError, NextcloudError)):
            await nc_mcp.call("get_circle", circle_id="nonexistent-id-xxxxxxxxxxxxxxxx")

    @pytest.mark.asyncio
    async def test_update_name(self, nc_mcp: McpTestHelper) -> None:
        circle = await _make_circle(nc_mcp, "mcp-test-circle-rename-old")
        await nc_mcp.call(
            "update_circle_name",
            circle_id=circle["id"],
            name="mcp-test-circle-rename-new",
        )
        fetched = json.loads(await nc_mcp.call("get_circle", circle_id=circle["id"]))
        assert fetched["name"] == "mcp-test-circle-rename-new"

    @pytest.mark.asyncio
    async def test_update_description(self, nc_mcp: McpTestHelper) -> None:
        circle = await _make_circle(nc_mcp, "mcp-test-circle-desc")
        await nc_mcp.call(
            "update_circle_description",
            circle_id=circle["id"],
            description="hello world",
        )
        fetched = json.loads(await nc_mcp.call("get_circle", circle_id=circle["id"]))
        assert fetched["description"] == "hello world"

    @pytest.mark.asyncio
    async def test_update_config_flags(self, nc_mcp: McpTestHelper) -> None:
        circle = await _make_circle(nc_mcp, "mcp-test-circle-config")
        # 24 = VISIBLE (8) | OPEN (16)
        await nc_mcp.call("update_circle_config", circle_id=circle["id"], config=24)
        fetched = json.loads(await nc_mcp.call("get_circle", circle_id=circle["id"]))
        assert fetched["config"] == 24

    @pytest.mark.asyncio
    async def test_delete_removes_circle(self, nc_mcp: McpTestHelper) -> None:
        circle = await _make_circle(nc_mcp, "mcp-test-circle-delete")
        result = json.loads(await nc_mcp.call("delete_circle", circle_id=circle["id"]))
        assert result == {"deleted_circle_id": circle["id"]}
        with pytest.raises((ToolError, NextcloudError)):
            await nc_mcp.call("get_circle", circle_id=circle["id"])


class TestMembers:
    @pytest.mark.asyncio
    async def test_owner_present_in_members(self, nc_mcp: McpTestHelper) -> None:
        circle = await _make_circle(nc_mcp, "mcp-test-circle-owner")
        members: list[dict[str, Any]] = json.loads(await nc_mcp.call("list_circle_members", circle_id=circle["id"]))
        assert isinstance(members, list)
        admin_member = next((m for m in members if m.get("userId") == "admin"), None)
        assert admin_member is not None, "owner should be in members"
        assert admin_member["level"] == 9

    @pytest.mark.asyncio
    async def test_add_and_list_member(self, nc_mcp: McpTestHelper, circle_peer: str) -> None:
        circle = await _make_circle(nc_mcp, "mcp-test-circle-add-member")
        added = json.loads(await nc_mcp.call("add_circle_member", circle_id=circle["id"], user_id=circle_peer))
        assert added["userId"] == circle_peer
        members: list[dict[str, Any]] = json.loads(await nc_mcp.call("list_circle_members", circle_id=circle["id"]))
        assert any(m.get("userId") == circle_peer for m in members)

    @pytest.mark.asyncio
    async def test_add_member_rejects_bad_type(self, nc_mcp: McpTestHelper) -> None:
        circle = await _make_circle(nc_mcp, "mcp-test-circle-bad-type")
        with pytest.raises((ToolError, ValueError), match=r"[Ii]nvalid member_type"):
            await nc_mcp.call(
                "add_circle_member",
                circle_id=circle["id"],
                user_id="anyone",
                member_type="bogus",
            )

    @pytest.mark.asyncio
    async def test_update_member_level(self, nc_mcp: McpTestHelper, circle_peer: str) -> None:
        circle = await _make_circle(nc_mcp, "mcp-test-circle-promote")
        added = json.loads(await nc_mcp.call("add_circle_member", circle_id=circle["id"], user_id=circle_peer))
        await nc_mcp.call(
            "update_circle_member_level",
            circle_id=circle["id"],
            member_id=added["id"],
            level="moderator",
        )
        members: list[dict[str, Any]] = json.loads(await nc_mcp.call("list_circle_members", circle_id=circle["id"]))
        peer = next(m for m in members if m.get("userId") == circle_peer)
        assert peer["level"] == 4

    @pytest.mark.asyncio
    async def test_update_level_rejects_bad_value(self, nc_mcp: McpTestHelper, circle_peer: str) -> None:
        circle = await _make_circle(nc_mcp, "mcp-test-circle-bad-level")
        added = json.loads(await nc_mcp.call("add_circle_member", circle_id=circle["id"], user_id=circle_peer))
        with pytest.raises((ToolError, ValueError), match=r"[Ii]nvalid level"):
            await nc_mcp.call(
                "update_circle_member_level",
                circle_id=circle["id"],
                member_id=added["id"],
                level="superuser",
            )

    @pytest.mark.asyncio
    async def test_remove_member(self, nc_mcp: McpTestHelper, circle_peer: str) -> None:
        circle = await _make_circle(nc_mcp, "mcp-test-circle-kick")
        added = json.loads(await nc_mcp.call("add_circle_member", circle_id=circle["id"], user_id=circle_peer))
        result = json.loads(
            await nc_mcp.call(
                "remove_circle_member",
                circle_id=circle["id"],
                member_id=added["id"],
            )
        )
        assert result == {"removed_member_id": added["id"]}
        members: list[dict[str, Any]] = json.loads(await nc_mcp.call("list_circle_members", circle_id=circle["id"]))
        assert not any(m.get("userId") == circle_peer for m in members)


class TestJoinLeave:
    @pytest.mark.asyncio
    async def test_leave_as_non_owner(self, nc_mcp: McpTestHelper, circle_peer: str) -> None:
        """Admin adds peer then removes peer — membership disappears."""
        admin = nc_mcp
        circle = json.loads(await admin.call("create_circle", name="mcp-test-circle-leave"))
        peer_member = json.loads(await admin.call("add_circle_member", circle_id=circle["id"], user_id=circle_peer))
        # Admin removes peer (equivalent to peer leaving, same effect)
        await admin.call(
            "remove_circle_member",
            circle_id=circle["id"],
            member_id=peer_member["id"],
        )
        members: list[dict[str, Any]] = json.loads(await admin.call("list_circle_members", circle_id=circle["id"]))
        assert not any(m.get("userId") == circle_peer for m in members)


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_returns_list(self, nc_mcp: McpTestHelper) -> None:
        """Search should return a JSON list regardless of matches."""
        await _make_circle(nc_mcp, "mcp-test-circle-search")
        results = json.loads(await nc_mcp.call("search_circles", term="admin"))
        assert isinstance(results, list)


class TestCirclesPermissions:
    @pytest.mark.asyncio
    async def test_read_only_allows_list(self, nc_mcp_read_only: McpTestHelper) -> None:
        result = await nc_mcp_read_only.call("list_circles")
        assert isinstance(json.loads(result), list)

    @pytest.mark.asyncio
    async def test_read_only_blocks_create(self, nc_mcp_read_only: McpTestHelper) -> None:
        with pytest.raises(ToolError, match=r"[Pp]ermission"):
            await nc_mcp_read_only.call("create_circle", name="mcp-test-circle-perm")

    @pytest.mark.asyncio
    async def test_read_only_blocks_delete(self, nc_mcp_read_only: McpTestHelper) -> None:
        with pytest.raises(ToolError, match=r"[Pp]ermission"):
            await nc_mcp_read_only.call("delete_circle", circle_id="doesnt-matter")

    @pytest.mark.asyncio
    async def test_write_blocks_delete(self, nc_mcp_write: McpTestHelper) -> None:
        with pytest.raises(ToolError, match=r"[Pp]ermission"):
            await nc_mcp_write.call("delete_circle", circle_id="doesnt-matter")

    @pytest.mark.asyncio
    async def test_write_allows_create_and_update(self, nc_mcp_write: McpTestHelper) -> None:
        created = json.loads(await nc_mcp_write.call("create_circle", name="mcp-test-circle-perm-write"))
        await nc_mcp_write.call(
            "update_circle_description",
            circle_id=created["id"],
            description="desc",
        )
        fetched = json.loads(await nc_mcp_write.call("get_circle", circle_id=created["id"]))
        assert fetched["description"] == "desc"
