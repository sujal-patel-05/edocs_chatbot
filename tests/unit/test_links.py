import pytest
from src.edocs.ingest.links import normalize_link

def test_normalize_link_relative():
    # Sibling link
    res = normalize_link("sub.html", "edocs", "guide")
    assert res == ("edocs", "guide/sub.html", "")

    # Parent traversal
    res = normalize_link("../other/page.html#section1", "edocs", "guide/topic")
    assert res == ("edocs", "guide/other/page.html", "section1")

    # Windows backslashes
    res = normalize_link("sub\\folder\\doc.htm", "edocs", "")
    assert res == ("edocs", "sub/folder/doc.htm", "")

    # Same page anchor
    res = normalize_link("#top", "edocs", "guide/topic")
    assert res == ("edocs", "", "top")

def test_normalize_link_cross_chm():
    # ms-its prefix
    res = normalize_link("ms-its:admin.chm::/params/acct.htm#p1", "edocs", "guide")
    assert res == ("admin", "params/acct.htm", "p1")

    # mk:@MSITStore with Windows path
    res = normalize_link("mk:@MSITStore:C:\\Help\\OtherHelp.CHM::/overview.html", "edocs", "")
    assert res == ("otherhelp", "overview.html", "")

def test_normalize_link_external():
    assert normalize_link("https://example.com", "edocs", "") is None
    assert normalize_link("mailto:support@symitar.com", "edocs", "") is None
    assert normalize_link("javascript:void(0)", "edocs", "") is None
