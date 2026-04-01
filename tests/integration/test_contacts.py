"""Integration tests for Contacts tools against a real Nextcloud instance."""

import contextlib
import json
from typing import Any

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from nc_mcp_server.state import get_config

from .conftest import McpTestHelper

pytestmark = pytest.mark.integration

BOOK_ID = "contacts"
PREFIX = "mcp-test-contact"


@pytest.fixture(autouse=True)
async def _cleanup_test_contacts(nc_mcp: McpTestHelper) -> None:
    """Delete any leftover test contacts before each test."""
    result = await nc_mcp.call("get_contacts", book_id=BOOK_ID, limit=200)
    for contact in json.loads(result)["data"]:
        uid = contact["uid"]
        if uid.startswith("mcp-") and PREFIX in contact.get("full_name", ""):
            with contextlib.suppress(ToolError):
                await nc_mcp.call("delete_contact", uid=uid, book_id=BOOK_ID)


async def _create(nc_mcp: McpTestHelper, suffix: str, **extra: str) -> dict[str, Any]:
    """Create a test contact and return the parsed result."""
    kw: dict[str, str] = {"full_name": f"{PREFIX}-{suffix}", "book_id": BOOK_ID, **extra}
    result: dict[str, Any] = json.loads(await nc_mcp.call("create_contact", **kw))
    return result


class TestListAddressbooks:
    @pytest.mark.asyncio
    async def test_returns_list(self, nc_mcp: McpTestHelper) -> None:
        result = await nc_mcp.call("list_addressbooks")
        books: list[dict[str, Any]] = json.loads(result)
        assert isinstance(books, list)
        assert len(books) >= 1

    @pytest.mark.asyncio
    async def test_default_contacts_book_exists(self, nc_mcp: McpTestHelper) -> None:
        books = json.loads(await nc_mcp.call("list_addressbooks"))
        ids = [b["id"] for b in books]
        assert "contacts" in ids

    @pytest.mark.asyncio
    async def test_book_has_required_fields(self, nc_mcp: McpTestHelper) -> None:
        books = json.loads(await nc_mcp.call("list_addressbooks"))
        book = books[0]
        for field in ["id", "name"]:
            assert field in book, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_excludes_system_books(self, nc_mcp: McpTestHelper) -> None:
        books = json.loads(await nc_mcp.call("list_addressbooks"))
        ids = [b["id"] for b in books]
        assert "z-server-generated--system" not in ids
        assert "z-app-generated--contactsinteraction--recent" not in ids


class TestCreateContact:
    @pytest.mark.asyncio
    async def test_create_with_full_name(self, nc_mcp: McpTestHelper) -> None:
        contact = await _create(nc_mcp, "fullname")
        assert contact["uid"].startswith("mcp-")
        assert contact["full_name"] == f"{PREFIX}-fullname"

    @pytest.mark.asyncio
    async def test_create_with_given_and_family(self, nc_mcp: McpTestHelper) -> None:
        result = json.loads(
            await nc_mcp.call("create_contact", given_name=f"{PREFIX}-given", family_name="Family", book_id=BOOK_ID)
        )
        assert "given" in result.get("full_name", "").lower() or result.get("name", {}).get("given")

    @pytest.mark.asyncio
    async def test_create_with_email(self, nc_mcp: McpTestHelper) -> None:
        contact = await _create(nc_mcp, "email", email="test@example.com")
        assert any(e["value"] == "test@example.com" for e in contact.get("emails", []))

    @pytest.mark.asyncio
    async def test_create_with_phone(self, nc_mcp: McpTestHelper) -> None:
        contact = await _create(nc_mcp, "phone", phone="+1234567890")
        assert any(p["value"] == "+1234567890" for p in contact.get("phones", []))

    @pytest.mark.asyncio
    async def test_create_with_organization(self, nc_mcp: McpTestHelper) -> None:
        contact = await _create(nc_mcp, "org", organization="Test Corp")
        assert contact.get("organization") == "Test Corp"

    @pytest.mark.asyncio
    async def test_create_with_title(self, nc_mcp: McpTestHelper) -> None:
        contact = await _create(nc_mcp, "title", title="Engineer")
        assert contact.get("title") == "Engineer"

    @pytest.mark.asyncio
    async def test_create_with_note(self, nc_mcp: McpTestHelper) -> None:
        contact = await _create(nc_mcp, "note", note="Important person")
        assert contact.get("note") == "Important person"

    @pytest.mark.asyncio
    async def test_create_with_all_fields(self, nc_mcp: McpTestHelper) -> None:
        contact = json.loads(
            await nc_mcp.call(
                "create_contact",
                full_name=f"{PREFIX}-allflds",
                email="all@test.com",
                phone="+9999999999",
                organization="Full Corp",
                title="CTO",
                note="Has all fields",
                book_id=BOOK_ID,
            )
        )
        assert contact["full_name"] == f"{PREFIX}-allflds"
        assert contact.get("organization") == "Full Corp"
        assert contact.get("title") == "CTO"
        assert contact.get("note") == "Has all fields"

    @pytest.mark.asyncio
    async def test_create_special_chars_roundtrip(self, nc_mcp: McpTestHelper) -> None:
        contact = await _create(nc_mcp, "special-R&D", organization="R&D <Team>", title='VP "Sales"')
        fetched = json.loads(await nc_mcp.call("get_contact", uid=contact["uid"], book_id=BOOK_ID))
        assert fetched.get("organization") == "R&D <Team>"
        assert fetched.get("title") == 'VP "Sales"'

    @pytest.mark.asyncio
    async def test_create_no_name_raises(self, nc_mcp: McpTestHelper) -> None:
        with pytest.raises((ToolError, ValueError)):
            await nc_mcp.call("create_contact", email="noname@test.com", book_id=BOOK_ID)

    @pytest.mark.asyncio
    async def test_create_unicode_name(self, nc_mcp: McpTestHelper) -> None:
        contact = await _create(nc_mcp, "unicode-Müller-日本語")
        assert "Müller" in contact["full_name"]
        assert "日本語" in contact["full_name"]


class TestGetContacts:
    @pytest.mark.asyncio
    async def test_returns_paginated_response(self, nc_mcp: McpTestHelper) -> None:
        result = json.loads(await nc_mcp.call("get_contacts", book_id=BOOK_ID, limit=200))
        assert "data" in result
        assert "pagination" in result
        assert isinstance(result["data"], list)

    @pytest.mark.asyncio
    async def test_created_contact_appears(self, nc_mcp: McpTestHelper) -> None:
        created = await _create(nc_mcp, "appears")
        result = json.loads(await nc_mcp.call("get_contacts", book_id=BOOK_ID, limit=200))
        uids = [c["uid"] for c in result["data"]]
        assert created["uid"] in uids

    @pytest.mark.asyncio
    async def test_contact_has_etag(self, nc_mcp: McpTestHelper) -> None:
        created = await _create(nc_mcp, "etag")
        result = json.loads(await nc_mcp.call("get_contacts", book_id=BOOK_ID, limit=200))
        match = next(c for c in result["data"] if c["uid"] == created["uid"])
        assert match["etag"]

    @pytest.mark.asyncio
    async def test_pagination_limit(self, nc_mcp: McpTestHelper) -> None:
        for i in range(3):
            await _create(nc_mcp, f"paglim-{i}")
        result = json.loads(await nc_mcp.call("get_contacts", book_id=BOOK_ID, limit=2))
        assert result["pagination"]["count"] <= 2
        assert result["pagination"]["limit"] == 2

    @pytest.mark.asyncio
    async def test_nonexistent_book_raises(self, nc_mcp: McpTestHelper) -> None:
        with pytest.raises(ToolError):
            await nc_mcp.call("get_contacts", book_id="nonexistent-book-xyz")


class TestGetContact:
    @pytest.mark.asyncio
    async def test_get_by_uid(self, nc_mcp: McpTestHelper) -> None:
        created = await _create(nc_mcp, "getbyuid", email="get@test.com")
        contact = json.loads(await nc_mcp.call("get_contact", uid=created["uid"], book_id=BOOK_ID))
        assert contact["uid"] == created["uid"]
        assert contact["full_name"] == f"{PREFIX}-getbyuid"
        assert any(e["value"] == "get@test.com" for e in contact.get("emails", []))
        assert contact["etag"]

    @pytest.mark.asyncio
    async def test_nonexistent_uid_raises(self, nc_mcp: McpTestHelper) -> None:
        with pytest.raises((ToolError, ValueError)):
            await nc_mcp.call("get_contact", uid="nonexistent-uid-xyz", book_id=BOOK_ID)


class TestUpdateContact:
    @pytest.mark.asyncio
    async def test_update_title(self, nc_mcp: McpTestHelper) -> None:
        created = await _create(nc_mcp, "upd-title")
        contact = json.loads(await nc_mcp.call("get_contact", uid=created["uid"], book_id=BOOK_ID))
        updated = json.loads(
            await nc_mcp.call(
                "update_contact", uid=created["uid"], etag=contact["etag"], title="New Title", book_id=BOOK_ID
            )
        )
        assert updated.get("title") == "New Title"

    @pytest.mark.asyncio
    async def test_update_email(self, nc_mcp: McpTestHelper) -> None:
        created = await _create(nc_mcp, "upd-email", email="old@test.com")
        contact = json.loads(await nc_mcp.call("get_contact", uid=created["uid"], book_id=BOOK_ID))
        updated = json.loads(
            await nc_mcp.call(
                "update_contact", uid=created["uid"], etag=contact["etag"], email="new@test.com", book_id=BOOK_ID
            )
        )
        emails = [e["value"] for e in updated.get("emails", [])]
        assert "new@test.com" in emails

    @pytest.mark.asyncio
    async def test_update_organization(self, nc_mcp: McpTestHelper) -> None:
        created = await _create(nc_mcp, "upd-org", organization="Old Corp")
        contact = json.loads(await nc_mcp.call("get_contact", uid=created["uid"], book_id=BOOK_ID))
        updated = json.loads(
            await nc_mcp.call(
                "update_contact",
                uid=created["uid"],
                etag=contact["etag"],
                organization="New Corp",
                book_id=BOOK_ID,
            )
        )
        assert updated.get("organization") == "New Corp"

    @pytest.mark.asyncio
    async def test_update_preserves_unchanged_fields(self, nc_mcp: McpTestHelper) -> None:
        created = await _create(nc_mcp, "upd-preserve", email="keep@test.com", organization="Keep Corp")
        contact = json.loads(await nc_mcp.call("get_contact", uid=created["uid"], book_id=BOOK_ID))
        updated = json.loads(
            await nc_mcp.call(
                "update_contact", uid=created["uid"], etag=contact["etag"], note="Added note", book_id=BOOK_ID
            )
        )
        assert updated.get("note") == "Added note"
        assert updated.get("organization") == "Keep Corp"

    @pytest.mark.asyncio
    async def test_update_etag_changes(self, nc_mcp: McpTestHelper) -> None:
        created = await _create(nc_mcp, "upd-etag")
        contact = json.loads(await nc_mcp.call("get_contact", uid=created["uid"], book_id=BOOK_ID))
        updated = json.loads(
            await nc_mcp.call(
                "update_contact", uid=created["uid"], etag=contact["etag"], title="Changed", book_id=BOOK_ID
            )
        )
        assert updated["etag"] != contact["etag"]

    @pytest.mark.asyncio
    async def test_update_wrong_etag_fails(self, nc_mcp: McpTestHelper) -> None:
        created = await _create(nc_mcp, "upd-badetag")
        with pytest.raises(ToolError):
            await nc_mcp.call("update_contact", uid=created["uid"], etag="wrong-etag", title="Nope", book_id=BOOK_ID)

    @pytest.mark.asyncio
    async def test_update_no_fields_raises(self, nc_mcp: McpTestHelper) -> None:
        created = await _create(nc_mcp, "upd-nofields")
        contact = json.loads(await nc_mcp.call("get_contact", uid=created["uid"], book_id=BOOK_ID))
        with pytest.raises((ToolError, ValueError)):
            await nc_mcp.call("update_contact", uid=created["uid"], etag=contact["etag"], book_id=BOOK_ID)

    @pytest.mark.asyncio
    async def test_update_nonexistent_uid_raises(self, nc_mcp: McpTestHelper) -> None:
        with pytest.raises((ToolError, ValueError)):
            await nc_mcp.call("update_contact", uid="nonexistent-uid-xyz", etag="fake", title="Nope", book_id=BOOK_ID)


async def _put_vcard_with_categories(nc_mcp: McpTestHelper, suffix: str, categories: list[str]) -> str:
    """Create a test contact with CATEGORIES via direct CardDAV PUT. Returns UID."""
    uid = f"mcp-cat-{suffix}"
    full_name = f"{PREFIX}-cat-{suffix}"
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"UID:{uid}",
        f"FN:{full_name}",
        f"N:;{full_name};;;",
    ]
    if categories:
        lines.append(f"CATEGORIES:{','.join(categories)}")
    lines.append("END:VCARD")
    vcard = "\r\n".join(lines) + "\r\n"
    config = get_config()
    await nc_mcp.client.dav_request(
        "PUT",
        f"addressbooks/users/{config.user}/{BOOK_ID}/{uid}.vcf",
        body=vcard,
        headers={"Content-Type": "text/vcard; charset=utf-8"},
        context=f"Create test contact '{uid}'",
    )
    return uid


class TestContactCategories:
    @pytest.mark.asyncio
    async def test_single_category(self, nc_mcp: McpTestHelper) -> None:
        uid = await _put_vcard_with_categories(nc_mcp, "single", ["Work"])
        contact = json.loads(await nc_mcp.call("get_contact", uid=uid, book_id=BOOK_ID))
        assert contact["categories"] == ["Work"]

    @pytest.mark.asyncio
    async def test_multiple_categories(self, nc_mcp: McpTestHelper) -> None:
        uid = await _put_vcard_with_categories(nc_mcp, "multi", ["Work", "VIP", "Family"])
        contact = json.loads(await nc_mcp.call("get_contact", uid=uid, book_id=BOOK_ID))
        assert set(contact["categories"]) == {"Work", "VIP", "Family"}

    @pytest.mark.asyncio
    async def test_no_categories_omits_field(self, nc_mcp: McpTestHelper) -> None:
        contact = await _create(nc_mcp, "cat-none")
        fetched = json.loads(await nc_mcp.call("get_contact", uid=contact["uid"], book_id=BOOK_ID))
        assert "categories" not in fetched

    @pytest.mark.asyncio
    async def test_categories_in_listing(self, nc_mcp: McpTestHelper) -> None:
        uid = await _put_vcard_with_categories(nc_mcp, "list", ["Colleague", "Friend"])
        result = json.loads(await nc_mcp.call("get_contacts", book_id=BOOK_ID, limit=200))
        match = next(c for c in result["data"] if c["uid"] == uid)
        assert set(match["categories"]) == {"Colleague", "Friend"}

    @pytest.mark.asyncio
    async def test_unicode_categories(self, nc_mcp: McpTestHelper) -> None:
        uid = await _put_vcard_with_categories(nc_mcp, "unicode", ["Arbeit", "Famille", "友達"])
        contact = json.loads(await nc_mcp.call("get_contact", uid=uid, book_id=BOOK_ID))
        assert set(contact["categories"]) == {"Arbeit", "Famille", "友達"}


async def _put_vcard_with_name(nc_mcp: McpTestHelper, suffix: str, given: str = "", family: str = "") -> str:
    """Create a test contact with a structured N field via direct CardDAV PUT. Returns UID."""
    uid = f"mcp-name-{suffix}"
    full_name = f"{PREFIX}-{suffix}"
    n_parts = f"{family};{given};;;"
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"UID:{uid}",
        f"FN:{full_name}",
        f"N:{n_parts}",
        "END:VCARD",
    ]
    vcard = "\r\n".join(lines) + "\r\n"
    config = get_config()
    await nc_mcp.client.dav_request(
        "PUT",
        f"addressbooks/users/{config.user}/{BOOK_ID}/{uid}.vcf",
        body=vcard,
        headers={"Content-Type": "text/vcard; charset=utf-8"},
        context=f"Create test contact '{uid}'",
    )
    return uid


class TestUpdateStructuredName:
    @pytest.mark.asyncio
    async def test_update_given_preserves_family(self, nc_mcp: McpTestHelper) -> None:
        uid = await _put_vcard_with_name(nc_mcp, "upd-given", given="John", family="Doe")
        contact = json.loads(await nc_mcp.call("get_contact", uid=uid, book_id=BOOK_ID))
        updated = json.loads(
            await nc_mcp.call("update_contact", uid=uid, etag=contact["etag"], given_name="Jane", book_id=BOOK_ID)
        )
        assert updated["name"]["given"] == "Jane"
        assert updated["name"]["family"] == "Doe"

    @pytest.mark.asyncio
    async def test_update_family_preserves_given(self, nc_mcp: McpTestHelper) -> None:
        uid = await _put_vcard_with_name(nc_mcp, "upd-family", given="John", family="Doe")
        contact = json.loads(await nc_mcp.call("get_contact", uid=uid, book_id=BOOK_ID))
        updated = json.loads(
            await nc_mcp.call("update_contact", uid=uid, etag=contact["etag"], family_name="Smith", book_id=BOOK_ID)
        )
        assert updated["name"]["given"] == "John"
        assert updated["name"]["family"] == "Smith"

    @pytest.mark.asyncio
    async def test_update_both_names(self, nc_mcp: McpTestHelper) -> None:
        uid = await _put_vcard_with_name(nc_mcp, "upd-both", given="John", family="Doe")
        contact = json.loads(await nc_mcp.call("get_contact", uid=uid, book_id=BOOK_ID))
        updated = json.loads(
            await nc_mcp.call(
                "update_contact",
                uid=uid,
                etag=contact["etag"],
                given_name="Jane",
                family_name="Smith",
                book_id=BOOK_ID,
            )
        )
        assert updated["name"]["given"] == "Jane"
        assert updated["name"]["family"] == "Smith"

    @pytest.mark.asyncio
    async def test_update_given_auto_updates_fn(self, nc_mcp: McpTestHelper) -> None:
        uid = await _put_vcard_with_name(nc_mcp, "upd-autofn", given="John", family="Doe")
        contact = json.loads(await nc_mcp.call("get_contact", uid=uid, book_id=BOOK_ID))
        updated = json.loads(
            await nc_mcp.call("update_contact", uid=uid, etag=contact["etag"], given_name="Jane", book_id=BOOK_ID)
        )
        assert "Jane" in updated["full_name"]
        assert "Doe" in updated["full_name"]

    @pytest.mark.asyncio
    async def test_update_given_on_family_only_contact(self, nc_mcp: McpTestHelper) -> None:
        uid = await _put_vcard_with_name(nc_mcp, "upd-add-given", family="Doe")
        contact = json.loads(await nc_mcp.call("get_contact", uid=uid, book_id=BOOK_ID))
        updated = json.loads(
            await nc_mcp.call("update_contact", uid=uid, etag=contact["etag"], given_name="Jane", book_id=BOOK_ID)
        )
        assert updated["name"]["given"] == "Jane"
        assert updated["name"]["family"] == "Doe"

    @pytest.mark.asyncio
    async def test_update_family_on_given_only_contact(self, nc_mcp: McpTestHelper) -> None:
        uid = await _put_vcard_with_name(nc_mcp, "upd-add-family", given="John")
        contact = json.loads(await nc_mcp.call("get_contact", uid=uid, book_id=BOOK_ID))
        updated = json.loads(
            await nc_mcp.call("update_contact", uid=uid, etag=contact["etag"], family_name="Doe", book_id=BOOK_ID)
        )
        assert updated["name"]["given"] == "John"
        assert updated["name"]["family"] == "Doe"

    @pytest.mark.asyncio
    async def test_update_preserves_prefix_suffix(self, nc_mcp: McpTestHelper) -> None:
        uid = "mcp-name-upd-prefix"
        full_name = f"{PREFIX}-upd-prefix"
        lines = [
            "BEGIN:VCARD",
            "VERSION:3.0",
            f"UID:{uid}",
            f"FN:{full_name}",
            "N:Doe;John;William;Dr.;Jr.",
            "END:VCARD",
        ]
        vcard = "\r\n".join(lines) + "\r\n"
        config = get_config()
        await nc_mcp.client.dav_request(
            "PUT",
            f"addressbooks/users/{config.user}/{BOOK_ID}/{uid}.vcf",
            body=vcard,
            headers={"Content-Type": "text/vcard; charset=utf-8"},
            context=f"Create test contact '{uid}'",
        )
        contact = json.loads(await nc_mcp.call("get_contact", uid=uid, book_id=BOOK_ID))
        assert contact["name"]["prefix"] == "Dr."
        assert contact["name"]["suffix"] == "Jr."
        assert contact["name"]["additional"] == "William"
        updated = json.loads(
            await nc_mcp.call("update_contact", uid=uid, etag=contact["etag"], given_name="Jane", book_id=BOOK_ID)
        )
        assert updated["name"]["given"] == "Jane"
        assert updated["name"]["family"] == "Doe"
        assert updated["name"]["additional"] == "William"
        assert updated["name"]["prefix"] == "Dr."
        assert updated["name"]["suffix"] == "Jr."

    @pytest.mark.asyncio
    async def test_update_full_name_with_given(self, nc_mcp: McpTestHelper) -> None:
        uid = await _put_vcard_with_name(nc_mcp, "upd-fn-given", given="John", family="Doe")
        contact = json.loads(await nc_mcp.call("get_contact", uid=uid, book_id=BOOK_ID))
        updated = json.loads(
            await nc_mcp.call(
                "update_contact",
                uid=uid,
                etag=contact["etag"],
                full_name="Dr. Jane Smith",
                given_name="Jane",
                family_name="Smith",
                book_id=BOOK_ID,
            )
        )
        assert updated["full_name"] == "Dr. Jane Smith"
        assert updated["name"]["given"] == "Jane"
        assert updated["name"]["family"] == "Smith"

    @pytest.mark.asyncio
    async def test_update_name_preserves_other_fields(self, nc_mcp: McpTestHelper) -> None:
        uid = "mcp-name-upd-preserve"
        full_name = f"{PREFIX}-upd-preserve"
        lines = [
            "BEGIN:VCARD",
            "VERSION:3.0",
            f"UID:{uid}",
            f"FN:{full_name}",
            "N:Doe;John;;;",
            "EMAIL;TYPE=WORK:john@test.com",
            "ORG:Test Corp",
            "CATEGORIES:Work,VIP",
            "END:VCARD",
        ]
        vcard = "\r\n".join(lines) + "\r\n"
        config = get_config()
        await nc_mcp.client.dav_request(
            "PUT",
            f"addressbooks/users/{config.user}/{BOOK_ID}/{uid}.vcf",
            body=vcard,
            headers={"Content-Type": "text/vcard; charset=utf-8"},
            context=f"Create test contact '{uid}'",
        )
        contact = json.loads(await nc_mcp.call("get_contact", uid=uid, book_id=BOOK_ID))
        updated = json.loads(
            await nc_mcp.call("update_contact", uid=uid, etag=contact["etag"], given_name="Jane", book_id=BOOK_ID)
        )
        assert updated["name"]["given"] == "Jane"
        assert updated.get("organization") == "Test Corp"
        assert any(e["value"] == "john@test.com" for e in updated.get("emails", []))
        assert set(updated.get("categories", [])) == {"Work", "VIP"}


class TestDeleteContact:
    @pytest.mark.asyncio
    async def test_delete_removes_contact(self, nc_mcp: McpTestHelper) -> None:
        created = await _create(nc_mcp, "del-remove")
        result = await nc_mcp.call("delete_contact", uid=created["uid"], book_id=BOOK_ID)
        assert "deleted" in result.lower()
        contacts = json.loads(await nc_mcp.call("get_contacts", book_id=BOOK_ID, limit=200))
        uids = [c["uid"] for c in contacts["data"]]
        assert created["uid"] not in uids

    @pytest.mark.asyncio
    async def test_delete_nonexistent_raises(self, nc_mcp: McpTestHelper) -> None:
        with pytest.raises((ToolError, ValueError)):
            await nc_mcp.call("delete_contact", uid="nonexistent-uid-xyz", book_id=BOOK_ID)


class TestContactPermissions:
    @pytest.mark.asyncio
    async def test_read_only_allows_list_addressbooks(self, nc_mcp_read_only: McpTestHelper) -> None:
        result = await nc_mcp_read_only.call("list_addressbooks")
        assert isinstance(json.loads(result), list)

    @pytest.mark.asyncio
    async def test_read_only_allows_get_contacts(self, nc_mcp_read_only: McpTestHelper) -> None:
        result = await nc_mcp_read_only.call("get_contacts", book_id=BOOK_ID, limit=200)
        assert isinstance(json.loads(result)["data"], list)

    @pytest.mark.asyncio
    async def test_read_only_blocks_create(self, nc_mcp_read_only: McpTestHelper) -> None:
        with pytest.raises(ToolError, match=r"[Pp]ermission"):
            await nc_mcp_read_only.call("create_contact", full_name="blocked", book_id=BOOK_ID)

    @pytest.mark.asyncio
    async def test_read_only_blocks_delete(self, nc_mcp_read_only: McpTestHelper) -> None:
        with pytest.raises(ToolError, match=r"[Pp]ermission"):
            await nc_mcp_read_only.call("delete_contact", uid="any", book_id=BOOK_ID)

    @pytest.mark.asyncio
    async def test_write_allows_create(self, nc_mcp: McpTestHelper, nc_mcp_write: McpTestHelper) -> None:
        result = await nc_mcp_write.call("create_contact", full_name=f"{PREFIX}-write-ok", book_id=BOOK_ID)
        contact = json.loads(result)
        assert contact["uid"]
