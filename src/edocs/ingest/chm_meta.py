"""
CHM #SYSTEM metadata parser.

Parses the binary #SYSTEM file from a CHM archive to extract:
- contents_file: the .hhc table of contents filename
- index_file: the .hhk keyword index filename
- default_topic: the default HTML page
- title: the CHM title
"""

from __future__ import annotations

import glob
import struct
from pathlib import Path
from typing import Optional


SYSTEM_CODES = {0: "contents_file", 1: "index_file", 2: "default_topic", 3: "title"}


def parse_system(data: bytes) -> dict[str, str]:
    """Parse the binary #SYSTEM file and return a dict of metadata fields."""
    out: dict[str, str] = {}
    pos = 4  # skip 4-byte version
    while pos + 4 <= len(data):
        code, length = struct.unpack_from("<HH", data, pos)
        pos += 4
        chunk = data[pos : pos + length]
        pos += length
        if code in SYSTEM_CODES:
            out[SYSTEM_CODES[code]] = chunk.split(b"\x00", 1)[0].decode(
                "cp1252", "replace"
            )
    return out


def load_system_from_dir(extracted_dir: Path) -> dict[str, str]:
    """
    Load #SYSTEM metadata from an extracted CHM directory.

    Falls back to globbing for .hhc/.hhk if #SYSTEM is missing.
    """
    system_path = extracted_dir / "#SYSTEM"
    meta: dict[str, str] = {}

    if system_path.exists():
        meta = parse_system(system_path.read_bytes())

    # Fallback: glob for .hhc and .hhk if not found in #SYSTEM
    if "contents_file" not in meta:
        hhc_files = list(extracted_dir.rglob("*.hhc"))
        if hhc_files:
            meta["contents_file"] = str(hhc_files[0].relative_to(extracted_dir))

    if "index_file" not in meta:
        hhk_files = list(extracted_dir.rglob("*.hhk"))
        if hhk_files:
            meta["index_file"] = str(hhk_files[0].relative_to(extracted_dir))

    if "default_topic" not in meta:
        # Try common defaults
        for name in ["index.htm", "index.html", "default.htm", "default.html"]:
            candidates = list(extracted_dir.rglob(name))
            if candidates:
                meta["default_topic"] = str(
                    candidates[0].relative_to(extracted_dir)
                )
                break

    return meta
