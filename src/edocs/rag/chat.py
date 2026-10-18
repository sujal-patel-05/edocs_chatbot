"""
Interactive Chat CLI for Symitar eDocs Assistant.

Usage:
    python -m src.edocs.rag.chat
"""

from __future__ import annotations

import sys
from src.edocs.rag.orchestrator import Orchestrator


def run_chat_cli():
    print("=" * 60)
    print("Symitar eDocs Assistant (Interactive Console)")
    print("Type 'exit' or 'quit' to end session.")
    print("=" * 60 + "\n")

    orchestrator = Orchestrator()
    history = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSession ended.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            print("Goodbye!")
            break

        res = orchestrator.process_query(message=user_input, history=history)
        print(f"\nAssistant: {res['answer']}\n")

        if res["citations"]:
            print("Sources:")
            for c in res["citations"]:
                print(f"  [{c['n']}] {c['title']} — {c['breadcrumb']} (release {c['release']})")
            print()

        # Update history
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": res["answer"]})


if __name__ == "__main__":
    run_chat_cli()
