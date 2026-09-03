from __future__ import annotations

from html import escape


def pre_block(text: str) -> str:
    return f"<pre>{escape(text)}</pre>"
