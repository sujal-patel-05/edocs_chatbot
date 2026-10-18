import pytest
from src.edocs.rag.gazetteer import Gazetteer
from src.edocs.rag.router import Router
from src.edocs.rag.retrieve import Retriever, rrf_fuse
from src.edocs.rag.rerank import Reranker
from src.edocs.rag.context import build_context
from src.edocs.store.pg import PostgresStore
from src.edocs.models import Chunk

def test_gazetteer_entity_extraction():
    gaz = Gazetteer(release="2023.00")
    matches = gaz.match("What is the data type for the COMMENT field?")
    assert "comment" in matches["mnemonics"] or "comment" in matches["records"]

def test_router_intents():
    gaz = Gazetteer(release="2023.00")
    router = Router(gazetteer=gaz)

    # Greeting
    res_greet = router.route("Hello assistant")
    assert res_greet.in_domain is True
    assert res_greet.intent == "greeting"

    # Out of domain
    res_ood = router.route("What is the weather in Dallas?")
    assert res_ood.in_domain is False
    assert res_ood.intent == "out_of_domain"

    # Procedure
    res_proc = router.route("How do I create an account schedule record in Episys?")
    assert res_proc.in_domain is True
    assert res_proc.intent == "procedure"

    # Field lookup
    res_field = router.route("COMMENT")
    assert res_field.in_domain is True
    assert res_field.intent == "field_lookup"

def test_rrf_fuse_logic():
    list1 = ["docA", "docB", "docC"]
    list2 = ["docB", "docA", "docD"]
    fused = rrf_fuse([list1, list2], k=60)
    top_doc_ids = [doc_id for doc_id, score in fused]
    # docA and docB appear in both lists and should score higher than docC and docD
    assert top_doc_ids[0] in ("docA", "docB")
    assert top_doc_ids[1] in ("docA", "docB")

def test_exact_lookup_retrieval():
    store = PostgresStore("postgresql://localhost:5432/edocs")
    gaz = Gazetteer(release="2023.00")
    router = Router(gazetteer=gaz)
    retriever = Retriever(store=store)

    decision = router.route("COMMENT")
    results = retriever.retrieve("COMMENT", decision=decision, release="2023.00", top_k=5)

    assert len(results) >= 1
    top_chunk, score = results[0]
    assert score > 0
    assert "COMMENT" in top_chunk.text

def test_context_builder_budget_and_format():
    sample_chunk = Chunk(
        chunk_id="edocs/sample.html#0",
        doc_id="edocs/sample.html",
        release="2023.00",
        text="Sample topic body text about Symitar.",
        section_path=["Admin", "Sample Topic"],
        topic_type="concept",
        product_area="Admin",
        kind="topic",
        token_count=20,
        content_hash="hash1",
    )
    context_str, citations = build_context([(sample_chunk, 0.95)], max_tokens=500)
    assert '<excerpt id="1"' in context_str
    assert 'doc_id="edocs/sample.html"' in context_str
    assert len(citations) == 1
    assert citations[0]["n"] == 1
    assert citations[0]["doc_id"] == "edocs/sample.html"
