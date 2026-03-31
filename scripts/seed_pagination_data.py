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

    for i in range(1, COUNT + 1):
        s.post(
            f"{url}/remote.php/dav/comments/files/{file_id}",
            json={"actorType": "users", "verb": "comment", "message": f"Pagination test comment {i:03d}"},
            headers={"Content-Type": "application/json"},
        )
    print(f"  {COUNT} comments on file {file_id}")


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

    print("Comments...")
    seed_comments(s, url, user)

    print("=== Seed complete ===")
    s.close()


if __name__ == "__main__":
    main()
