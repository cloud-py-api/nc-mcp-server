"""Integration tests for Talk poll tools against a real Nextcloud instance."""

import json
from typing import Any

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from .conftest import McpTestHelper

pytestmark = pytest.mark.integration


async def _create_room(nc_mcp: McpTestHelper, name: str, room_type: int = 2) -> dict[str, Any]:
    """Create a conversation and return the parsed result."""
    result = await nc_mcp.call("create_conversation", room_type=room_type, name=name)
    return json.loads(result)


async def _delete_room(nc_mcp: McpTestHelper, token: str) -> None:
    """Delete a conversation via the client (bypasses MCP permission checks)."""
    await nc_mcp.client.ocs_delete(f"apps/spreed/api/v4/room/{token}")


async def _create_test_poll(
    nc_mcp: McpTestHelper,
    token: str,
    question: str = "Favorite color?",
    options: list[str] | None = None,
    result_mode: int = 0,
    max_votes: int = 0,
) -> dict[str, Any]:
    """Create a poll and return the parsed result."""
    if options is None:
        options = ["Red", "Blue", "Green"]
    result = await nc_mcp.call(
        "create_poll",
        token=token,
        question=question,
        options=options,
        result_mode=result_mode,
        max_votes=max_votes,
    )
    return json.loads(result)


class TestCreatePoll:
    @pytest.mark.asyncio
    async def test_create_basic_poll(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-create-poll")
        try:
            poll = await _create_test_poll(nc_mcp, str(room["token"]))
            assert poll["question"] == "Favorite color?"
            assert poll["options"] == ["Red", "Blue", "Green"]
            assert poll["status"] == "open"
            assert "id" in poll
        finally:
            await _delete_room(nc_mcp, str(room["token"]))

    @pytest.mark.asyncio
    async def test_create_poll_returns_id(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-poll-id")
        try:
            poll = await _create_test_poll(nc_mcp, str(room["token"]))
            assert isinstance(poll["id"], int)
            assert poll["id"] > 0
        finally:
            await _delete_room(nc_mcp, str(room["token"]))

    @pytest.mark.asyncio
    async def test_create_poll_public_result_mode(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-poll-public")
        try:
            poll = await _create_test_poll(nc_mcp, str(room["token"]), result_mode=0)
            assert poll["result_mode"] == "public"
        finally:
            await _delete_room(nc_mcp, str(room["token"]))

    @pytest.mark.asyncio
    async def test_create_poll_hidden_result_mode(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-poll-hidden")
        try:
            poll = await _create_test_poll(nc_mcp, str(room["token"]), result_mode=1)
            assert poll["result_mode"] == "hidden"
        finally:
            await _delete_room(nc_mcp, str(room["token"]))

    @pytest.mark.asyncio
    async def test_create_poll_with_max_votes(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-poll-maxvotes")
        try:
            poll = await _create_test_poll(nc_mcp, str(room["token"]), max_votes=1)
            assert poll["max_votes"] == 1
        finally:
            await _delete_room(nc_mcp, str(room["token"]))

    @pytest.mark.asyncio
    async def test_create_poll_with_two_options(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-poll-2opts")
        try:
            poll = await _create_test_poll(nc_mcp, str(room["token"]), question="Yes or No?", options=["Yes", "No"])
            assert len(poll["options"]) == 2
        finally:
            await _delete_room(nc_mcp, str(room["token"]))

    @pytest.mark.asyncio
    async def test_create_poll_fewer_than_two_options_raises(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-poll-1opt")
        try:
            with pytest.raises((ToolError, ValueError)):
                await nc_mcp.call(
                    "create_poll",
                    token=str(room["token"]),
                    question="Bad poll",
                    options=["Only one"],
                )
        finally:
            await _delete_room(nc_mcp, str(room["token"]))

    @pytest.mark.asyncio
    async def test_create_poll_in_nonexistent_conversation_raises(self, nc_mcp: McpTestHelper) -> None:
        with pytest.raises(ToolError):
            await nc_mcp.call(
                "create_poll",
                token="nonexistent-xyz-12345",
                question="Nope?",
                options=["A", "B"],
            )

    @pytest.mark.asyncio
    async def test_create_poll_initial_state(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-poll-init")
        try:
            poll = await _create_test_poll(nc_mcp, str(room["token"]))
            assert poll["num_voters"] == 0
            assert poll["voted_self"] == []
            assert poll["actor_id"] == "admin"
        finally:
            await _delete_room(nc_mcp, str(room["token"]))


class TestGetPoll:
    @pytest.mark.asyncio
    async def test_get_poll_returns_details(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-get-poll")
        try:
            created = await _create_test_poll(nc_mcp, str(room["token"]))
            result = await nc_mcp.call("get_poll", token=str(room["token"]), poll_id=int(created["id"]))
            poll = json.loads(result)
            assert poll["id"] == created["id"]
            assert poll["question"] == "Favorite color?"
            assert poll["options"] == ["Red", "Blue", "Green"]
        finally:
            await _delete_room(nc_mcp, str(room["token"]))

    @pytest.mark.asyncio
    async def test_get_poll_has_required_fields(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-poll-fields")
        try:
            created = await _create_test_poll(nc_mcp, str(room["token"]))
            result = await nc_mcp.call("get_poll", token=str(room["token"]), poll_id=int(created["id"]))
            poll = json.loads(result)
            required = [
                "id",
                "question",
                "options",
                "status",
                "result_mode",
                "max_votes",
                "actor_id",
                "actor_display_name",
                "num_voters",
                "voted_self",
            ]
            for field in required:
                assert field in poll, f"Missing field: {field}"
        finally:
            await _delete_room(nc_mcp, str(room["token"]))

    @pytest.mark.asyncio
    async def test_get_nonexistent_poll_raises(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-poll-404")
        try:
            with pytest.raises(ToolError):
                await nc_mcp.call("get_poll", token=str(room["token"]), poll_id=999999)
        finally:
            await _delete_room(nc_mcp, str(room["token"]))

    @pytest.mark.asyncio
    async def test_get_poll_in_nonexistent_conversation_raises(self, nc_mcp: McpTestHelper) -> None:
        with pytest.raises(ToolError):
            await nc_mcp.call("get_poll", token="nonexistent-xyz-12345", poll_id=1)

    @pytest.mark.asyncio
    async def test_get_poll_reflects_votes(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-poll-voted")
        try:
            created = await _create_test_poll(nc_mcp, str(room["token"]))
            await nc_mcp.call("vote_poll", token=str(room["token"]), poll_id=int(created["id"]), option_ids=[1])
            result = await nc_mcp.call("get_poll", token=str(room["token"]), poll_id=int(created["id"]))
            poll = json.loads(result)
            assert poll["voted_self"] == [1]
            assert poll["num_voters"] == 1
        finally:
            await _delete_room(nc_mcp, str(room["token"]))


class TestVotePoll:
    @pytest.mark.asyncio
    async def test_vote_single_option(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-vote-single")
        try:
            created = await _create_test_poll(nc_mcp, str(room["token"]))
            result = await nc_mcp.call(
                "vote_poll", token=str(room["token"]), poll_id=int(created["id"]), option_ids=[0]
            )
            poll = json.loads(result)
            assert poll["voted_self"] == [0]
            assert poll["num_voters"] == 1
        finally:
            await _delete_room(nc_mcp, str(room["token"]))

    @pytest.mark.asyncio
    async def test_vote_multiple_options(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-vote-multi")
        try:
            # max_votes=0 means unlimited
            created = await _create_test_poll(nc_mcp, str(room["token"]), max_votes=0)
            result = await nc_mcp.call(
                "vote_poll", token=str(room["token"]), poll_id=int(created["id"]), option_ids=[0, 2]
            )
            poll = json.loads(result)
            assert sorted(poll["voted_self"]) == [0, 2]
        finally:
            await _delete_room(nc_mcp, str(room["token"]))

    @pytest.mark.asyncio
    async def test_vote_replaces_previous_vote(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-vote-replace")
        try:
            created = await _create_test_poll(nc_mcp, str(room["token"]))
            # First vote
            await nc_mcp.call("vote_poll", token=str(room["token"]), poll_id=int(created["id"]), option_ids=[0])
            # Change vote
            result = await nc_mcp.call(
                "vote_poll", token=str(room["token"]), poll_id=int(created["id"]), option_ids=[1]
            )
            poll = json.loads(result)
            assert poll["voted_self"] == [1]
            assert poll["num_voters"] == 1  # Still one voter
        finally:
            await _delete_room(nc_mcp, str(room["token"]))

    @pytest.mark.asyncio
    async def test_vote_shows_public_results(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-vote-public")
        try:
            created = await _create_test_poll(nc_mcp, str(room["token"]), result_mode=0)
            result = await nc_mcp.call(
                "vote_poll", token=str(room["token"]), poll_id=int(created["id"]), option_ids=[0]
            )
            poll = json.loads(result)
            # Public result mode: votes visible after voting
            assert "votes" in poll
            assert poll["votes"]["option-0"] == 1
        finally:
            await _delete_room(nc_mcp, str(room["token"]))

    @pytest.mark.asyncio
    async def test_vote_empty_option_ids_raises(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-vote-empty")
        try:
            created = await _create_test_poll(nc_mcp, str(room["token"]))
            with pytest.raises((ToolError, ValueError)):
                await nc_mcp.call("vote_poll", token=str(room["token"]), poll_id=int(created["id"]), option_ids=[])
        finally:
            await _delete_room(nc_mcp, str(room["token"]))

    @pytest.mark.asyncio
    async def test_vote_on_nonexistent_poll_raises(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-vote-404")
        try:
            with pytest.raises(ToolError):
                await nc_mcp.call("vote_poll", token=str(room["token"]), poll_id=999999, option_ids=[0])
        finally:
            await _delete_room(nc_mcp, str(room["token"]))

    @pytest.mark.asyncio
    async def test_vote_on_closed_poll_raises(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-vote-closed")
        try:
            created = await _create_test_poll(nc_mcp, str(room["token"]))
            await nc_mcp.call("close_poll", token=str(room["token"]), poll_id=int(created["id"]))
            with pytest.raises(ToolError):
                await nc_mcp.call("vote_poll", token=str(room["token"]), poll_id=int(created["id"]), option_ids=[0])
        finally:
            await _delete_room(nc_mcp, str(room["token"]))


class TestClosePoll:
    @pytest.mark.asyncio
    async def test_close_poll(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-close-poll")
        try:
            created = await _create_test_poll(nc_mcp, str(room["token"]))
            result = await nc_mcp.call("close_poll", token=str(room["token"]), poll_id=int(created["id"]))
            poll = json.loads(result)
            assert poll["status"] == "closed"
        finally:
            await _delete_room(nc_mcp, str(room["token"]))

    @pytest.mark.asyncio
    async def test_close_poll_reveals_results(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-close-reveal")
        try:
            created = await _create_test_poll(nc_mcp, str(room["token"]), result_mode=1)
            # Vote first
            await nc_mcp.call("vote_poll", token=str(room["token"]), poll_id=int(created["id"]), option_ids=[0])
            # Close — should reveal results even though result_mode was hidden
            result = await nc_mcp.call("close_poll", token=str(room["token"]), poll_id=int(created["id"]))
            poll = json.loads(result)
            assert poll["status"] == "closed"
            assert "votes" in poll
            assert poll["num_voters"] == 1
        finally:
            await _delete_room(nc_mcp, str(room["token"]))

    @pytest.mark.asyncio
    async def test_close_already_closed_poll_raises(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-close-twice")
        try:
            created = await _create_test_poll(nc_mcp, str(room["token"]))
            await nc_mcp.call("close_poll", token=str(room["token"]), poll_id=int(created["id"]))
            with pytest.raises(ToolError):
                await nc_mcp.call("close_poll", token=str(room["token"]), poll_id=int(created["id"]))
        finally:
            await _delete_room(nc_mcp, str(room["token"]))

    @pytest.mark.asyncio
    async def test_close_nonexistent_poll_raises(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-close-404")
        try:
            with pytest.raises(ToolError):
                await nc_mcp.call("close_poll", token=str(room["token"]), poll_id=999999)
        finally:
            await _delete_room(nc_mcp, str(room["token"]))

    @pytest.mark.asyncio
    async def test_close_poll_preserves_question_and_options(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-close-data")
        try:
            created = await _create_test_poll(
                nc_mcp,
                str(room["token"]),
                question="Preserved?",
                options=["A", "B", "C"],
            )
            result = await nc_mcp.call("close_poll", token=str(room["token"]), poll_id=int(created["id"]))
            poll = json.loads(result)
            assert poll["question"] == "Preserved?"
            assert poll["options"] == ["A", "B", "C"]
        finally:
            await _delete_room(nc_mcp, str(room["token"]))

    @pytest.mark.asyncio
    async def test_close_public_poll_includes_voter_details(self, nc_mcp: McpTestHelper) -> None:
        room = await _create_room(nc_mcp, "test-close-details")
        try:
            created = await _create_test_poll(nc_mcp, str(room["token"]), result_mode=0)
            await nc_mcp.call("vote_poll", token=str(room["token"]), poll_id=int(created["id"]), option_ids=[0])
            result = await nc_mcp.call("close_poll", token=str(room["token"]), poll_id=int(created["id"]))
            poll = json.loads(result)
            assert "details" in poll
            assert isinstance(poll["details"], list)
            assert len(poll["details"]) >= 1
            assert poll["details"][0]["actorId"] == "admin"
        finally:
            await _delete_room(nc_mcp, str(room["token"]))


class TestPollPermissions:
    @pytest.mark.asyncio
    async def test_read_only_allows_get_poll(self, nc_mcp_read_only: McpTestHelper) -> None:
        # Create room and poll via client directly (bypasses MCP permission checks)
        client = nc_mcp_read_only.client
        room = await client.ocs_post("apps/spreed/api/v4/room", data={"roomType": 2, "roomName": "test-perm-read-poll"})
        token = str(room["token"])
        try:
            poll_data = await client.ocs_post(
                f"apps/spreed/api/v1/poll/{token}",
                data={"question": "Read test?", "options[]": ["A", "B"], "resultMode": 0, "maxVotes": 0},
            )
            result = await nc_mcp_read_only.call("get_poll", token=token, poll_id=int(poll_data["id"]))
            poll = json.loads(result)
            assert poll["id"] == poll_data["id"]
        finally:
            await client.ocs_delete(f"apps/spreed/api/v4/room/{token}")

    @pytest.mark.asyncio
    async def test_read_only_blocks_create_poll(self, nc_mcp_read_only: McpTestHelper) -> None:
        with pytest.raises(ToolError, match=r"requires 'write' permission"):
            await nc_mcp_read_only.call(
                "create_poll",
                token="x",
                question="Blocked?",
                options=["A", "B"],
            )

    @pytest.mark.asyncio
    async def test_read_only_blocks_vote_poll(self, nc_mcp_read_only: McpTestHelper) -> None:
        with pytest.raises(ToolError, match=r"requires 'write' permission"):
            await nc_mcp_read_only.call("vote_poll", token="x", poll_id=1, option_ids=[0])

    @pytest.mark.asyncio
    async def test_read_only_blocks_close_poll(self, nc_mcp_read_only: McpTestHelper) -> None:
        with pytest.raises(ToolError, match=r"requires 'destructive' permission"):
            await nc_mcp_read_only.call("close_poll", token="x", poll_id=1)

    @pytest.mark.asyncio
    async def test_write_allows_create_and_vote_but_blocks_close(self, nc_mcp_write: McpTestHelper) -> None:
        # Create room via client directly to avoid fixture ordering issues
        client = nc_mcp_write.client
        room = await client.ocs_post(
            "apps/spreed/api/v4/room", data={"roomType": 2, "roomName": "test-perm-write-poll"}
        )
        token = str(room["token"])
        try:
            # WRITE allows create_poll
            created = await _create_test_poll(nc_mcp_write, token)
            # WRITE allows vote_poll
            result = await nc_mcp_write.call("vote_poll", token=token, poll_id=int(created["id"]), option_ids=[0])
            poll = json.loads(result)
            assert poll["voted_self"] == [0]
            # WRITE blocks close_poll
            with pytest.raises(ToolError, match=r"requires 'destructive' permission"):
                await nc_mcp_write.call("close_poll", token=token, poll_id=int(created["id"]))
        finally:
            await client.ocs_delete(f"apps/spreed/api/v4/room/{token}")
