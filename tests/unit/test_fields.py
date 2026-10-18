import pytest
from src.edocs.ingest.fields import extract_field_props, extract_field_record

LABELS = {
    "field number": "field_number",
    "poweron mnemonic": "poweron_mnemonic",
    "mnemonic": "poweron_mnemonic",
    "data type": "data_type",
    "source": "source",
    "help file": "help_file",
    "default value": "default_value",
    "default control": "default_control",
}

def test_extract_field_props_from_table():
    html = """
    <html>
    <body>
        <h1>Test Field</h1>
        <table class="symTbl">
            <tr><td>Field Number</td><td>100</td></tr>
            <tr><td>Mnemonic</td><td>TESTMNEM</td></tr>
            <tr><td>Data Type</td><td>Character</td></tr>
            <tr><td>Help File</td><td>1234</td></tr>
        </table>
    </body>
    </html>
    """
    props = extract_field_props(html, LABELS)
    assert props is not None
    assert props["field_number"] == "100"
    assert props["poweron_mnemonic"] == "TESTMNEM"
    assert props["data_type"] == "Character"
    assert props["help_file"] == "1234"

def test_extract_field_record_model():
    html = """
    <html>
    <body>
        <h1>Account Description</h1>
        <p>This field holds the description for the account.</p>
        <table>
            <tr><td>Field Number</td><td>001</td></tr>
            <tr><td>Mnemonic</td><td>DESCRIPTION</td></tr>
            <tr><td>Data Type</td><td>Character (40)</td></tr>
        </table>
    </body>
    </html>
    """
    rec = extract_field_record(
        doc_id="edocs/field_001.html",
        release="2023.00",
        html=html,
        labels=LABELS,
        title="Account Description",
        breadcrumbs=["Account Records", "Account Description"],
    )
    assert rec is not None
    assert rec.field_number == "001"
    assert rec.poweron_mnemonic == "DESCRIPTION"
    assert rec.field_name == "Account Description"
    assert rec.record == "Account"
    assert "description for the account" in (rec.description or "")
