import pytest
from src.edocs.models import Document, FieldRecord
from src.edocs.ingest.chunker import chunk_document, make_field_card_chunk

def test_chunk_document_short():
    doc = Document(
        doc_id="edocs/guide/intro.html",
        release="2023.00",
        chm="edocs",
        path="guide/intro.html",
        title="Introduction",
        breadcrumbs=[["Guide", "Introduction"]],
        toc_order=1,
        topic_type="concept",
        product_area="Guide",
        summary="An introductory topic",
        markdown="This is the introduction text for Symitar Episys documentation.",
        content_hash="abc123hash",
    )
    chunks = chunk_document(doc, max_tokens=800)
    assert len(chunks) == 1
    assert chunks[0].doc_id == "edocs/guide/intro.html"
    assert chunks[0].kind == "topic"
    assert "[Release 2023.00]" in chunks[0].text
    assert "Type: concept." in chunks[0].text
    assert "This is the introduction text" in chunks[0].text

def test_make_field_card_chunk():
    doc = Document(
        doc_id="edocs/fields/balance.html",
        release="2023.00",
        chm="edocs",
        path="fields/balance.html",
        title="Balance Field",
        breadcrumbs=[["Fields", "Balance Field"]],
        toc_order=5,
        topic_type="reference",
        product_area="Fields",
        summary="Account balance field reference",
        markdown="Detailed notes on balance.",
        content_hash="def456hash",
    )
    fld = FieldRecord(
        release="2023.00",
        record="Share",
        field_name="Balance",
        field_number="005",
        poweron_mnemonic="BALANCE",
        data_type="Money",
        doc_id=doc.doc_id,
    )
    card_chunk = make_field_card_chunk(fld, doc)
    assert card_chunk.kind == "field_card"
    assert "Record: Share | Field: Balance" in card_chunk.text
    assert "Field Number: 005" in card_chunk.text
    assert "PowerOn Mnemonic: BALANCE" in card_chunk.text
