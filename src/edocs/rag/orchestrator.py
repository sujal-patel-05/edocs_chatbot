"""
RAG Pipeline Orchestrator for Symitar eDocs Assistant.

Implements the complete online query pipeline (Section 11).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Dict, Generator, List, Optional
import yaml

from src.edocs.config import Settings, load_settings
from src.edocs.llm.client import LLMClient
from src.edocs.rag.context import build_context
from src.edocs.rag.gazetteer import Gazetteer
from src.edocs.rag.pii import redact_pii
from src.edocs.rag.postcheck import verify_and_clean_response
from src.edocs.rag.rerank import Reranker
from src.edocs.rag.retrieve import Retriever
from src.edocs.rag.rewrite import rewrite_question
from src.edocs.rag.router import Router, RouterDecision
from src.edocs.store.pg import PostgresStore
from src.edocs.store.qdrant import QdrantVectorStore

logger = logging.getLogger("edocs.rag.orchestrator")


class Orchestrator:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or load_settings()
        self.store = PostgresStore(dsn=self.settings.postgres.dsn)
        self.qdrant = QdrantVectorStore(
            url=self.settings.qdrant.url,
            collection_name=self.settings.qdrant.collection,
        )
        self.gazetteer = Gazetteer(release=self.settings.app.default_release)
        self.router = Router(gazetteer=self.gazetteer)
        self.reranker = Reranker(
            model_name=self.settings.reranker.model,
            top_n_in=self.settings.reranker.top_n_in,
            top_n_out=self.settings.reranker.top_n_out,
            min_score=self.settings.reranker.min_score,
        )
        self.retriever = Retriever(
            store=self.store,
            reranker=self.reranker,
            qdrant=self.qdrant,
        )
        self.llm = LLMClient(config=self.settings.llm)

        # Load templates
        templates_path = Path("prompts/templates.yaml")
        if templates_path.exists():
            with open(templates_path, "r", encoding="utf-8") as f:
                self.templates = yaml.safe_load(f) or {}
        else:
            self.templates = {}

        # Load system prompt
        sys_prompt_path = Path("prompts/system_answer.md")
        if sys_prompt_path.exists():
            self.system_prompt_template = sys_prompt_path.read_text(encoding="utf-8")
        else:
            self.system_prompt_template = ""

    def process_query(
        self,
        message: str,
        history: Optional[List[dict]] = None,
        release: Optional[str] = None,
        user_role: str = "general",
    ) -> dict:
        """Execute full question answering pipeline."""
        t_start = time.time()
        rel = release or self.settings.app.default_release

        # 1. PII Redaction
        clean_msg, has_pii = redact_pii(message)

        # 2. Follow-up Rewrite
        standalone_q = rewrite_question(clean_msg, history=history, llm_client=self.llm)

        # 3. Router
        decision = self.router.route(standalone_q)

        # 4. Out of domain gate
        if not decision.in_domain:
            refusal = self.templates.get(
                "refusal",
                "I can only help with Symitar Episys documentation. Try asking about an Episys feature, procedure, record or field, PowerOn, a job, or an error message.",
            )
            return {
                "answer": refusal,
                "citations": [],
                "intent": decision.intent,
                "in_domain": False,
                "verification": {"citations_ok": True, "identifiers_ok": True, "removed": []},
                "latency_ms": int((time.time() - t_start) * 1000),
            }

        # 5. Greeting gate
        if decision.intent == "greeting":
            greeting = self.templates.get(
                "greeting",
                "Hi! Ask me anything about Symitar Episys documentation — for example a procedure, a record or field, PowerOn syntax, or an error message.",
            )
            return {
                "answer": greeting,
                "citations": [],
                "intent": "greeting",
                "in_domain": True,
                "verification": {"citations_ok": True, "identifiers_ok": True, "removed": []},
                "latency_ms": int((time.time() - t_start) * 1000),
            }

        # 6. Retrieval & Reranking
        scored_chunks = self.retriever.retrieve(
            query=standalone_q,
            decision=decision,
            release=rel,
            top_k=self.settings.reranker.top_n_out,
        )

        # 7. Relevance threshold check
        if not scored_chunks:
            not_found = self.templates.get(
                "not_found", "I couldn't find this in the indexed eDocs for release {release}."
            ).format(release=rel)
            return {
                "answer": not_found,
                "citations": [],
                "intent": decision.intent,
                "in_domain": True,
                "verification": {"citations_ok": True, "identifiers_ok": True, "removed": []},
                "latency_ms": int((time.time() - t_start) * 1000),
            }

        # 8. Build context
        context_str, citations = build_context(
            scored_chunks, max_tokens=self.settings.context.max_context_tokens
        )

        # 9. Format System Answer Prompt
        refusal_text = self.templates.get("refusal", "Out of domain.")
        not_found_text = self.templates.get("not_found", "Not found.").format(release=rel)

        sys_prompt = self.system_prompt_template.format(
            organization="Symitar Episys Operations",
            refusal_text=refusal_text,
            not_found_text=not_found_text,
            intent=decision.intent,
            user_role=user_role,
            release=rel,
            related_topics="",
            numbered_excerpts=context_str,
        )

        # 10. Call LLM
        raw_answer = self.llm.generate(
            prompt=standalone_q,
            system_prompt=sys_prompt,
            context_excerpts=context_str,
        )

        # 11. Post-checks
        clean_answer, verification = verify_and_clean_response(
            answer=raw_answer,
            context_text=context_str,
            num_excerpts=len(citations),
        )

        # Append PII note if user originally had PII
        if has_pii:
            pii_notice = self.templates.get("pii_notice", "")
            if pii_notice:
                clean_answer = f"{clean_answer}\n\n*Note: {pii_notice}*"

        latency_ms = int((time.time() - t_start) * 1000)

        return {
            "answer": clean_answer,
            "citations": citations,
            "intent": decision.intent,
            "in_domain": True,
            "verification": verification,
            "latency_ms": latency_ms,
        }
