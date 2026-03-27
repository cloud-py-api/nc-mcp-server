"""Integration tests for error handling against a real Nextcloud instance.

Verifies that errors from Nextcloud are translated into helpful messages
rather than raw HTTP status codes or stack traces.
"""

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from nextcloud_mcp.client import NextcloudClient, NextcloudError

from .conftest import TEST_BASE_DIR, McpTestHelper

pytestmark = pytest.mark.integration


class TestNextcloudErrorMessages:
    """Verify that NextcloudError is raised with contextual, helpful messages."""

    @pytest.mark.asyncio
    async def test_file_not_found(self, nc_client: NextcloudClient) -> None:
        with pytest.raises(NextcloudError, match=r"Not found") as exc_info:
            await nc_client.dav_get("this-file-will-never-exist-12345.txt")
        assert exc_info.value.status_code == 404
        assert "Get file" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_directory_not_found(self, nc_client: NextcloudClient) -> None:
        with pytest.raises(NextcloudError, match=r"Not found") as exc_info:
            await nc_client.dav_propfind("nonexistent-dir-12345/", depth=1)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_not_found(self, nc_client: NextcloudClient) -> None:
        with pytest.raises(NextcloudError, match=r"Not found") as exc_info:
            await nc_client.dav_delete("nonexistent-file-12345.txt")
        assert exc_info.value.status_code == 404
        assert "Delete" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_move_source_not_found(self, nc_client: NextcloudClient) -> None:
        with pytest.raises(NextcloudError, match=r"Not found") as exc_info:
            await nc_client.dav_move("nonexistent-12345.txt", "dest.txt")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_create_dir_conflict(self, nc_client: NextcloudClient) -> None:
        await nc_client.dav_mkcol(TEST_BASE_DIR)
        with pytest.raises(NextcloudError) as exc_info:
            await nc_client.dav_mkcol(TEST_BASE_DIR)
        # Already exists should be 405 Method Not Allowed
        assert exc_info.value.status_code in (405, 409)

    @pytest.mark.asyncio
    async def test_error_has_status_code_attribute(self, nc_client: NextcloudClient) -> None:
        with pytest.raises(NextcloudError) as exc_info:
            await nc_client.dav_get("nonexistent-12345.txt")
        assert isinstance(exc_info.value.status_code, int)
        assert exc_info.value.status_code > 0


class TestOcsErrorMessages:
    """Verify that OCS error messages from Nextcloud are extracted, not discarded."""

    @pytest.mark.asyncio
    async def test_get_nonexistent_user_includes_ocs_message(self, nc_client: NextcloudClient) -> None:
        with pytest.raises(NextcloudError, match="User does not exist") as exc_info:
            await nc_client.ocs_get("cloud/users/nonexistent-user-xyz-12345")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_nonexistent_share_includes_ocs_message(self, nc_client: NextcloudClient) -> None:
        with pytest.raises(NextcloudError, match="Wrong share ID, share does not exist") as exc_info:
            await nc_client.ocs_get("apps/files_sharing/api/v1/shares/999999")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_share_nonexistent_path_includes_ocs_message(self, nc_client: NextcloudClient) -> None:
        with pytest.raises(NextcloudError, match="Wrong path") as exc_info:
            await nc_client.ocs_post(
                "apps/files_sharing/api/v1/shares",
                data={"path": "/nonexistent-xyz-12345.txt", "shareType": 3},
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_create_duplicate_user_includes_ocs_message(self, nc_client: NextcloudClient) -> None:
        with pytest.raises(NextcloudError, match="already exists") as exc_info:
            await nc_client.ocs_post("cloud/users", data={"userid": "admin", "password": "test"})
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_ocs_error_preserves_context_prefix(self, nc_client: NextcloudClient) -> None:
        with pytest.raises(NextcloudError) as exc_info:
            await nc_client.ocs_get("cloud/users/nonexistent-user-xyz-12345")
        msg = str(exc_info.value)
        assert "OCS GET" in msg
        assert "User does not exist" in msg


class TestErrorsThroughMcpTools:
    """Verify that errors propagate correctly through the MCP tool layer."""

    @pytest.mark.asyncio
    async def test_get_file_not_found_via_tool(self, nc_mcp: McpTestHelper) -> None:
        with pytest.raises(ToolError, match=r"Not found"):
            await nc_mcp.call("get_file", path="nonexistent-12345.txt")

    @pytest.mark.asyncio
    async def test_list_directory_not_found_via_tool(self, nc_mcp: McpTestHelper) -> None:
        with pytest.raises(ToolError, match=r"Not found"):
            await nc_mcp.call("list_directory", path="nonexistent-dir-12345/")

    @pytest.mark.asyncio
    async def test_delete_not_found_via_tool(self, nc_mcp: McpTestHelper) -> None:
        with pytest.raises(ToolError, match=r"Not found"):
            await nc_mcp.call("delete_file", path="nonexistent-12345.txt")

    @pytest.mark.asyncio
    async def test_get_nonexistent_user_ocs_message_via_tool(self, nc_mcp: McpTestHelper) -> None:
        with pytest.raises(ToolError, match="User does not exist"):
            await nc_mcp.call("get_user", user_id="nonexistent-user-xyz-12345")

    @pytest.mark.asyncio
    async def test_get_nonexistent_share_ocs_message_via_tool(self, nc_mcp: McpTestHelper) -> None:
        with pytest.raises(ToolError, match="Wrong share ID"):
            await nc_mcp.call("get_share", share_id=999999)
