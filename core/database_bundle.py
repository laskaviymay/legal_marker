from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path


REQUIRED_DATABASE_FILES: tuple[str, ...] = (
    "agents.json",
    "aliases.json",
    "forms.json",
    "sources.json",
)


def build_database_bundle(data_dir: Path, bundle_path: Path, version: str) -> dict[str, object]:
    data_dir = Path(data_dir)
    bundle_path = Path(bundle_path)
    bundle_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = {
        "version": version,
        "files": {
            name: _sha256(data_dir / name)
            for name in REQUIRED_DATABASE_FILES
        },
    }

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in REQUIRED_DATABASE_FILES:
            archive.write(data_dir / name, arcname=name)
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def extract_database_bundle(bundle_path: Path, out_dir: Path) -> dict[str, object]:
    bundle_path = Path(bundle_path)
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(bundle_path) as archive:
        archive.extractall(out_dir)

    manifest_path = out_dir / "manifest.json"
    if not manifest_path.exists():
        raise ValueError("Database bundle is missing manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name in REQUIRED_DATABASE_FILES:
        file_path = out_dir / name
        if not file_path.exists():
            raise ValueError(f"Database bundle is missing {name}")
    return manifest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
