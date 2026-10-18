"""
OpenAI-compatible LLM client for local Ollama / vLLM serving.

Provides streaming and non-streaming completions, with fallback to grounded
extractive synthesis when the local LLM server is offline.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Generator, List, Optional
from src.edocs.config import LLMConfig

logger = logging.getLogger("edocs.llm.client")


class LLMClient:
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self.base_url = self.config.base_url.rstrip("/")
        self.model = self.config.model
        self.temperature = self.config.temperature
        self.max_tokens = self.config.max_tokens
        self.timeout_s = self.config.timeout_s

    def is_server_reachable(self) -> bool:
        """Check if local LLM server is up."""
        try:
            req = urllib.request.Request(f"{self.base_url}/models", method="GET")
            with urllib.request.urlopen(req, timeout=1.5):
                return True
        except Exception:
            return False

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context_excerpts: Optional[str] = None,
    ) -> str:
        """Execute non-streaming completion."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "edocs-assistant/1.0",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        for attempt in range(2):
            try:
                req = urllib.request.Request(
                    f"{self.base_url}/chat/completions",
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    return data["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as he:
                if he.code == 429 and attempt == 0:
                    import time
                    time.sleep(1.8)
                    continue
                logger.warning(
                    "Local/Hosted LLM server at %s unavailable (%s). Using extractive fallback synthesis.",
                    self.base_url,
                    he,
                )
                return self._fallback_synthesis(prompt, context_excerpts)
            except Exception as e:
                logger.warning(
                    "Local/Hosted LLM server at %s unavailable (%s). Using extractive fallback synthesis.",
                    self.base_url,
                    e,
                )
                return self._fallback_synthesis(prompt, context_excerpts)

        return self._fallback_synthesis(prompt, context_excerpts)

    def stream_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context_excerpts: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """Execute streaming completion, yielding text delta tokens."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "edocs-assistant/1.0",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        try:
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                for line in resp:
                    line_str = line.decode("utf-8").strip()
                    if line_str.startswith("data: ") and line_str != "data: [DONE]":
                        chunk_data = json.loads(line_str[6:])
                        delta = chunk_data["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
        except Exception as e:
            logger.warning(
                "Local LLM streaming to %s failed (%s). Yielding fallback synthesis.",
                self.base_url,
                e,
            )
            fallback = self._fallback_synthesis(prompt, context_excerpts)
            for word in fallback.split(" "):
                yield word + " "

    def _fallback_synthesis(
        self, prompt: str, context_excerpts: Optional[str] = None
    ) -> str:
        """
        Extractive synthesis fallback when the neural model is offline.
        Produces grounded answer directly from the retrieved context with citations.
        """
        if not context_excerpts or "<excerpt" not in context_excerpts:
            return "I couldn't find this documented in the indexed eDocs [1]."

        import re
        # Find all excerpts
        excerpts = re.findall(r'<excerpt\s+id="(\d+)"[^>]*?>(.*?)</excerpt>', context_excerpts, re.DOTALL)
        if not excerpts:
            # Fallback regex if title contained '>'
            excerpts = re.findall(r'<excerpt\s+id="(\d+)"[\s\S]*?score="[\d.]+">\n?(.*?)</excerpt>', context_excerpts)

        if excerpts:
            overview_text = ""
            field_cards = []
            primary_id = excerpts[0][0]

            for eid, content in excerpts:
                clean_body = re.sub(r'^[^\n]*score="[\d.]+">\s*', '', content.strip())
                if "| Field |" in clean_body or "| Field #" in clean_body or "Record Overview" in clean_body:
                    overview_text = clean_body
                    primary_id = eid
                    break
                elif "Record:" in clean_body and "Field:" in clean_body:
                    field_cards.append((eid, clean_body))

            if overview_text:
                return f"{overview_text}\n\n[Cited from eDocs: {primary_id}]"

            if field_cards:
                cards_formatted = []
                for eid, card in field_cards[:5]:
                    cards_formatted.append(f"- **{card.split('|')[1].strip() if '|' in card else 'Field'}**: {card} [{eid}]")
                return "### Retrieved Field Definitions\n\n" + "\n".join(cards_formatted)

            # Extract substantive content across top excerpts (procedures, steps, explanations)
            combined_blocks = []
            for eid, content in excerpts[:3]:
                clean_body = re.sub(r'^[^\n]*score="[\d.]+">\s*', '', content.strip())
                lines = [
                    l for l in clean_body.splitlines()
                    if l.strip() and not l.startswith("[Release") and not l.startswith("Type:")
                ]
                if lines:
                    block_text = "\n".join(lines).strip()
                    combined_blocks.append(f"{block_text} [{eid}]")

            if combined_blocks:
                return "\n\n".join(combined_blocks)

        return "Documented details are available in the linked eDocs sources [1]."
