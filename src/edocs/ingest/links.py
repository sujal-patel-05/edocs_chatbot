"""
Link normalisation module for CHM HTML pages.

Resolves relative links, parent traversals (..), backslashes, URL encoding,
same-page anchors, and cross-CHM prefixes (ms-its:, mk:@MSITStore:, its:).
"""

from __future__ import annotations

import re
from urllib.parse import unquote

_ITS = re.compile(
    r"^(?:mk:@MSITStore:|ms-its:|its:)(?P<chm>.+?\.chm)::(?P<path>/.*)$",
    re.IGNORECASE,
)


def normalize_link(
    href: str, current_chm: str, current_dir: str
) -> tuple[str, str, str] | None:
    """
    Normalize an href link within the CHM corpus.

    Returns:
        (chm_stem, page_path, anchor)
        - page_path == "" means same-page anchor
        - None means external (http, https, mailto, javascript)
    """
    href = unquote(href.strip())
    if not href or href.lower().startswith(
        ("http:", "https:", "mailto:", "javascript:", "tel:")
    ):
        return None

    m = _ITS.match(href)
    if m:
        chm = (
            m["chm"]
            .replace("\\", "/")
            .split("/")[-1]
            .lower()
            .removesuffix(".chm")
        )
        path, _, anchor = m["path"].lstrip("/").partition("#")
        return chm, path.lower(), anchor

    path, _, anchor = href.partition("#")
    if not path:
        return current_chm, "", anchor

    parts = (
        (current_dir.split("/") if current_dir else [])
        + path.replace("\\", "/").split("/")
    )
    stack: list[str] = []
    for p in parts:
        if p in ("", "."):
            continue
        if p == "..":
            if stack:
                stack.pop()
        else:
            stack.append(p)

    return current_chm, "/".join(stack).lower(), anchor
