from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from core.database_bundle import build_database_bundle
from core.importer import build_database, load_database
from core.marker import annotate_text


PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
DEFAULT_DESKTOP = Path.home() / "Desktop"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s: %(message)s")
    try:
        if args.export_db:
            version = args.db_version or _default_db_version()
            build_database_bundle(args.data_dir, args.export_db, version=version)
            print(f"Exported database bundle: {args.export_db}")
            if not args.text and not args.input and not args.update:
                return 0

        if args.update:
            entities = build_database(
                foreign_agents_path=args.foreign_agents,
                undesirable_path=args.undesirable,
                rosfinmonitoring_path=args.rosfinmonitoring,
                extremist_materials_path=args.extremist_materials,
                output_dir=args.data_dir,
            )
            print(f"Updated database: {len(entities)} entities")
            if not args.text and not args.input:
                return 0

        text = _read_input(args)
        entities = load_database(args.data_dir)
        result = annotate_text(text, entities)
        print(result.marked_text)
        if args.json:
            payload = {
                "matches": [
                    {
                        "entity": match.entity.to_dict(),
                        "start": match.start,
                        "end": match.end,
                        "text": match.text,
                        "confidence": match.confidence,
                        "match_type": match.match_type,
                    }
                    for match in result.matches
                ],
                "ambiguous_matches": [
                    {
                        "text": item.text,
                        "start": item.start,
                        "end": item.end,
                        "reason": item.reason,
                        "candidates": [candidate.to_dict() for candidate in item.candidates],
                    }
                    for item in result.ambiguous_matches
                ],
            }
            print("\nJSON")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        if args.verbose:
            logging.exception("Failed")
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mark legal-status entities in Russian newsroom text.")
    parser.add_argument("--text", help="Text to check.")
    parser.add_argument("--input", type=Path, help="UTF-8 text file to check.")
    parser.add_argument("--update", action="store_true", help="Rebuild JSON database from source files.")
    parser.add_argument("--export-db", type=Path, help="Export current JSON database as a zip bundle.")
    parser.add_argument("--db-version", help="Version string for exported database bundle.")
    parser.add_argument("--json", action="store_true", help="Print structured match metadata after marked text.")
    parser.add_argument("--verbose", action="store_true", help="Enable detailed logs.")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--foreign-agents", type=Path, default=DEFAULT_DESKTOP / "export.xlsx")
    parser.add_argument("--undesirable", type=Path, default=DEFAULT_DESKTOP / "export (1).xlsx")
    parser.add_argument("--rosfinmonitoring", type=Path, default=_find_rosfinmonitoring_source(DEFAULT_DESKTOP))
    parser.add_argument("--extremist-materials", type=Path, default=DEFAULT_DESKTOP / "exportfsm.docx")
    return parser


def _read_input(args: argparse.Namespace) -> str:
    if args.text:
        return args.text
    if args.input:
        return args.input.read_text(encoding="utf-8")
    raise ValueError("Provide --text or --input, or use --update only.")


def _find_rosfinmonitoring_docx(desktop: Path) -> Path:
    return _find_rosfinmonitoring_source(desktop)


def _find_rosfinmonitoring_source(desktop: Path) -> Path:
    priority = {".docx": 1, ".xlsx": 2, ".xls": 3}
    candidates = [
        path
        for path in desktop.iterdir()
        if path.suffix.lower() in priority
        and "росфинмониторинг" in path.name.lower()
        and not path.name.startswith("~$")
    ]
    if candidates:
        return max(candidates, key=lambda path: (priority[path.suffix.lower()], path.stat().st_mtime, path.stat().st_size))
    return desktop / "РОСФИНМОНИТОРИНГ Федеральная служба по финансовому мониторингу.docx"


def _default_db_version() -> str:
    return datetime.now().strftime("local-%Y%m%d%H%M%S")


if __name__ == "__main__":
    raise SystemExit(main())
