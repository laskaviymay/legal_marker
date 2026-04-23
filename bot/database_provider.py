from __future__ import annotations

import json
import shutil
from pathlib import Path
from urllib.request import Request, urlopen

from bot.config import BotConfig
from core.database_bundle import REQUIRED_DATABASE_FILES, extract_database_bundle


class DatabaseProvider:
    def __init__(
        self,
        config: BotConfig,
        download_bytes=None,
    ) -> None:
        self.config = config
        self._download_bytes = download_bytes or _download_bytes

    @property
    def current_dir(self) -> Path:
        return self.config.db_dir / "current"

    @property
    def previous_dir(self) -> Path:
        return self.config.db_dir / "previous"

    @property
    def downloads_dir(self) -> Path:
        return self.config.db_dir / "downloads"

    def ensure_ready(self) -> Path:
        for candidate in (self.current_dir, self.config.db_dir):
            if _looks_like_database_dir(candidate):
                return candidate
        if self.config.db_url:
            return self.update_from_remote()
        raise FileNotFoundError(f"Database directory is not ready: {self.config.db_dir}")

    def update_from_remote(self) -> Path:
        if not self.config.db_url:
            raise ValueError("LEGAL_MARKER_DB_URL is not configured")

        self.config.db_dir.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        bundle_bytes = self._download_bytes(
            self.config.db_url,
            headers=_request_headers(self.config.github_token),
        )
        bundle_path = self.downloads_dir / "legal-marker-db.zip"
        bundle_path.write_bytes(bundle_bytes)

        incoming_dir = self.config.db_dir / "incoming"
        extract_database_bundle(bundle_path, incoming_dir)

        if self.previous_dir.exists():
            shutil.rmtree(self.previous_dir, ignore_errors=True)
        if self.current_dir.exists():
            shutil.move(str(self.current_dir), str(self.previous_dir))
        shutil.move(str(incoming_dir), str(self.current_dir))
        return self.current_dir

    def current_version(self) -> str:
        manifest = self.manifest()
        return str(manifest.get("version", "unknown"))

    def manifest(self) -> dict[str, object]:
        active_dir = self.ensure_ready()
        manifest_path = active_dir / "manifest.json"
        if not manifest_path.exists():
            return {"version": "unversioned"}
        return json.loads(manifest_path.read_text(encoding="utf-8"))


def _looks_like_database_dir(path: Path) -> bool:
    return path.exists() and all((path / name).exists() for name in REQUIRED_DATABASE_FILES)


def _request_headers(github_token: str | None) -> dict[str, str]:
    headers = {
        "User-Agent": "LegalMarkerBot/1.0",
        "Accept": "application/octet-stream",
    }
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    return headers


def _download_bytes(url: str, headers: dict[str, str] | None = None, timeout: int = 60) -> bytes:
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=timeout) as response:
        return response.read()
