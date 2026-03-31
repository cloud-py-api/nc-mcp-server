"""Integration tests for Calendar tools against a real Nextcloud instance."""

import contextlib
import json
import uuid

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from .conftest import McpTestHelper

pytestmark = pytest.mark.integration

CAL_ID = "personal"


@pytest.fixture(autouse=True)
async def _cleanup_test_events(nc_mcp: McpTestHelper) -> None:
    """Delete any leftover test events before each test."""
    result = await nc_mcp.call("get_events", calendar_id=CAL_ID, limit=200)
    for event in json.loads(result)["data"]:
        uid = event["uid"]
        if uid.startswith("mcp-test-") or "mcp-test" in event.get("summary", ""):
            with contextlib.suppress(ToolError):
                await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=uid)


class TestListCalendars:
    @pytest.mark.asyncio
    async def test_returns_list(self, nc_mcp: McpTestHelper) -> None:
        result = await nc_mcp.call("list_calendars")
        calendars = json.loads(result)
        assert isinstance(calendars, list)
        assert calendars

    @pytest.mark.asyncio
    async def test_personal_calendar_exists(self, nc_mcp: McpTestHelper) -> None:
        result = await nc_mcp.call("list_calendars")
        calendars = json.loads(result)
        ids = [c["id"] for c in calendars]
        assert CAL_ID in ids

    @pytest.mark.asyncio
    async def test_calendar_has_fields(self, nc_mcp: McpTestHelper) -> None:
        result = await nc_mcp.call("list_calendars")
        calendars = json.loads(result)
        personal = next(c for c in calendars if c["id"] == CAL_ID)
        for field in ["id", "name", "components", "writable"]:
            assert field in personal, f"Missing field: {field}"
        assert personal["writable"] is True
        assert "VEVENT" in personal["components"]

    @pytest.mark.asyncio
    async def test_skips_inbox_outbox_trashbin(self, nc_mcp: McpTestHelper) -> None:
        result = await nc_mcp.call("list_calendars")
        calendars = json.loads(result)
        ids = [c["id"] for c in calendars]
        for skip in ["inbox", "outbox", "trashbin"]:
            assert skip not in ids

    @pytest.mark.asyncio
    async def test_contact_birthdays_not_writable(self, nc_mcp: McpTestHelper) -> None:
        result = await nc_mcp.call("list_calendars")
        calendars = json.loads(result)
        birthdays = next((c for c in calendars if c["id"] == "contact_birthdays"), None)
        if birthdays:
            assert birthdays["writable"] is False


class TestCreateEvent:
    @pytest.mark.asyncio
    async def test_create_timed_event(self, nc_mcp: McpTestHelper) -> None:
        result = await nc_mcp.call(
            "create_event",
            calendar_id=CAL_ID,
            summary="mcp-test-timed",
            start="2026-06-15T10:00:00Z",
            end="2026-06-15T11:00:00Z",
        )
        created = json.loads(result)
        assert "uid" in created
        assert created["summary"] == "mcp-test-timed"

        event = json.loads(await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid=created["uid"]))
        assert event["summary"] == "mcp-test-timed"
        assert event["all_day"] is False
        assert "2026-06-15T10:00:00" in event["dtstart"]

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])

    @pytest.mark.asyncio
    async def test_create_all_day_event(self, nc_mcp: McpTestHelper) -> None:
        result = await nc_mcp.call(
            "create_event",
            calendar_id=CAL_ID,
            summary="mcp-test-allday",
            start="2026-06-20",
            all_day=True,
        )
        created = json.loads(result)
        event = json.loads(await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid=created["uid"]))
        assert event["all_day"] is True
        assert event["dtstart"] == "2026-06-20"
        assert event["dtend"] == "2026-06-21"

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])

    @pytest.mark.asyncio
    async def test_create_with_description_and_location(self, nc_mcp: McpTestHelper) -> None:
        result = await nc_mcp.call(
            "create_event",
            calendar_id=CAL_ID,
            summary="mcp-test-details",
            start="2026-07-01T14:00:00Z",
            end="2026-07-01T15:00:00Z",
            description="Test description with special chars: <>&",
            location="Building A, Room 101",
        )
        created = json.loads(result)
        event = json.loads(await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid=created["uid"]))
        assert event["description"] == "Test description with special chars: <>&"
        assert event["location"] == "Building A, Room 101"

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])

    @pytest.mark.asyncio
    async def test_create_with_tentative_status(self, nc_mcp: McpTestHelper) -> None:
        result = await nc_mcp.call(
            "create_event",
            calendar_id=CAL_ID,
            summary="mcp-test-tentative",
            start="2026-07-10T09:00:00Z",
            status="TENTATIVE",
        )
        created = json.loads(result)
        event = json.loads(await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid=created["uid"]))
        assert event["status"] == "TENTATIVE"

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])

    @pytest.mark.asyncio
    async def test_create_defaults_end_timed(self, nc_mcp: McpTestHelper) -> None:
        result = await nc_mcp.call(
            "create_event",
            calendar_id=CAL_ID,
            summary="mcp-test-default-end",
            start="2026-08-01T13:00:00Z",
        )
        created = json.loads(result)
        event = json.loads(await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid=created["uid"]))
        assert "2026-08-01T14:00:00" in event["dtend"]

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])

    @pytest.mark.asyncio
    async def test_create_with_categories(self, nc_mcp: McpTestHelper) -> None:
        result = await nc_mcp.call(
            "create_event",
            calendar_id=CAL_ID,
            summary="mcp-test-cats",
            start="2026-08-05T10:00:00Z",
            categories="Work, Meeting, Important",
        )
        created = json.loads(result)
        event = json.loads(await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid=created["uid"]))
        assert "categories" in event
        assert "Work" in event["categories"]
        assert "Meeting" in event["categories"]
        assert "Important" in event["categories"]

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])

    @pytest.mark.asyncio
    async def test_create_recurring_weekly(self, nc_mcp: McpTestHelper) -> None:
        result = await nc_mcp.call(
            "create_event",
            calendar_id=CAL_ID,
            summary="mcp-test-weekly",
            start="2027-06-02T10:00:00Z",
            end="2027-06-02T11:00:00Z",
            rrule="FREQ=WEEKLY;COUNT=4",
        )
        created = json.loads(result)
        event = json.loads(await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid=created["uid"]))
        assert "rrule" in event
        assert "WEEKLY" in event["rrule"]
        assert "COUNT=4" in event["rrule"]

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])

    @pytest.mark.asyncio
    async def test_create_recurring_daily_with_until(self, nc_mcp: McpTestHelper) -> None:
        result = await nc_mcp.call(
            "create_event",
            calendar_id=CAL_ID,
            summary="mcp-test-daily",
            start="2027-07-01T09:00:00Z",
            end="2027-07-01T09:30:00Z",
            rrule="FREQ=DAILY;UNTIL=20270705T235959Z",
        )
        created = json.loads(result)
        events = json.loads(
            await nc_mcp.call(
                "get_events",
                calendar_id=CAL_ID,
                start="2027-07-01T00:00:00Z",
                end="2027-07-31T23:59:59Z",
            )
        )["data"]
        matching = [e for e in events if e["uid"] == created["uid"]]
        assert len(matching) >= 1

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])

    @pytest.mark.asyncio
    async def test_create_recurring_monthly_byday(self, nc_mcp: McpTestHelper) -> None:
        result = await nc_mcp.call(
            "create_event",
            calendar_id=CAL_ID,
            summary="mcp-test-monthly",
            start="2027-08-01T14:00:00Z",
            end="2027-08-01T15:00:00Z",
            rrule="FREQ=MONTHLY;BYMONTHDAY=1;COUNT=3",
        )
        created = json.loads(result)
        event = json.loads(await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid=created["uid"]))
        assert "MONTHLY" in event["rrule"]
        assert "BYMONTHDAY=1" in event["rrule"]

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])

    @pytest.mark.asyncio
    async def test_create_invalid_status_raises(self, nc_mcp: McpTestHelper) -> None:
        with pytest.raises((ToolError, ValueError)):
            await nc_mcp.call(
                "create_event",
                calendar_id=CAL_ID,
                summary="mcp-test-bad-status",
                start="2026-08-01T10:00:00Z",
                status="INVALID",
            )

    @pytest.mark.asyncio
    async def test_create_in_nonexistent_calendar_raises(self, nc_mcp: McpTestHelper) -> None:
        with pytest.raises(ToolError):
            await nc_mcp.call(
                "create_event",
                calendar_id="nonexistent-cal-xyz",
                summary="mcp-test-bad-cal",
                start="2026-08-01T10:00:00Z",
            )


class TestGetEvents:
    @pytest.mark.asyncio
    async def test_get_empty_calendar(self, nc_mcp: McpTestHelper) -> None:
        result = await nc_mcp.call("get_events", calendar_id=CAL_ID, limit=200)
        events = json.loads(result)["data"]
        assert isinstance(events, list)

    @pytest.mark.asyncio
    async def test_get_events_returns_created(self, nc_mcp: McpTestHelper) -> None:
        created = json.loads(
            await nc_mcp.call(
                "create_event",
                calendar_id=CAL_ID,
                summary="mcp-test-list",
                start="2026-09-01T10:00:00Z",
                end="2026-09-01T11:00:00Z",
            )
        )
        result = await nc_mcp.call("get_events", calendar_id=CAL_ID, limit=200)
        events = json.loads(result)["data"]
        uids = [e["uid"] for e in events]
        assert created["uid"] in uids

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])

    @pytest.mark.asyncio
    async def test_get_events_with_time_range(self, nc_mcp: McpTestHelper) -> None:
        uid1 = json.loads(
            await nc_mcp.call(
                "create_event",
                calendar_id=CAL_ID,
                summary="mcp-test-jan",
                start="2027-01-15T10:00:00Z",
                end="2027-01-15T11:00:00Z",
            )
        )["uid"]
        uid2 = json.loads(
            await nc_mcp.call(
                "create_event",
                calendar_id=CAL_ID,
                summary="mcp-test-mar",
                start="2027-03-15T10:00:00Z",
                end="2027-03-15T11:00:00Z",
            )
        )["uid"]

        result = await nc_mcp.call(
            "get_events",
            calendar_id=CAL_ID,
            start="2027-01-01T00:00:00Z",
            end="2027-01-31T23:59:59Z",
        )
        events = json.loads(result)["data"]
        uids = [e["uid"] for e in events]
        assert uid1 in uids
        assert uid2 not in uids

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=uid1)
        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=uid2)

    @pytest.mark.asyncio
    async def test_get_events_requires_both_start_and_end(self, nc_mcp: McpTestHelper) -> None:
        with pytest.raises((ToolError, ValueError)):
            await nc_mcp.call("get_events", calendar_id=CAL_ID, start="2027-01-01T00:00:00Z")

    @pytest.mark.asyncio
    async def test_event_has_etag(self, nc_mcp: McpTestHelper) -> None:
        created = json.loads(
            await nc_mcp.call(
                "create_event",
                calendar_id=CAL_ID,
                summary="mcp-test-etag",
                start="2026-10-01T10:00:00Z",
            )
        )
        result = await nc_mcp.call("get_events", calendar_id=CAL_ID, limit=200)
        events = json.loads(result)["data"]
        matching = [e for e in events if e["uid"] == created["uid"]]
        assert len(matching) == 1
        assert matching[0]["etag"]

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])


class TestGetEvent:
    @pytest.mark.asyncio
    async def test_get_single_event(self, nc_mcp: McpTestHelper) -> None:
        created = json.loads(
            await nc_mcp.call(
                "create_event",
                calendar_id=CAL_ID,
                summary="mcp-test-single",
                start="2026-11-01T09:00:00Z",
                end="2026-11-01T10:00:00Z",
                description="Single event test",
                location="Office",
            )
        )
        event = json.loads(await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid=created["uid"]))
        assert event["uid"] == created["uid"]
        assert event["summary"] == "mcp-test-single"
        assert event["description"] == "Single event test"
        assert event["location"] == "Office"
        assert event["etag"]

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])

    @pytest.mark.asyncio
    async def test_get_nonexistent_event_raises(self, nc_mcp: McpTestHelper) -> None:
        with pytest.raises(ToolError, match="not found"):
            await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid="nonexistent-uid-xyz")


class TestUpdateEvent:
    @pytest.mark.asyncio
    async def test_update_summary(self, nc_mcp: McpTestHelper) -> None:
        created = json.loads(
            await nc_mcp.call(
                "create_event",
                calendar_id=CAL_ID,
                summary="mcp-test-update-orig",
                start="2026-12-01T10:00:00Z",
            )
        )
        await nc_mcp.call("update_event", calendar_id=CAL_ID, event_uid=created["uid"], summary="mcp-test-updated")
        event = json.loads(await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid=created["uid"]))
        assert event["summary"] == "mcp-test-updated"

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])

    @pytest.mark.asyncio
    async def test_update_time(self, nc_mcp: McpTestHelper) -> None:
        created = json.loads(
            await nc_mcp.call(
                "create_event",
                calendar_id=CAL_ID,
                summary="mcp-test-update-time",
                start="2026-12-05T10:00:00Z",
                end="2026-12-05T11:00:00Z",
            )
        )
        await nc_mcp.call(
            "update_event",
            calendar_id=CAL_ID,
            event_uid=created["uid"],
            start="2026-12-05T14:00:00Z",
            end="2026-12-05T16:00:00Z",
        )
        event = json.loads(await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid=created["uid"]))
        assert "2026-12-05T14:00:00" in event["dtstart"]
        assert "2026-12-05T16:00:00" in event["dtend"]

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])

    @pytest.mark.asyncio
    async def test_update_description_and_location(self, nc_mcp: McpTestHelper) -> None:
        created = json.loads(
            await nc_mcp.call(
                "create_event",
                calendar_id=CAL_ID,
                summary="mcp-test-update-desc",
                start="2026-12-10T10:00:00Z",
            )
        )
        await nc_mcp.call(
            "update_event",
            calendar_id=CAL_ID,
            event_uid=created["uid"],
            description="Updated desc",
            location="New location",
        )
        event = json.loads(await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid=created["uid"]))
        assert event["description"] == "Updated desc"
        assert event["location"] == "New location"

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])

    @pytest.mark.asyncio
    async def test_update_clear_description(self, nc_mcp: McpTestHelper) -> None:
        created = json.loads(
            await nc_mcp.call(
                "create_event",
                calendar_id=CAL_ID,
                summary="mcp-test-clear",
                start="2026-12-15T10:00:00Z",
                description="To be cleared",
            )
        )
        await nc_mcp.call("update_event", calendar_id=CAL_ID, event_uid=created["uid"], description="")
        event = json.loads(await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid=created["uid"]))
        assert event["description"] == ""

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])

    @pytest.mark.asyncio
    async def test_update_status(self, nc_mcp: McpTestHelper) -> None:
        created = json.loads(
            await nc_mcp.call(
                "create_event",
                calendar_id=CAL_ID,
                summary="mcp-test-status",
                start="2026-12-20T10:00:00Z",
            )
        )
        await nc_mcp.call("update_event", calendar_id=CAL_ID, event_uid=created["uid"], status="CANCELLED")
        event = json.loads(await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid=created["uid"]))
        assert event["status"] == "CANCELLED"

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])

    @pytest.mark.asyncio
    async def test_update_categories(self, nc_mcp: McpTestHelper) -> None:
        created = json.loads(
            await nc_mcp.call(
                "create_event",
                calendar_id=CAL_ID,
                summary="mcp-test-update-cats",
                start="2026-12-22T10:00:00Z",
            )
        )
        await nc_mcp.call("update_event", calendar_id=CAL_ID, event_uid=created["uid"], categories="Personal,Travel")
        event = json.loads(await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid=created["uid"]))
        assert "categories" in event
        assert "Personal" in event["categories"]
        assert "Travel" in event["categories"]

        await nc_mcp.call("update_event", calendar_id=CAL_ID, event_uid=created["uid"], categories="")
        event = json.loads(await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid=created["uid"]))
        assert "categories" not in event or event.get("categories") == []

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])

    @pytest.mark.asyncio
    async def test_update_nonexistent_raises(self, nc_mcp: McpTestHelper) -> None:
        with pytest.raises(ToolError, match="not found"):
            await nc_mcp.call("update_event", calendar_id=CAL_ID, event_uid="nonexistent-uid", summary="x")

    @pytest.mark.asyncio
    async def test_update_invalid_status_raises(self, nc_mcp: McpTestHelper) -> None:
        created = json.loads(
            await nc_mcp.call(
                "create_event",
                calendar_id=CAL_ID,
                summary="mcp-test-bad-status-upd",
                start="2026-12-25T10:00:00Z",
            )
        )
        with pytest.raises((ToolError, ValueError)):
            await nc_mcp.call("update_event", calendar_id=CAL_ID, event_uid=created["uid"], status="BADSTATUS")

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])


class TestDeleteEvent:
    @pytest.mark.asyncio
    async def test_delete_event(self, nc_mcp: McpTestHelper) -> None:
        created = json.loads(
            await nc_mcp.call(
                "create_event",
                calendar_id=CAL_ID,
                summary="mcp-test-delete",
                start="2027-01-01T10:00:00Z",
            )
        )
        result = await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])
        assert "deleted" in result.lower()

        with pytest.raises(ToolError, match="not found"):
            await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid=created["uid"])

    @pytest.mark.asyncio
    async def test_delete_nonexistent_raises(self, nc_mcp: McpTestHelper) -> None:
        with pytest.raises(ToolError, match="not found"):
            await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid="nonexistent-uid-xyz")


class TestCalendarPermissions:
    @pytest.mark.asyncio
    async def test_read_only_allows_list(self, nc_mcp_read_only: McpTestHelper) -> None:
        result = await nc_mcp_read_only.call("list_calendars")
        assert isinstance(json.loads(result), list)

    @pytest.mark.asyncio
    async def test_read_only_allows_get_events(self, nc_mcp_read_only: McpTestHelper) -> None:
        result = await nc_mcp_read_only.call("get_events", calendar_id=CAL_ID, limit=200)
        assert isinstance(json.loads(result)["data"], list)

    @pytest.mark.asyncio
    async def test_read_only_blocks_create(self, nc_mcp_read_only: McpTestHelper) -> None:
        with pytest.raises(ToolError, match=r"requires 'write' permission"):
            await nc_mcp_read_only.call(
                "create_event",
                calendar_id=CAL_ID,
                summary="blocked",
                start="2027-01-01T10:00:00Z",
            )

    @pytest.mark.asyncio
    async def test_read_only_blocks_update(self, nc_mcp_read_only: McpTestHelper) -> None:
        with pytest.raises(ToolError, match=r"requires 'write' permission"):
            await nc_mcp_read_only.call(
                "update_event",
                calendar_id=CAL_ID,
                event_uid="any",
                summary="blocked",
            )

    @pytest.mark.asyncio
    async def test_read_only_blocks_delete(self, nc_mcp_read_only: McpTestHelper) -> None:
        with pytest.raises(ToolError, match=r"requires 'destructive' permission"):
            await nc_mcp_read_only.call("delete_event", calendar_id=CAL_ID, event_uid="any")


class TestCalendarEdgeCases:
    @pytest.mark.asyncio
    async def test_create_and_get_preserves_unicode(self, nc_mcp: McpTestHelper) -> None:
        created = json.loads(
            await nc_mcp.call(
                "create_event",
                calendar_id=CAL_ID,
                summary="mcp-test-unicode: Ünïcödé 日本語 🎉",
                start="2027-02-01T10:00:00Z",
                description="Описание на русском",
                location="東京タワー",
            )
        )
        event = json.loads(await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid=created["uid"]))
        assert "Ünïcödé" in event["summary"]
        assert "日本語" in event["summary"]
        assert "Описание на русском" in event["description"]
        assert "東京タワー" in event["location"]

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])

    @pytest.mark.asyncio
    async def test_create_multi_day_all_day(self, nc_mcp: McpTestHelper) -> None:
        created = json.loads(
            await nc_mcp.call(
                "create_event",
                calendar_id=CAL_ID,
                summary="mcp-test-multiday",
                start="2027-03-01",
                end="2027-03-04",
                all_day=True,
            )
        )
        event = json.loads(await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid=created["uid"]))
        assert event["all_day"] is True
        assert event["dtstart"] == "2027-03-01"
        assert event["dtend"] == "2027-03-04"

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])

    @pytest.mark.asyncio
    async def test_update_preserves_unchanged_fields(self, nc_mcp: McpTestHelper) -> None:
        created = json.loads(
            await nc_mcp.call(
                "create_event",
                calendar_id=CAL_ID,
                summary="mcp-test-preserve",
                start="2027-04-01T10:00:00Z",
                end="2027-04-01T11:00:00Z",
                description="Original desc",
                location="Original loc",
            )
        )
        await nc_mcp.call("update_event", calendar_id=CAL_ID, event_uid=created["uid"], summary="mcp-test-new-title")
        event = json.loads(await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid=created["uid"]))
        assert event["summary"] == "mcp-test-new-title"
        assert event["description"] == "Original desc"
        assert event["location"] == "Original loc"
        assert "2027-04-01T10:00:00" in event["dtstart"]

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])

    @pytest.mark.asyncio
    async def test_event_with_categories_raw(self, nc_mcp: McpTestHelper) -> None:
        uid = f"mcp-test-cats-{uuid.uuid4()}"
        ical = (
            "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//EN\r\n"
            "BEGIN:VEVENT\r\n"
            f"UID:{uid}\r\n"
            "DTSTART:20270601T100000Z\r\n"
            "DTEND:20270601T110000Z\r\n"
            "SUMMARY:mcp-test-categories\r\n"
            "CATEGORIES:Work,Meeting\r\n"
            "DTSTAMP:20260330T000000Z\r\n"
            "END:VEVENT\r\nEND:VCALENDAR\r\n"
        )
        user = nc_mcp.client._config.user
        path = f"calendars/{user}/{CAL_ID}/{uid}.ics"
        await nc_mcp.client.dav_request(
            "PUT",
            path,
            body=ical,
            headers={"Content-Type": "text/calendar; charset=utf-8"},
        )
        event = json.loads(await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid=uid))
        assert "categories" in event
        assert "Work" in event["categories"]
        assert "Meeting" in event["categories"]

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=uid)

    @pytest.mark.asyncio
    async def test_event_with_rrule(self, nc_mcp: McpTestHelper) -> None:
        uid = f"mcp-test-rrule-{uuid.uuid4()}"
        ical = (
            "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//EN\r\n"
            "BEGIN:VEVENT\r\n"
            f"UID:{uid}\r\n"
            "DTSTART:20270701T090000Z\r\n"
            "DTEND:20270701T100000Z\r\n"
            "SUMMARY:mcp-test-rrule\r\n"
            "RRULE:FREQ=WEEKLY;COUNT=4\r\n"
            "DTSTAMP:20260330T000000Z\r\n"
            "END:VEVENT\r\nEND:VCALENDAR\r\n"
        )
        user = nc_mcp.client._config.user
        path = f"calendars/{user}/{CAL_ID}/{uid}.ics"
        await nc_mcp.client.dav_request(
            "PUT",
            path,
            body=ical,
            headers={"Content-Type": "text/calendar; charset=utf-8"},
        )
        event = json.loads(await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid=uid))
        assert "rrule" in event
        assert "WEEKLY" in event["rrule"]
        assert "COUNT=4" in event["rrule"]

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=uid)

    @pytest.mark.asyncio
    async def test_create_event_with_no_timezone(self, nc_mcp: McpTestHelper) -> None:
        created = json.loads(
            await nc_mcp.call(
                "create_event",
                calendar_id=CAL_ID,
                summary="mcp-test-no-tz",
                start="2027-05-01T15:30:00",
            )
        )
        event = json.loads(await nc_mcp.call("get_event", calendar_id=CAL_ID, event_uid=created["uid"]))
        assert "2027-05-01T15:30:00" in event["dtstart"]

        await nc_mcp.call("delete_event", calendar_id=CAL_ID, event_uid=created["uid"])
