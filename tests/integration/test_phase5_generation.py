import pytest
from src.edocs.rag.pii import redact_pii
from src.edocs.rag.rewrite import rewrite_question
from src.edocs.rag.postcheck import verify_and_clean_response
from src.edocs.rag.orchestrator import Orchestrator

def test_pii_redaction():
    text_ssn = "My SSN is 123-45-6789, please help."
    clean, has_pii = redact_pii(text_ssn)
    assert has_pii is True
    assert "[REDACTED_SSN]" in clean
    assert "123-45-6789" not in clean

    text_acct = "Check account number 12345678."
    clean, has_pii = redact_pii(text_acct)
    assert has_pii is True
    assert "[REDACTED_ACCOUNT]" in clean

    text_clean = "How do I create a Loan Schedule Record?"
    clean, has_pii = redact_pii(text_clean)
    assert has_pii is False
    assert clean == text_clean

def test_rewrite_question():
    # Standalone query
    q = "How do I perform file maintenance on schedule records?"
    res = rewrite_question(q, history=[])
    assert res == q

    # Query with pronoun referencing prior turn
    history = [
        {"role": "user", "content": "Tell me about the COMMENT field"},
        {"role": "assistant", "content": "COMMENT is a field in the Comment record."},
    ]
    followup = "What is its data type?"
    res_followup = rewrite_question(followup, history=history)
    assert "COMMENT" in res_followup or "data type" in res_followup

def test_postcheck_citations_and_identifiers():
    context = "<excerpt id='1'>The COMMENT field has data type 40 Characters.</excerpt>"
    # Valid citation [1]
    ans_valid = "The COMMENT field holds up to 40 characters [1]."
    clean, ver = verify_and_clean_response(ans_valid, context, num_excerpts=1)
    assert "[1]" in clean
    assert ver["citations_ok"] is True

    # Invalid citation [4] when num_excerpts=1
    ans_invalid = "The COMMENT field holds up to 40 characters [4]."
    clean, ver = verify_and_clean_response(ans_invalid, context, num_excerpts=1)
    assert "[4]" not in clean
    assert ver["citations_ok"] is False

def test_orchestrator_end_to_end():
    orch = Orchestrator()

    # Out of domain
    res_ood = orch.process_query("What is the stock price of Apple?")
    assert res_ood["in_domain"] is False
    assert "I can only help with Symitar Episys documentation" in res_ood["answer"]
    assert len(res_ood["citations"]) == 0

    # Greeting
    res_greet = orch.process_query("Hello there")
    assert res_greet["intent"] == "greeting"
    assert "Hi!" in res_greet["answer"]

    # In-domain field lookup
    res_field = orch.process_query("COMMENT")
    assert res_field["in_domain"] is True
    assert len(res_field["citations"]) >= 1
    assert res_field["latency_ms"] >= 0

    # In-domain with PII
    res_pii = orch.process_query("What is COMMENT for account 98765432?")
    assert res_pii["in_domain"] is True
    assert "removed what looked like member or personal data" in res_pii["answer"]
