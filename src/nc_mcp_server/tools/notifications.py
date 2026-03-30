"""Notification tools — list and dismiss notifications via OCS API."""

import json

from mcp.server.fastmcp import FastMCP

from ..annotations import DESTRUCTIVE, READONLY
from ..permissions import PermissionLevel, require_permission
from ..state import get_client


def register(mcp: FastMCP) -> None:
    """Register notification tools with the MCP server."""

    @mcp.tool(annotations=READONLY)
    @require_permission(PermissionLevel.READ)
    async def list_notifications(limit: int = 50, offset: int = 0) -> str:
        """List notifications for the current Nextcloud user.

        Returns notifications sorted by newest first.

        Args:
            limit: Maximum number of notifications to return (1-200, default 50).
            offset: Number of notifications to skip for pagination (default 0).

        Returns:
            JSON with "data" (list of notification objects) and "pagination"
            (count, offset, limit, has_more).
        """
        limit = max(1, min(200, limit))
        offset = max(0, offset)
        client = get_client()
        data = await client.ocs_get("apps/notifications/api/v2/notifications")
        page = data[offset : offset + limit]
        has_more = offset + limit < len(data)

        return json.dumps(
            {
                "data": page,
                "pagination": {"count": len(page), "offset": offset, "limit": limit, "has_more": has_more},
            },
            default=str,
        )

    @mcp.tool(annotations=DESTRUCTIVE)
    @require_permission(PermissionLevel.DESTRUCTIVE)
    async def dismiss_notification(notification_id: int) -> str:
        """Dismiss (permanently delete) a single notification by its ID.

        Use list_notifications first to find the notification_id to dismiss.

        Args:
            notification_id: The numeric ID of the notification to dismiss.

        Returns:
            Confirmation message.
        """
        client = get_client()
        await client.ocs_delete(
            f"apps/notifications/api/v2/notifications/{notification_id}",
        )
        return f"Notification {notification_id} dismissed."

    @mcp.tool(annotations=DESTRUCTIVE)
    @require_permission(PermissionLevel.DESTRUCTIVE)
    async def dismiss_all_notifications() -> str:
        """Dismiss (permanently delete) ALL notifications for the current user.

        This cannot be undone. Use list_notifications first to review
        what will be dismissed.

        Returns:
            Confirmation message.
        """
        client = get_client()
        await client.ocs_delete("apps/notifications/api/v2/notifications")
        return "All notifications dismissed."
