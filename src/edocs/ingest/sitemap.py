"""
TOC (.hhc) and keyword index (.hhk) sitemap parser.

These files use a malformed HTML-like format with nested <UL>/<OBJECT> tags.
We use a streaming HTMLParser to handle unclosed <LI> tags and other quirks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Generator


@dataclass
class Node:
    """A node in the TOC or keyword index tree."""

    name: str
    locals: list[str] = field(default_factory=list)
    see_also: str | None = None
    children: list["Node"] = field(default_factory=list)


class SitemapParser(HTMLParser):
    """
    Streaming parser for .hhc and .hhk files.

    Handles malformed HTML (unclosed <LI>, mixed case, stray tags).
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("ROOT")
        self.stack: list[Node] = [self.root]
        self.last: Node | None = None
        self.cur: Node | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "ul":
            self.stack.append(self.last or self.stack[-1])
        elif tag == "object" and a.get("type", "").lower() == "text/sitemap":
            self.cur = Node("")
        elif tag == "param" and self.cur is not None:
            n, v = a.get("name", "").lower(), a.get("value", "").strip()
            if n == "name" and not self.cur.name:
                self.cur.name = v
            elif n == "local":
                self.cur.locals.append(v)
            elif n == "see also":
                self.cur.see_also = v

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "object" and self.cur is not None:
            self.stack[-1].children.append(self.cur)
            self.last, self.cur = self.cur, None
        elif tag == "ul" and len(self.stack) > 1:
            self.last = self.stack.pop()


def parse_sitemap(text: str) -> Node:
    """Parse a .hhc or .hhk file and return the root node of the tree."""
    p = SitemapParser()
    p.feed(text)
    p.close()
    return p.root


def walk(
    node: Node, path: tuple[str, ...] = ()
) -> Generator[tuple[tuple[str, ...], Node], None, None]:
    """Yield (breadcrumb_path, node) for every node in the tree."""
    for c in node.children:
        yield path + (c.name,), c
        yield from walk(c, path + (c.name,))


def count_nodes(node: Node) -> int:
    """Count total nodes in the tree (excluding root)."""
    total = len(node.children)
    for c in node.children:
        total += count_nodes(c)
    return total


def max_depth(node: Node, current: int = 0) -> int:
    """Return the maximum depth of the tree."""
    if not node.children:
        return current
    return max(max_depth(c, current + 1) for c in node.children)


def depth_histogram(node: Node, current: int = 0) -> dict[int, int]:
    """Return a histogram of node counts at each depth level."""
    hist: dict[int, int] = {}
    for c in node.children:
        depth = current + 1
        hist[depth] = hist.get(depth, 0) + 1
        child_hist = depth_histogram(c, depth)
        for d, count in child_hist.items():
            hist[d] = hist.get(d, 0) + count
    return hist


def load_sitemap(path: Path) -> Node:
    """Load and parse a sitemap file (.hhc or .hhk), trying multiple encodings."""
    raw = path.read_bytes()

    # Try encodings in order
    for encoding in ["utf-8", "cp1252", "latin-1"]:
        try:
            text = raw.decode(encoding)
            return parse_sitemap(text)
        except UnicodeDecodeError:
            continue

    # Last resort
    text = raw.decode("utf-8", errors="replace")
    return parse_sitemap(text)
