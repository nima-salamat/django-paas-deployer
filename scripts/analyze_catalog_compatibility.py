from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app_catalog.compatibility import analyze_directory, summarize, write_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Statically analyze a Compose/catalog tree against PassDeployer's catalog capabilities.")
    parser.add_argument("source_dir", type=Path, help="Root directory containing YAML/Compose templates")
    parser.add_argument("--json", dest="json_path", type=Path, help="Write machine-readable JSON report")
    parser.add_argument("--fail-on-unsupported", action="store_true", help="Exit non-zero when any template is unsupported or invalid")
    args = parser.parse_args()
    root = args.source_dir.resolve()
    if not root.is_dir():
        parser.error(f"source directory does not exist: {root}")
    results = analyze_directory(root)
    summary = summarize(results)
    print(json.dumps(summary, indent=2))
    if args.json_path:
        write_report(results, args.json_path.resolve(), source_root=root)
    if args.fail_on_unsupported and any(item.classification in {"UNSUPPORTED", "INVALID"} for item in results):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
