"""
Query classification and intent router.

Classifies incoming queries into in-domain/out-of-domain, determines intent
(procedure, field_lookup, poweron_code, etc.), and extracts entities.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field
from src.edocs.rag.gazetteer import Gazetteer

logger = logging.getLogger("edocs.rag.router")

IntentType = Literal[
    "procedure",
    "field_lookup",
    "poweron_code",
    "error_troubleshoot",
    "concept",
    "navigation",
    "release_info",
    "greeting",
    "out_of_domain",
]


class RouterEntities(BaseModel):
    records: List[str] = Field(default_factory=list)
    fields: List[str] = Field(default_factory=list)
    mnemonics: List[str] = Field(default_factory=list)
    codes: List[str] = Field(default_factory=list)
    other_terms: List[str] = Field(default_factory=list)


class RouterDecision(BaseModel):
    in_domain: bool = True
    intent: IntentType = "concept"
    entities: RouterEntities = Field(default_factory=RouterEntities)
    needs_clarification: bool = False
    clarifying_question: Optional[str] = None


class Router:
    def __init__(self, gazetteer: Optional[Gazetteer] = None):
        self.gazetteer = gazetteer or Gazetteer()

    def route(self, question: str) -> RouterDecision:
        """
        Route and classify question.
        Combines gazetteer matches with rule-based and model intent classification.
        """
        q = question.strip().lower()

        # 1. Check greeting
        if re.match(r"^(hi|hello|hey|good morning|good afternoon)\b", q):
            return RouterDecision(
                in_domain=True,
                intent="greeting",
                entities=RouterEntities(),
            )

        # 2. Check out of domain patterns (weather, stock price, unrelated software, general finance, etc.)
        out_of_domain_patterns = [
            r"\b(weather|movie|recipe|dinner|sports|football|basketball)\b",
            r"\b(stock price|stocks|stock market|bitcoin|crypto|apple stock)\b",
            r"\b(fiserv|dna|corelation|keystone|symitar competitors)\b",
            r"\b(write a poem|tell a joke|who is the president|capital of)\b",
        ]
        for pat in out_of_domain_patterns:
            if re.search(pat, q):
                return RouterDecision(
                    in_domain=False,
                    intent="out_of_domain",
                    entities=RouterEntities(),
                )

        # 3. Match terms using gazetteer
        g_matches = self.gazetteer.match(question)
        entities = RouterEntities(
            records=g_matches.get("records", []),
            fields=g_matches.get("fields", []),
            mnemonics=g_matches.get("mnemonics", []),
            codes=[],
            other_terms=g_matches.get("keywords", []),
        )

        # 4. Classify intent
        intent: IntentType = "concept"

        if re.search(r"\b(mnemonic|field number|field name|data type|help file|default value)\b", q):
            intent = "field_lookup"
        elif len(entities.mnemonics) > 0 and len(q.split()) <= 4:
            intent = "field_lookup"
        elif len(entities.records) > 0 and len(q.split()) <= 4:
            intent = "field_lookup"
        elif re.search(r"\b(record|fields|table of fields|code|codes)\b", q) and len(entities.records) > 0:
            intent = "field_lookup"
        elif re.search(r"\b(poweron|repgen|specfile|def specfile|fmperform)\b", q):
            intent = "poweron_code"
        elif re.search(r"\b(how do i|how to|steps to|create a|revise a|delete a|postponing|run a batch)\b", q):
            intent = "procedure"
        elif re.search(r"\b(error|warning|exception|failed|issue|troubleshoot)\b", q):
            intent = "error_troubleshoot"
        elif re.search(r"\b(what is new|release notes|whats new|2023\.00 changes)\b", q):
            intent = "release_info"
        elif re.search(r"\b(menu|where is|navigate to|window|screen)\b", q):
            intent = "navigation"

        return RouterDecision(
            in_domain=True,
            intent=intent,
            entities=entities,
        )
