"""Merge flat translation batches into a locale file, shaped like en.json.

WHY A BUILDER RATHER THAN HAND-EDITED JSON
------------------------------------------
Seven languages times 662 keys is 4,634 strings. Hand-maintaining that nesting
five more times guarantees a key lands in the wrong block, and a key in the
wrong block does not error — it renders the key path on screen in the middle of
a sentence, in a language nobody on the team reads.

So translations arrive as flat dot-paths and this rebuilds the tree from
en.json, which stays the single source of truth for the SHAPE. A path that does
not exist in en.json is rejected rather than silently creating a new branch.

Usage:
    python scripts/build_locale.py mr batch.json      # merge a batch
    python scripts/build_locale.py --status           # what is still missing
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

I18N = Path(__file__).resolve().parents[1] / "apps" / "web" / "src" / "i18n"
LOCALES = ["hi", "mr", "bn", "gu", "ta", "te"]


def flatten(node: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(flatten(value, path))
        else:
            out[path] = value
    return out


def unflatten(flat: dict[str, str]) -> dict:
    tree: dict = {}
    for path, value in flat.items():
        node = tree
        parts = path.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return tree


def load(name: str) -> dict:
    path = I18N / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def merge(locale: str, batch: dict[str, str]) -> tuple[int, list[str]]:
    english = flatten(load("en"))
    current = flatten(load(locale))

    unknown = [key for key in batch if key not in english]
    current.update({k: v for k, v in batch.items() if k in english})

    # Written in en.json's key order so the files diff cleanly against each
    # other and a reviewer can read them side by side.
    ordered = {key: current[key] for key in english if key in current}
    path = I18N / f"{locale}.json"
    path.write_text(
        json.dumps(unflatten(ordered), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return len(ordered), unknown


def status() -> int:
    english = flatten(load("en"))
    print(f"en.json: {len(english)} keys\n")
    incomplete = 0
    for locale in LOCALES:
        have = flatten(load(locale))
        missing = [key for key in english if key not in have]
        mark = "OK " if not missing else "   "
        print(f"  {mark}{locale}: {len(have)}/{len(english)}", end="")
        if missing:
            incomplete += 1
            blocks = sorted({key.split('.')[0] for key in missing})
            print(f"  missing {len(missing)} in: {', '.join(blocks[:8])}")
        else:
            print()
    return incomplete


def main() -> int:
    if "--status" in sys.argv:
        return 0 if status() == 0 else 1

    if len(sys.argv) < 3:
        print(__doc__)
        return 1

    locale, batch_path = sys.argv[1], sys.argv[2]
    batch = json.loads(Path(batch_path).read_text(encoding="utf-8"))
    total, unknown = merge(locale, batch)
    print(f"{locale}: {total} keys after merge")
    if unknown:
        # Loudly. A typo'd path would otherwise be silently dropped and the
        # string would stay English with nobody noticing which one.
        print(f"  REJECTED {len(unknown)} unknown paths: {unknown[:5]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
