import pytest
from src.edocs.ingest.sitemap import parse_sitemap, walk

def test_parse_sitemap_nested_and_unclosed():
    sample_hhc = """
    <!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML//EN">
    <HTML>
    <BODY>
    <UL>
        <LI> <OBJECT type="text/sitemap">
            <param name="Name" value="Getting Started">
            <param name="Local" value="intro.html">
        </OBJECT>
        <UL>
            <LI> <OBJECT type="text/sitemap">
                <param name="Name" value="Overview">
                <param name="Local" value="overview.html">
            </OBJECT>
            <LI> <OBJECT type="text/sitemap">
                <param name="Name" value="Architecture">
                <param name="Local" value="arch.html">
                <param name="See Also" value="System Requirements">
            </OBJECT>
        </UL>
        <LI> <OBJECT type="text/sitemap">
            <param name="Name" value="Account Records">
        </OBJECT>
    </UL>
    </BODY>
    </HTML>
    """
    root = parse_sitemap(sample_hhc)
    assert len(root.children) == 2
    getting_started = root.children[0]
    assert getting_started.name == "Getting Started"
    assert getting_started.locals == ["intro.html"]
    assert len(getting_started.children) == 2
    
    arch = getting_started.children[1]
    assert arch.name == "Architecture"
    assert arch.see_also == "System Requirements"
    
    acct = root.children[1]
    assert acct.name == "Account Records"
    assert acct.locals == []
    
    entries = list(walk(root))
    assert len(entries) == 4
    paths = [p for p, n in entries]
    assert ("Getting Started",) in paths
    assert ("Getting Started", "Overview") in paths
    assert ("Getting Started", "Architecture") in paths
    assert ("Account Records",) in paths
