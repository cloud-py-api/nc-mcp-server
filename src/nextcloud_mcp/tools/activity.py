"""Activity tools — recent activity feed via OCS API."""

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..permissions import PermissionLevel, require_permission
from ..state import get_client

_VALID_FILTERS = {
    "all",
    "self",
    "by",
    "files",
    "files_sharing",
    "files_favorites",
    "calendar",
    "calendar_todo",
    "comments",
    "contacts",
    "deck",
    "forms",
    "security",
    "tables",
    "circles",
}

_VALID_SORT = {"asc", "desc"}


def _format_activity(a: dict[str, Any]) -> dict[str, Any]:
    """Extract the most useful fields from a raw activity object."""
    result: dict[str, Any] = {
        "activity_id": a["activity_id"],
        "app": a.get("app", ""),
        "type": a.get("type", ""),
        "user": a.get("user", ""),
        "subject": a.get("subject", ""),
        "datetime": a.get("datetime", ""),
    }
    message = a.get("message", "")
    if message:
        result["message"] = message
    link = a.get("link", "")
    if link:
        result["link"] = link
    object_type = a.get("object_type", "")
    if object_type:
        result["object_type"] = object_type
        result["object_id"] = a.get("object_id", 0)
        result["object_name"] = a.get("object_name", "")
    return result


def register(mcp: FastMCP) -> None:
    """Register activity tools with the MCP server."""

    @mcp.tool()
    @require_permission(PermissionLevel.READ)
    async def get_activity(
        activity_filter: str = "all",
        limit: int = 30,
        since: int = 0,
        object_type: str = "",
        object_id: int = 0,
        sort: str = "desc",
    ) -> str:
        """Get the recent activity feed for the current Nextcloud user.

        Activities track what happened across Nextcloud: file changes, shares,
        calendar events, Talk messages, and more.

        Available filters: "all", "self" (your actions), "by" (others' actions),
        "files", "files_sharing", "files_favorites", "calendar", "calendar_todo",
        "comments", "contacts", "deck", "forms", "security", "tables", "circles".

        To get activities for a specific file or object, provide both object_type
        and object_id (e.g., object_type="files", object_id=742).

        Args:
            activity_filter: Activity filter (default: "all"). Use "self" to see only
                    your actions, "by" for actions by others, or an app-specific
                    filter like "files" or "calendar".
            limit: Maximum number of activities to return (1-200, default: 30).
            since: Activity ID to paginate from. Use the smallest activity_id from
                   a previous call to fetch older activities. Default 0 = newest.
            object_type: Filter by object type (e.g., "files"). Must be used
                         together with object_id.
            object_id: Filter by object ID. Must be used together with object_type.
            sort: Sort order: "desc" (newest first, default) or "asc" (oldest first).

        Returns:
            JSON list of activity objects, each with: activity_id, app, type,
            user, subject, datetime. The last line shows pagination info if more
            activities may exist.
        """
        if activity_filter not in _VALID_FILTERS:
            valid = ", ".join(sorted(_VALID_FILTERS))
            raise ValueError(f"Invalid activity_filter '{activity_filter}'. Valid filters: {valid}")
        if sort not in _VALID_SORT:
            raise ValueError(f"Invalid sort '{sort}'. Must be 'asc' or 'desc'.")
        limit = max(1, min(200, limit))
        client = get_client()
        params: dict[str, str] = {"limit": str(limit), "sort": sort}
        if since:
            params["since"] = str(since)
        if object_type and object_id:
            params["object_type"] = object_type
            params["object_id"] = str(object_id)
        path = (
            f"apps/activity/api/v2/activity/{activity_filter}"
            if activity_filter != "all"
            else "apps/activity/api/v2/activity"
        )
        data = await client.ocs_get(path, params=params)
        activities = [_format_activity(a) for a in data]
        result = json.dumps(activities, indent=2, default=str)
        if activities:
            oldest_id = min(a["activity_id"] for a in activities)
            result += f"\n\n--- {len(activities)} activities. For older results, call with since={oldest_id} ---"
        return result
