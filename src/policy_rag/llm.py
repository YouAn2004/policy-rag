"""Language model back end. A small interface so tests can use a scripted fake."""

import json
import re

from . import config


class OllamaLLM:
    def __init__(self, model=config.LLM_MODEL):
        self.model = model

    def complete(self, prompt, system=None, purpose="", json_mode=False):
        import ollama

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = ollama.chat(
            model=self.model,
            messages=messages,
            format="json" if json_mode else "",
            keep_alive="30m",
            options={"temperature": 0, "num_ctx": config.LLM_NUM_CTX},
        )
        return resp["message"]["content"].strip()


def parse_json(text):
    """Parse a JSON object from model output. Returns {} when nothing usable is found."""
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        m = re.search(r"\{.*\}", text or "", re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                pass
    return {}
