"""The one thing the citation queue needed from the poster repo.

`citations.py` called `content_generator._call_claude` to write each
directory's description at the length that directory allows. That single
import was the only code-level tie between the citation system and the social
poster, so it moved here rather than dragging `content_generator`, `config`
and the platform rules along with it.

Same request shape, same model, same failure behaviour. No key, and the caller
sees the exception — a description is not worth inventing offline.
"""
import os

import requests

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def _call_claude(system_prompt: str, user_prompt: str, max_tokens: int = 1200) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. The queue writes each directory's "
            "description at that directory's length limit; without a key it "
            "would have to ship a generic one, which is the thing a citation "
            "must not be."
        )
    resp = requests.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": ANTHROPIC_MODEL,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return "".join(block.get("text", "") for block in data.get("content", []))
