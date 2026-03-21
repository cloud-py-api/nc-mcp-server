"""Integration tests for notifications against a real Nextcloud instance."""

import pytest

from nextcloud_mcp.client import NextcloudClient

pytestmark = pytest.mark.integration

ADMIN_NOTIF_ENDPOINT = "apps/notifications/api/v1/admin_notifications/admin"
LIST_ENDPOINT = "apps/notifications/api/v2/notifications"


async def _generate_notification(
    nc_client: NextcloudClient,
    subject: str = "Test",
    message: str = "body",
) -> None:
    """Create a notification via the admin_notifications OCS API."""
    await nc_client.ocs_post(
        ADMIN_NOTIF_ENDPOINT,
        data={"shortMessage": subject, "longMessage": message},
    )


async def _dismiss_all(nc_client: NextcloudClient) -> None:
    """Dismiss all notifications for cleanup."""
    await nc_client.ocs_delete(LIST_ENDPOINT)


class TestListNotifications:
    @pytest.mark.asyncio
    async def test_returns_list(self, nc_client: NextcloudClient) -> None:
        data = await nc_client.ocs_get(LIST_ENDPOINT)
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_notification_fields(self, nc_client: NextcloudClient) -> None:
        await _generate_notification(nc_client, subject="field-test", message="field body")
        data = await nc_client.ocs_get(LIST_ENDPOINT)
        assert len(data) >= 1
        notif = data[0]
        assert "notification_id" in notif
        assert "subject" in notif
        assert "message" in notif
        assert "datetime" in notif
        assert "app" in notif
        await _dismiss_all(nc_client)


class TestDismissNotification:
    @pytest.mark.asyncio
    async def test_dismiss_removes_notification(self, nc_client: NextcloudClient) -> None:
        await _generate_notification(nc_client, subject="dismiss-test")
        data = await nc_client.ocs_get(LIST_ENDPOINT)
        target = next(n for n in data if n["subject"] == "dismiss-test")
        nid = target["notification_id"]

        await nc_client.ocs_delete(f"apps/notifications/api/v2/notifications/{nid}")

        data_after = await nc_client.ocs_get(LIST_ENDPOINT)
        ids_after = [n["notification_id"] for n in data_after]
        assert nid not in ids_after
        await _dismiss_all(nc_client)

    @pytest.mark.asyncio
    async def test_dismiss_nonexistent_is_idempotent(self, nc_client: NextcloudClient) -> None:
        # Nextcloud returns 200 for nonexistent IDs — idempotent delete
        await nc_client.ocs_delete("apps/notifications/api/v2/notifications/999999")


class TestDismissAllNotifications:
    @pytest.mark.asyncio
    async def test_dismiss_all_clears_notifications(self, nc_client: NextcloudClient) -> None:
        await _generate_notification(nc_client, subject="all-1")
        await _generate_notification(nc_client, subject="all-2")
        data = await nc_client.ocs_get(LIST_ENDPOINT)
        assert len(data) >= 2

        await nc_client.ocs_delete(LIST_ENDPOINT)

        data_after = await nc_client.ocs_get(LIST_ENDPOINT)
        assert len(data_after) == 0

    @pytest.mark.asyncio
    async def test_dismiss_all_when_empty_succeeds(self, nc_client: NextcloudClient) -> None:
        await _dismiss_all(nc_client)
        await nc_client.ocs_delete(LIST_ENDPOINT)
        data = await nc_client.ocs_get(LIST_ENDPOINT)
        assert len(data) == 0
