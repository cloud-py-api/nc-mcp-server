"""File management tools — list, read, upload, delete, move, search files via WebDAV."""

import contextlib
import json
import xml.etree.ElementTree as ET
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..permissions import PermissionLevel, require_permission
from ..state import get_client, get_config

DAV_NS = "DAV:"
OC_NS = "http://owncloud.org/ns"


def _build_search_xml(user: str, query: str, path: str, limit: int, offset: int, mimetype: str) -> str:
    """Build a WebDAV SEARCH request body."""
    where_parts: list[str] = []
    if query:
        where_parts.append(f"<d:like><d:prop><d:displayname/></d:prop><d:literal>%{query}%</d:literal></d:like>")
    if mimetype:
        mime_pattern = mimetype if "%" in mimetype or "/" in mimetype else f"{mimetype}/%"
        where_parts.append(
            f"<d:like><d:prop><d:getcontenttype/></d:prop><d:literal>{mime_pattern}</d:literal></d:like>"
        )
    if not where_parts:
        where_clause = "<d:gt><d:prop><oc:fileid/></d:prop><d:literal>0</d:literal></d:gt>"
    elif len(where_parts) == 1:
        where_clause = where_parts[0]
    else:
        where_clause = "<d:and>" + "".join(where_parts) + "</d:and>"
    scope = f"/files/{user}/{path.strip('/')}" if path.strip("/") else f"/files/{user}"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<d:searchrequest xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">'
        "<d:basicsearch>"
        "<d:select><d:prop>"
        "<d:displayname/><d:getlastmodified/><d:getcontenttype/>"
        "<d:getcontentlength/><d:resourcetype/><oc:fileid/><oc:size/>"
        "</d:prop></d:select>"
        f"<d:from><d:scope><d:href>{scope}</d:href>"
        "<d:depth>infinity</d:depth></d:scope></d:from>"
        f"<d:where>{where_clause}</d:where>"
        "<d:orderby><d:order><d:prop><d:getlastmodified/></d:prop>"
        "<d:descending/></d:order></d:orderby>"
        f"<d:limit><d:nresults>{limit}</d:nresults>"
        f"<d:firstresult>{offset}</d:firstresult></d:limit>"
        "</d:basicsearch></d:searchrequest>"
    )


def _parse_search_results(xml_text: str, user: str) -> list[dict[str, Any]]:
    """Parse a SEARCH response into a list of file dicts."""
    root = ET.fromstring(xml_text)  # noqa: S314
    entries: list[dict[str, Any]] = []
    dav_prefix = f"/remote.php/dav/files/{user}/"
    for response in root.findall(f"{{{DAV_NS}}}response"):
        href_el = response.find(f"{{{DAV_NS}}}href")
        if href_el is None or href_el.text is None:
            continue
        href = href_el.text
        path = (href.split(dav_prefix, 1)[1] if dav_prefix in href else href).rstrip("/")
        propstat = response.find(f"{{{DAV_NS}}}propstat")
        if propstat is None:
            continue
        prop = propstat.find(f"{{{DAV_NS}}}prop")
        if prop is None:
            continue
        resource_type = prop.find(f"{{{DAV_NS}}}resourcetype")
        is_dir = resource_type is not None and resource_type.find(f"{{{DAV_NS}}}collection") is not None
        entry: dict[str, Any] = {"path": path or "/", "is_directory": is_dir}
        for tag, key in [
            (f"{{{DAV_NS}}}getlastmodified", "last_modified"),
            (f"{{{DAV_NS}}}getcontenttype", "content_type"),
            (f"{{{DAV_NS}}}getcontentlength", "size"),
            (f"{{{OC_NS}}}fileid", "file_id"),
            (f"{{{OC_NS}}}size", "total_size"),
        ]:
            el = prop.find(tag)
            if el is not None and el.text:
                entry[key] = el.text
        for size_key in ("size", "total_size"):
            if size_key in entry:
                with contextlib.suppress(ValueError, TypeError):
                    entry[size_key] = int(entry[size_key])
        entries.append(entry)
    return entries


def _register_read_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @require_permission(PermissionLevel.READ)
    async def list_directory(path: str = "/") -> str:
        """List files and folders in a Nextcloud directory.

        Args:
            path: Directory path relative to user's root (default: "/" for root).
                  Example: "Documents", "Photos/Vacation"

        Returns:
            JSON list of entries, each with: path, is_directory, size, last_modified, content_type.
        """
        client = get_client()
        entries = await client.dav_propfind(path, depth=1)
        # First entry is the directory itself — skip it
        if entries and entries[0]["path"].rstrip("/") == path.strip("/"):
            entries = entries[1:]
        return json.dumps(entries, indent=2, default=str)

    @mcp.tool()
    @require_permission(PermissionLevel.READ)
    async def get_file(path: str) -> str:
        """Read a file's content from Nextcloud.

        Best for text files (txt, md, json, csv, xml, etc.).
        For binary files, returns a message with the file size instead.

        Args:
            path: File path relative to user's root. Example: "Documents/notes.md"

        Returns:
            The file content as text, or a description for binary files.
        """
        client = get_client()
        content = await client.dav_get(path)
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return f"[Binary file, {len(content)} bytes. Use download tools for binary content.]"

    @mcp.tool()
    @require_permission(PermissionLevel.READ)
    async def search_files(
        query: str = "",
        path: str = "/",
        mimetype: str = "",
        limit: int = 20,
        offset: int = 0,
    ) -> str:
        """Search for files in Nextcloud by name and/or MIME type.

        Searches recursively through all subdirectories of the given path.
        Results are sorted by last modified date (newest first).

        At least one of query or mimetype must be provided.

        Args:
            query: Filename search pattern. Matches anywhere in the filename.
                   Example: "report" matches "quarterly-report.pdf", "report-2026.docx".
            path: Directory to search in (default: "/" for entire user folder).
                  Example: "Documents" to only search in Documents.
            mimetype: Filter by MIME type prefix. Example: "image" for all images,
                      "application/pdf" for PDFs, "text" for all text files.
            limit: Maximum number of results (1-100, default: 20).
            offset: Number of results to skip for pagination (default: 0).

        Returns:
            JSON list of matching files with: path, is_directory, file_id, size,
            last_modified, content_type. Includes pagination info.
        """
        if not query and not mimetype:
            raise ValueError("At least one of 'query' or 'mimetype' must be provided.")
        limit = max(1, min(100, limit))
        config = get_config()
        client = get_client()
        body = _build_search_xml(config.user, query, path, limit, offset, mimetype)
        response = await client.dav_request(
            "SEARCH",
            "",
            body=body,
            headers={"Content-Type": "text/xml; charset=utf-8"},
            context=f"Search files: query={query!r} mimetype={mimetype!r}",
        )
        results = _parse_search_results(response.text or "", config.user)
        result = json.dumps(results, indent=2, default=str)
        if results:
            next_offset = offset + len(results)
            result += f"\n\n--- {len(results)} results (offset={offset}). Next page: offset={next_offset} ---"
        return result


def _register_write_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @require_permission(PermissionLevel.WRITE)
    async def upload_file(path: str, content: str) -> str:
        """Upload or overwrite a text file in Nextcloud.

        Creates the file if it doesn't exist. Overwrites if it does.

        Args:
            path: Destination path relative to user's root. Example: "Documents/report.md"
            content: Text content to write to the file.

        Returns:
            Confirmation message.
        """
        client = get_client()
        await client.dav_put(path, content.encode("utf-8"), content_type="text/plain; charset=utf-8")
        return f"File uploaded successfully: {path}"

    @mcp.tool()
    @require_permission(PermissionLevel.WRITE)
    async def create_directory(path: str) -> str:
        """Create a new directory in Nextcloud.

        Args:
            path: Directory path to create. Example: "Documents/Projects/NewProject"

        Returns:
            Confirmation message.
        """
        client = get_client()
        await client.dav_mkcol(path)
        return f"Directory created: {path}"


def _register_destructive_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @require_permission(PermissionLevel.DESTRUCTIVE)
    async def delete_file(path: str) -> str:
        """Delete a file or directory from Nextcloud.

        WARNING: This permanently deletes the file/directory (moves to trash if enabled).

        Args:
            path: Path to delete. Example: "Documents/old-file.txt"

        Returns:
            Confirmation message.
        """
        client = get_client()
        await client.dav_delete(path)
        return f"Deleted: {path}"

    @mcp.tool()
    @require_permission(PermissionLevel.DESTRUCTIVE)
    async def move_file(source: str, destination: str) -> str:
        """Move or rename a file/directory in Nextcloud.

        Args:
            source: Current path. Example: "Documents/old-name.txt"
            destination: New path. Example: "Documents/new-name.txt"

        Returns:
            Confirmation message.
        """
        client = get_client()
        await client.dav_move(source, destination)
        return f"Moved: {source} → {destination}"


def register(mcp: FastMCP) -> None:
    """Register file tools with the MCP server."""
    _register_read_tools(mcp)
    _register_write_tools(mcp)
    _register_destructive_tools(mcp)
