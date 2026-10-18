import pytest
from bs4 import BeautifulSoup
from src.edocs.ingest.html_clean import decode_html, html_to_markdown

def test_decode_html():
    raw_utf8 = "<html><head><meta charset='utf-8'></head><body>Hello world’s</body></html>".encode("utf-8")
    assert "Hello world’s" in decode_html(raw_utf8)

    raw_cp1252 = b"<html><body>Hello \x92world\x92</body></html>"
    decoded = decode_html(raw_cp1252)
    assert "world" in decoded

def test_html_to_markdown_admonitions_and_tables():
    html = """
    <html>
    <body>
        <h1>Step by Step Procedure</h1>
        <div class="note">This is a vital note.</div>
        <div class="important">Take backup first.</div>
        <ol>
            <li>Navigate to Account Manager.</li>
            <li>Select Edit.</li>
        </ol>
        <table>
            <tr><th>Param</th><th>Value</th></tr>
            <tr><td>TIMEOUT</td><td>30</td></tr>
        </table>
        <pre>
        IF ACCOUNT:BALANCE > 0 THEN
            PRINT "ACTIVE"
        END
        </pre>
    </body>
    </html>
    """
    soup = BeautifulSoup(html, "lxml")
    md, imgs = html_to_markdown(soup, "Step by Step Procedure")
    
    # Check that notes and important blocks were preserved with labels
    assert "> **Note:**" in md
    assert "> **Important:**" in md
    assert "Take backup first." in md
    
    # Check that procedure steps were preserved
    assert "1. Navigate to Account Manager." in md
    assert "2. Select Edit." in md
    
    # Check that table was converted
    assert "| Param | Value |" in md
    assert "| TIMEOUT | 30 |" in md
    
    # Check that code whitespace was preserved
    assert "IF ACCOUNT:BALANCE > 0 THEN" in md
    assert "```" in md
