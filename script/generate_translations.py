#!/usr/bin/env python3
"""Resolve strings.json into translations/en.json.

Home Assistant core resolves ``[%key:...%]`` references when it builds the
English translation, and tests load the built file rather than strings.json.
A custom component has no such build step, so this script does the same thing
against the core strings shipped in the virtualenv.
"""

import json
from pathlib import Path
import re
import sys

import homeassistant

REFERENCE = re.compile(r"^\[%key:(.+)%\]$")

REPO = Path(__file__).resolve().parent.parent
STRINGS = REPO / "custom_components" / "fglair_local" / "strings.json"
TRANSLATION = REPO / "custom_components" / "fglair_local" / "translations" / "en.json"
CORE = Path(homeassistant.__file__).parent


def load(path: Path) -> dict:
    """Read a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def lookup(data: dict, parts: list[str]) -> str:
    """Walk a dotted path into nested dicts."""
    for part in parts:
        data = data[part]
    if not isinstance(data, str):
        raise TypeError(f"{'::'.join(parts)} is not a string")
    return data


def dereference(key: str, own: dict) -> str:
    """Return the text a ``[%key:...%]`` reference points at."""
    parts = key.split("::")
    match parts:
        case ["common", *rest]:
            return lookup(load(CORE / "strings.json")["common"], rest)
        case ["component", domain, *rest]:
            return lookup(load(CORE / "components" / domain / "strings.json"), rest)
        case _:
            return lookup(own, parts)


def resolve(value: object, own: dict) -> object:
    """Replace every reference in a strings.json tree with its text."""
    match value:
        case dict():
            return {key: resolve(item, own) for key, item in value.items()}
        case str() if match := REFERENCE.match(value):
            return dereference(match.group(1), own)
        case _:
            return value


def main() -> int:
    """Write the resolved English translation."""
    strings = load(STRINGS)
    resolved = resolve(strings, strings)
    TRANSLATION.write_text(
        json.dumps(resolved, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {TRANSLATION.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
