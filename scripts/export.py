"""Export logique et archive reproductible sans secrets ni métadonnées Git."""
import argparse
import json
from pathlib import Path
import sys
import zipfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.config import Settings
from backend.app.store import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--code-only", action="store_true")
    args = parser.parse_args()
    output = ROOT/"output"
    output.mkdir(exist_ok=True)
    if not args.code_only:
        store = Store(Settings.load().database_url)
        with (output/"history.jsonl").open("w", encoding="utf-8") as target:
            for table in ("measurements", "alerts", "commands"):
                offset = 0
                while True:
                    rows = store.list_rows(table, 1000, offset)
                    for row in rows:
                        target.write(json.dumps({"table": table, "data": row}, ensure_ascii=False)+"\n")
                    if len(rows) < 1000:
                        break
                    offset += 1000
        store.engine.dispose()
    excluded = {".git", ".agents", ".codex", "secrets", "data", "output", "tmp", "node_modules", "__pycache__", ".pytest_cache"}
    def include(path):
        return not any(p in excluded or p.startswith(".venv") for p in path.parts) and path.suffix not in (".pyc", ".log", ".tsbuildinfo")
    with zipfile.ZipFile(output/"sentinel-x-code.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        # Prune excluded directories before traversal, including .git.
        import os
        for parent, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in excluded and not d.startswith(".venv")]
            for name in files:
                path = Path(parent)/name
                relative = path.relative_to(ROOT)
                if include(relative):
                    archive.write(path, relative.as_posix())
    print("Archive dans output/sentinel-x-code.zip ; secrets exclus.")


if __name__ == "__main__":
    main()
