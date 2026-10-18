"""
Gazetteer module for fast case-insensitive entity matching in queries.

Tracks known Symitar record names, field names, PowerOn mnemonics,
SymXchange mnemonics, and index keywords.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Set

logger = logging.getLogger("edocs.rag.gazetteer")


class Gazetteer:
    def __init__(self, release: str = "2023.00", processed_dir: Path | None = None):
        self.release = release
        self.processed_dir = (processed_dir or Path(f"data/processed/{release}")).resolve()
        self.records: Set[str] = set()
        self.fields: Set[str] = set()
        self.mnemonics: Set[str] = set()
        self.keywords: Set[str] = set()
        self._automaton = None
        self._term_map: Dict[str, str] = {}  # lowercase_term -> category
        self.load_terms()

    def load_terms(self):
        # Seed core Symitar record names
        core_records = [
            "LOAN", "ACCOUNT", "SHARE", "MEMBER", "NAME", "TRACKING",
            "CARD", "TRANSACTION", "USER", "WIRE", "EFT", "COLLATERAL",
            "NOTE", "HOLD", "APPLICATION", "PREFERENCE", "DEALER",
            "PARTICIPANT", "CHECK", "CHECKORDER", "IRS", "GLACCOUNT",
            "GLTRANSACTION", "ATMDIALOG", "ACHITEM", "ACHEDIT"
        ]
        for cr in core_records:
            self.records.add(cr)
            self._term_map[cr.lower()] = "records"
            self._term_map[f"{cr.lower()} record"] = "records"
            self._term_map[f"{cr.lower()} record fields"] = "records"

        fields_file = self.processed_dir / "fields.jsonl"
        if fields_file.exists():
            with open(fields_file, "r", encoding="utf-8") as f:
                for line in f:
                    data = json.loads(line)
                    if rec := data.get("record"):
                        self.records.add(rec)
                        self._term_map[rec.lower()] = "records"
                        clean_rec = re.sub(r"(?i)\s+(record|fields|file)", "", rec).strip()
                        if clean_rec:
                            self._term_map[clean_rec.lower()] = "records"
                    if fld := data.get("field_name"):
                        self.fields.add(fld)
                        self._term_map[fld.lower()] = "fields"
                    if mnem := data.get("poweron_mnemonic"):
                        self.mnemonics.add(mnem)
                        self._term_map[mnem.lower()] = "mnemonics"
                    if sym_mnem := data.get("symxchange_mnemonic"):
                        self.mnemonics.add(sym_mnem)
                        self._term_map[sym_mnem.lower()] = "mnemonics"

        kw_file = self.processed_dir / "keywords.jsonl"
        if kw_file.exists():
            with open(kw_file, "r", encoding="utf-8") as f:
                for line in f:
                    data = json.loads(line)
                    if term := data.get("term"):
                        self.keywords.add(term)
                        self._term_map[term.lower()] = "keywords"

        logger.info(
            "Gazetteer loaded: %d records, %d fields, %d mnemonics, %d keywords",
            len(self.records),
            len(self.fields),
            len(self.mnemonics),
            len(self.keywords),
        )
        self._build_matcher()

    def _build_matcher(self):
        try:
            import ahocorasick
            A = ahocorasick.Automaton()
            for term, cat in self._term_map.items():
                if len(term) >= 2:
                    A.add_word(term, (term, cat))
            A.make_automaton()
            self._automaton = A
            logger.info("Built Aho-Corasick automaton with %d terms", len(self._term_map))
        except ImportError:
            logger.info("pyahocorasick not available. Using regex boundary matcher.")
            self._automaton = None

    def match(self, text: str) -> Dict[str, List[str]]:
        """
        Match text against the gazetteer terms.
        Returns: {"records": [...], "fields": [...], "mnemonics": [...], "keywords": [...]}
        """
        matched: Dict[str, Set[str]] = {
            "records": set(),
            "fields": set(),
            "mnemonics": set(),
            "keywords": set(),
        }
        text_lower = text.lower()

        if self._automaton is not None:
            for end_idx, (term, cat) in self._automaton.iter(text_lower):
                start_idx = end_idx - len(term) + 1
                # Check word boundaries
                left_ok = start_idx == 0 or not text_lower[start_idx - 1].isalnum()
                right_ok = end_idx == len(text_lower) - 1 or not text_lower[end_idx + 1].isalnum()
                if left_ok and right_ok:
                    matched[cat].add(term)
        else:
            # Word boundary regex search
            words = set(re.findall(r"\b[A-Za-z0-9_:-]+\b", text_lower))
            for word in words:
                if word in self._term_map:
                    cat = self._term_map[word]
                    matched[cat].add(word)

        return {k: sorted(list(v)) for k, v in matched.items()}
