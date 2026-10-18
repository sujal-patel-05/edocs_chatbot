"""
CLI tool for Phase 4 retrieval testing without an LLM.

Usage:
    python -m src.edocs.rag.ask "How do I create a loan schedule record?"
    python -m src.edocs.rag.ask "COMMENT"
"""

from __future__ import annotations

import argparse
import sys
from src.edocs.config import load_settings
from src.edocs.rag.context import build_context
from src.edocs.rag.gazetteer import Gazetteer
from src.edocs.rag.rerank import Reranker
from src.edocs.rag.retrieve import Retriever
from src.edocs.rag.router import Router
from src.edocs.store.pg import PostgresStore
from src.edocs.store.qdrant import QdrantVectorStore


def ask_cli(query: str, release: str = "2023.00"):
    settings = load_settings()
    gaz = Gazetteer(release=release)
    router = Router(gazetteer=gaz)

    decision = router.route(query)
    print("=" * 60)
    print(f"QUERY: {query}")
    print(f"DECISION: in_domain={decision.in_domain}, intent={decision.intent}")
    print(f"ENTITIES: records={decision.entities.records}, fields={decision.entities.fields}, mnemonics={decision.entities.mnemonics}")
    print("=" * 60)

    if not decision.in_domain:
        print("\n[ROUTER REFUSAL]: Query classified as out of domain.")
        return

    if decision.intent == "greeting":
        print("\n[ROUTER GREETING]: Hello! Ask me anything about Symitar Episys documentation.")
        return

    store = PostgresStore(dsn=settings.postgres.dsn)
    reranker = Reranker(
        model_name=settings.reranker.model,
        top_n_in=settings.reranker.top_n_in,
        top_n_out=settings.reranker.top_n_out,
        min_score=settings.reranker.min_score,
    )
    qdrant = QdrantVectorStore(url=settings.qdrant.url, collection_name=settings.qdrant.collection)

    retriever = Retriever(store=store, reranker=reranker, qdrant=qdrant)
    results = retriever.retrieve(query=query, decision=decision, release=release, top_k=settings.reranker.top_n_out)

    print(f"\nRETRIEVED EXCERPTS ({len(results)} chunks):\n")
    for idx, (chunk, score) in enumerate(results, 1):
        bc = " > ".join(chunk.section_path)
        print(f"[{idx}] (Score: {score:.3f}) {chunk.doc_id}")
        print(f"    Breadcrumb: {bc}")
        print(f"    Kind: {chunk.kind}, Topic Type: {chunk.topic_type}")
        print(f"    Preview: {chunk.text.splitlines()[-1][:120]}...\n")


def main():
    parser = argparse.ArgumentParser(description="Symitar eDocs Retrieval CLI")
    parser.add_argument("query", type=str, help="Question or identifier to look up")
    parser.add_argument("--release", type=str, default="2023.00", help="Episys release label")
    args = parser.parse_args()

    ask_cli(query=args.query, release=args.release)


if __name__ == "__main__":
    main()
