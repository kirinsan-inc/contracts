#!/usr/bin/env python3
"""Validate the explicit public-document manifest and Markdown references."""
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
PARSER = MarkdownIt("commonmark", {"html": False}).enable("table")


def documents():
    entries = json.loads((ROOT / "print/documents.json").read_text(encoding="utf-8"))
    sources, outputs = set(), set()
    for entry in entries:
        source = entry["source"]
        output = entry["output"]
        if source in sources or output in outputs:
            raise ValueError("Duplicate source or output in print/documents.json")
        if Path(source).is_absolute() or ".." in Path(source).parts:
            raise ValueError(f"Source must be inside this repository: {source}")
        if Path(output).name != output or not output.endswith(".pdf"):
            raise ValueError(f"Invalid PDF filename: {output}")
        sources.add(source)
        outputs.add(output)
    return entries


def check():
    entries = documents()
    for entry in entries:
        fixed, alias = ROOT / entry["source"], ROOT / entry["alias"]
        if fixed.read_bytes() != alias.read_bytes():
            raise ValueError(f"Alias differs from fixed version: {entry['alias']}")
        if entry["version"] not in fixed.name:
            raise ValueError(f"Manifest version does not match filename: {fixed.name}")
    # Only public source folders: never inspect a user's local output directory.
    paths = [ROOT / name for name in ("README.md", "AGENTS.md", "CLAUDE.md")]
    paths += list((ROOT / "print").glob("*.md"))
    for folder in ("partner-agreement", "nda", "security-policy", "ai-guidelines"):
        paths.extend((ROOT / folder).glob("*.md"))
    count = 0
    for path in paths:
        if not path.exists():
            continue
        for token in PARSER.parse(path.read_text(encoding="utf-8")):
            for child in token.children or []:
                if child.type not in ("link_open", "image"):
                    continue
                url = child.attrGet("href") or child.attrGet("src") or ""
                parsed = urlsplit(url)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                target = (path.parent / unquote(parsed.path)).resolve()
                if not target.is_relative_to(ROOT):
                    raise ValueError(f"Relative link escapes repository: {path}: {url}")
                if not target.exists():
                    raise ValueError(f"Broken relative link: {path.relative_to(ROOT)}: {url}")
                count += 1
    print(f"OK: {len(entries)} fixed-version aliases; {count} relative links")
    return entries


if __name__ == "__main__":
    check()
