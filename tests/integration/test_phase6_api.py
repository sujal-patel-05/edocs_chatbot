import pytest
from fastapi.testclient import TestClient
from src.edocs.api.app import app

client = TestClient(app)

def test_healthz_and_readyz():
    res_health = client.get("/healthz")
    assert res_health.status_code == 200
    assert res_health.json() == {"status": "ok"}

    res_ready = client.get("/readyz")
    assert res_ready.status_code == 200
    assert res_ready.json()["status"] == "ready"

def test_releases_endpoint():
    res = client.get("/api/v1/releases")
    assert res.status_code == 200
    data = res.json()
    assert data["default_release"] == "2023.00"
    assert "2023.00" in data["available_releases"]

def test_fields_endpoint():
    res = client.get("/api/v1/fields?q=COMMENT")
    assert res.status_code == 200
    items = res.json()
    assert len(items) >= 1
    assert any("COMMENT" in (f.get("poweron_mnemonic") or "") for f in items)

def test_feedback_endpoint():
    payload = {
        "message_id": "msg-123",
        "rating": "up",
        "reason": None,
        "comment": "Accurate field answer."
    }
    res = client.post("/api/v1/feedback", json=payload)
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

def test_document_viewer_endpoint():
    # Fetch a known topic
    res = client.get("/api/v1/docs/edocs/whatsnew_c.html")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Symitar" in res.text

def test_chat_stream_contract():
    payload = {
        "message": "COMMENT",
        "release": "2023.00",
    }
    with client.stream("POST", "/api/v1/chat", json=payload) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        events_seen = []
        for line in response.iter_lines():
            if line.startswith("event: "):
                events_seen.append(line.split(": ")[1].strip())

        # Verify SSE event contract sequence
        assert "meta" in events_seen
        assert "token" in events_seen
        assert "answer_final" in events_seen
        assert "citations" in events_seen
        assert "done" in events_seen
