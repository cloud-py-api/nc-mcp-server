"""Configuration loaded from environment variables."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from .permissions import PermissionLevel


@dataclass(frozen=True)
class Config:
    """Server configuration from environment variables.

    Required:
        NEXTCLOUD_URL: Base URL of the Nextcloud instance (e.g. http://localhost:8080)
        NEXTCLOUD_USER: Username for authentication
        NEXTCLOUD_PASSWORD: App password for authentication

    Optional:
        NEXTCLOUD_MCP_PERMISSIONS: Permission level — 'read' (default), 'write', or 'destructive'
        NEXTCLOUD_MCP_HOST: Host to bind HTTP server (default: 0.0.0.0)
        NEXTCLOUD_MCP_PORT: Port for HTTP server (default: 8100)
        NEXTCLOUD_MCP_RETRY_MAX: Max retries on 429/503 (default: 3, 0 to disable)
        NEXTCLOUD_MCP_APP_PASSWORD: Set to 'true' when using an app password to skip session caching
        NEXTCLOUD_MCP_UPLOAD_ROOT: Absolute path to a local directory. When set, enables the
            upload_file_from_path tool, restricted to files under this directory (symlinks
            are resolved before the containment check). Unset by default — tool disabled.
    """

    nextcloud_url: str = field(default="")
    user: str = field(default="")
    password: str = field(default="")
    permission_level: PermissionLevel = field(default=PermissionLevel.READ)
    host: str = field(default="0.0.0.0")
    port: int = field(default=8100)
    retry_max: int = field(default=3)
    is_app_password: bool = field(default=False)
    upload_root: str = field(default="")

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        url = os.environ.get("NEXTCLOUD_URL", "").rstrip("/")
        user = os.environ.get("NEXTCLOUD_USER", "")
        password = os.environ.get("NEXTCLOUD_PASSWORD", "")

        perm_str = os.environ.get("NEXTCLOUD_MCP_PERMISSIONS", "read").lower()
        try:
            perm = PermissionLevel(perm_str)
        except ValueError:
            valid = ", ".join(p.value for p in PermissionLevel)
            raise ValueError(f"Invalid NEXTCLOUD_MCP_PERMISSIONS='{perm_str}'. Valid values: {valid}") from None

        host = os.environ.get("NEXTCLOUD_MCP_HOST", "0.0.0.0")
        port = int(os.environ.get("NEXTCLOUD_MCP_PORT", "8100"))
        retry_raw = os.environ.get("NEXTCLOUD_MCP_RETRY_MAX", "3")
        try:
            retry_max = int(retry_raw)
        except ValueError:
            raise ValueError(f"Invalid NEXTCLOUD_MCP_RETRY_MAX='{retry_raw}'. Expected integer >= 0.") from None

        app_pw_raw = os.environ.get("NEXTCLOUD_MCP_APP_PASSWORD", "").strip().lower()
        if app_pw_raw in ("", "false", "0", "no"):
            is_app_password = False
        elif app_pw_raw in ("true", "1", "yes"):
            is_app_password = True
        else:
            raise ValueError(f"Invalid NEXTCLOUD_MCP_APP_PASSWORD='{app_pw_raw}'. Expected: true/false, 1/0, yes/no.")

        upload_root_raw = os.environ.get("NEXTCLOUD_MCP_UPLOAD_ROOT", "").strip()
        if upload_root_raw:
            root = Path(upload_root_raw).expanduser()
            if not root.exists():
                raise ValueError(f"NEXTCLOUD_MCP_UPLOAD_ROOT='{upload_root_raw}' does not exist.")
            if not root.is_dir():
                raise ValueError(f"NEXTCLOUD_MCP_UPLOAD_ROOT='{upload_root_raw}' is not a directory.")
            upload_root = str(root.resolve(strict=True))
        else:
            upload_root = ""

        return cls(
            nextcloud_url=url,
            user=user,
            password=password,
            permission_level=perm,
            host=host,
            port=port,
            retry_max=max(0, retry_max),
            is_app_password=is_app_password,
            upload_root=upload_root,
        )

    def validate(self) -> None:
        """Raise ValueError if required config is missing."""
        missing: list[str] = []
        if not self.nextcloud_url:
            missing.append("NEXTCLOUD_URL")
        if not self.user:
            missing.append("NEXTCLOUD_USER")
        if not self.password:
            missing.append("NEXTCLOUD_PASSWORD")
        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}. "
                f"Set them before starting the MCP server."
            )
