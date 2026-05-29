#!/usr/bin/env python3
"""Seed synthetic data for pagination integration tests.

Creates bulk test data across multiple Nextcloud apps to verify
pagination behavior with limit/offset parameters.

Usage: python scripts/seed_pagination_data.py <NC_URL> <USER> <PASSWORD>

Seeded data uses the "mcp-pagtest" prefix and lives outside the
regular test cleanup path (mcp-test-suite), so it persists across
individual test runs but is ephemeral in CI (container destroyed).
"""

import sys
import time
import xml.etree.ElementTree as ET

import niquests

COUNT = 55
PREFIX = "mcp-pagtest"
PAGINATION_DIR = "mcp-pagination-data"


def _ocs_data(resp: niquests.Response) -> object:
    """Extract data from an OCS JSON response."""
    return resp.json()["ocs"]["data"]


def seed_files(s: niquests.Session, url: str, user: str) -> None:
    """Create files in a dedicated pagination test directory."""
    dav = f"{url}/remote.php/dav/files/{user}"
    s.request("MKCOL", f"{dav}/{PAGINATION_DIR}/")
    for i in range(1, COUNT + 1):
        s.put(
            f"{dav}/{PAGINATION_DIR}/pagtest-{i:03d}.txt",
            data=f"Pagination test file {i:03d}",
            headers={"Content-Type": "text/plain"},
        )
    print(f"  {COUNT} files in {PAGINATION_DIR}/")


def seed_conversations(s: niquests.Session, url: str) -> None:
    """Create Talk group conversations."""
    api = f"{url}/ocs/v2.php/apps/spreed/api/v4/room"
    existing = {r["name"] for r in _ocs_data(s.get(api))}
    created = 0
    for i in range(1, COUNT + 1):
        name = f"{PREFIX}-conv-{i:03d}"
        if name not in existing:
            s.post(api, json={"roomType": 2, "roomName": name})
            created += 1
    print(f"  {created} conversations (skipped {COUNT - created})")


def seed_calendar_events(s: niquests.Session, url: str, user: str) -> None:
    """Create calendar events via CalDAV PUT."""
    cal = f"{url}/remote.php/dav/calendars/{user}/personal"
    for i in range(1, COUNT + 1):
        uid = f"{PREFIX}-event-{i:03d}"
        hour = i % 24
        ical = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//NC MCP//Pagination Test//EN\r\n"
            "BEGIN:VEVENT\r\n"
            f"UID:{uid}\r\n"
            f"SUMMARY:Pagination Test Event {i:03d}\r\n"
            f"DTSTART:20270601T{hour:02d}0000Z\r\n"
            f"DTEND:20270601T{hour:02d}3000Z\r\n"
            f"DESCRIPTION:Seeded event {i:03d} for pagination testing\r\n"
            "DTSTAMP:20270101T000000Z\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        s.put(f"{cal}/{uid}.ics", data=ical, headers={"Content-Type": "text/calendar; charset=utf-8"})
    print(f"  {COUNT} calendar events")


def seed_trash(s: niquests.Session, url: str, user: str) -> None:
    """Create files then delete them to populate the trash bin."""
    dav = f"{url}/remote.php/dav/files/{user}"
    trash_dir = f"{PREFIX}-trash"
    s.request("MKCOL", f"{dav}/{trash_dir}/")
    for i in range(1, COUNT + 1):
        path = f"{dav}/{trash_dir}/trash-{i:03d}.txt"
        s.put(path, data=f"Trash item {i:03d}", headers={"Content-Type": "text/plain"})
    for i in range(1, COUNT + 1):
        s.delete(f"{dav}/{trash_dir}/trash-{i:03d}.txt")
    s.delete(f"{dav}/{trash_dir}/")
    print(f"  {COUNT} items in trash")


def seed_collective_pages(s: niquests.Session, url: str) -> None:
    """Create a collective with many pages for pagination testing."""
    api = f"{url}/ocs/v2.php/apps/collectives/api/v1.0"
    coll_name = f"{PREFIX}-collective"

    collectives = _ocs_data(s.get(f"{api}/collectives"))
    coll = next((c for c in collectives["collectives"] if c["name"] == coll_name), None)
    if not coll:
        resp = s.post(
            f"{api}/collectives",
            json={"name": coll_name},
            headers={"Content-Type": "application/json"},
        )
        coll = _ocs_data(resp)["collective"]
    coll_id = coll["id"]

    pages_data = _ocs_data(s.get(f"{api}/collectives/{coll_id}/pages"))
    pages = pages_data["pages"]
    landing_id = pages[0]["id"]
    existing_titles = {p["title"] for p in pages}

    created = 0
    for i in range(1, COUNT + 1):
        title = f"pagtest-page-{i:03d}"
        if title not in existing_titles:
            s.post(
                f"{api}/collectives/{coll_id}/pages/{landing_id}",
                json={"title": title},
                headers={"Content-Type": "application/json"},
            )
            created += 1
    # total = created + existing (minus landing page)
    print(f"  {created} pages in collective '{coll_name}' (skipped {COUNT - created})")


_GIVEN_NAMES = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Hank", "Iris", "Jack"]
_FAMILY_NAMES = ["Smith", "Jones", "Brown", "Davis", "Wilson", "Taylor", "Clark", "Lewis", "Hall", "Young"]


def seed_contacts(s: niquests.Session, url: str, user: str) -> None:
    """Create contacts with categories and varied name structures via CardDAV PUT."""
    dav = f"{url}/remote.php/dav/addressbooks/users/{user}/contacts"
    for i in range(1, COUNT + 1):
        uid = f"{PREFIX}-contact-{i:03d}"
        given = _GIVEN_NAMES[(i - 1) % len(_GIVEN_NAMES)]
        family = _FAMILY_NAMES[(i - 1) % len(_FAMILY_NAMES)]
        cats: list[str] = []
        if i % 2 == 0:
            cats.append("Work")
        if i % 3 == 0:
            cats.append("Family")
        if i % 5 == 0:
            cats.append("VIP")
        if not cats:
            cats.append("Friend")
        lines = ["BEGIN:VCARD", "VERSION:3.0", f"UID:{uid}"]
        remainder = i % 4
        if remainder == 1:
            lines.append(f"FN:{given} {family}")
            lines.append(f"N:{family};{given};;;")
        elif remainder == 2:
            lines.append(f"FN:{given}")
            lines.append(f"N:;{given};;;")
        elif remainder == 3:
            lines.append(f"FN:{family}")
            lines.append(f"N:{family};;;;")
        else:
            lines.append(f"FN:{given} {family}")
            lines.append(f"N:{family};{given};;;")
        lines.extend(
            [
                f"EMAIL;TYPE=WORK:pagtest{i:03d}@example.com",
                f"ORG:PagTest Corp {i:03d}",
                f"CATEGORIES:{','.join(cats)}",
                "END:VCARD",
            ]
        )
        vcard = "\r\n".join(lines) + "\r\n"
        s.put(f"{dav}/{uid}.vcf", data=vcard, headers={"Content-Type": "text/vcard; charset=utf-8"})
    print(f"  {COUNT} contacts with categories and varied name structures")


def _fetch_all_comments(s: niquests.Session, url: str, file_id: str) -> list[tuple[str, str, str]]:
    """Return all comments on file_id as list of (id, message, creation_ts)."""
    out: list[tuple[str, str, str]] = []
    offset = 0
    while True:
        report = s.request(
            "REPORT",
            f"{url}/remote.php/dav/comments/files/{file_id}",
            data=(
                '<?xml version="1.0" encoding="utf-8"?>'
                '<oc:filter-comments xmlns:oc="http://owncloud.org/ns">'
                f"<oc:limit>100</oc:limit><oc:offset>{offset}</oc:offset>"
                "</oc:filter-comments>"
            ),
            headers={"Content-Type": "application/xml"},
        )
        batch: list[tuple[str, str, str]] = []
        for resp_el in ET.fromstring(report.text).findall("{DAV:}response"):
            href = resp_el.find("{DAV:}href")
            msg_el = resp_el.find(".//{http://owncloud.org/ns}message")
            ts_el = resp_el.find(".//{http://owncloud.org/ns}creationDateTime")
            if href is not None and msg_el is not None and msg_el.text and ts_el is not None:
                cid = href.text.rstrip("/").split("/")[-1]
                batch.append((cid, msg_el.text, ts_el.text or ""))
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
        offset += 100
    return out


def seed_comments(s: niquests.Session, url: str, user: str) -> None:
    """Create a dedicated file and add many comments to it."""
    dav = f"{url}/remote.php/dav/files/{user}"
    comment_file = f"{PAGINATION_DIR}/comment-target.txt"
    s.put(f"{dav}/{comment_file}", data="File with many comments", headers={"Content-Type": "text/plain"})

    resp = s.request(
        "PROPFIND",
        f"{dav}/{comment_file}",
        data=(
            '<?xml version="1.0"?>'
            '<d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">'
            "<d:prop><oc:fileid/></d:prop>"
            "</d:propfind>"
        ),
        headers={"Content-Type": "text/xml", "Depth": "0"},
    )
    root = ET.fromstring(resp.text)
    fileid_el = root.find(".//{http://owncloud.org/ns}fileid")
    if fileid_el is None or not fileid_el.text:
        print("  WARNING: could not resolve file ID for comments, skipping")
        return
    file_id = fileid_el.text

    expected = {f"Pagination test comment {i:03d}" for i in range(1, COUNT + 1)}
    existing = _fetch_all_comments(s, url, file_id)
    expected_ts = [ts for _, msg, ts in existing if msg in expected]
    if expected.issubset({m for _, m, _ in existing}) and len(set(expected_ts)) >= COUNT:
        print(f"  {COUNT} comments on file {file_id} (already present with distinct timestamps)")
        return

    for cid, _, _ in existing:
        s.delete(f"{url}/remote.php/dav/comments/files/{file_id}/{cid}")

    for i in range(1, COUNT + 1):
        s.post(
            f"{url}/remote.php/dav/comments/files/{file_id}",
            json={"actorType": "users", "verb": "comment", "message": f"Pagination test comment {i:03d}"},
            headers={"Content-Type": "application/json"},
        )
        if i < COUNT:
            time.sleep(1.05)
    print(f"  {COUNT} comments on file {file_id} (reset and re-created with 1.05s spacing for stable pagination)")


def main() -> None:
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <NC_URL> <USER> <PASSWORD>")
        sys.exit(1)

    url = sys.argv[1].rstrip("/")
    user = sys.argv[2]
    password = sys.argv[3]

    s = niquests.Session()
    s.auth = (user, password)
    s.headers.update({"OCS-APIRequest": "true", "Accept": "application/json"})

    print(f"=== Seeding pagination test data ({COUNT} items per app) ===")

    print("Files...")
    seed_files(s, url, user)

    print("Talk conversations...")
    seed_conversations(s, url)

    print("Calendar events...")
    seed_calendar_events(s, url, user)

    print("Trash items...")
    seed_trash(s, url, user)

    print("Collective pages...")
    seed_collective_pages(s, url)

    print("Contacts...")
    seed_contacts(s, url, user)

    print("Comments...")
    seed_comments(s, url, user)

    print("=== Seed complete ===")
    s.close()


if __name__ == "__main__":
    main()
