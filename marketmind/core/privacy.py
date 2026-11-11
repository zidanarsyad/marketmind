"""Personal details in review text, masked before they can reach a file, a report or a screen.

Real reviews sometimes carry what a reviewer typed about themselves or someone else: an e-mail address, a phone
number, a user handle. The Tokopedia importer masks them as it imports (so they never reach ``data/real/``), and the
Consumer Insight agent masks the review quotes it picks for the report, whatever the data source.

Phone numbers are Indonesian mobile numbers (``0812-3456-7890``, ``+62 812 3456 7890``, ``6281234567890``): ``08``,
``+62 8`` or ``628`` followed by 9 to 13 more digits, optionally split by spaces, dots or dashes. Prices do not fit
that shape (``Rp 85.000``, ``Rp 628.500.000`` are too short after the prefix), nor do dates and times.
"""
from __future__ import annotations

import re

EMAIL = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")
PHONE = re.compile(r"(?<![\w.,+])(?:\+62[\s-]?|62|0)8\d(?:[\s.-]?\d){7,11}(?!\w)")
HANDLE = re.compile(r"(?<![\w@])@[A-Za-z0-9_][A-Za-z0-9_.]{1,28}[A-Za-z0-9_]\b")   # @abc and longer


def mask_personal(text: str | None) -> str | None:
    """``text`` with e-mail addresses, phone numbers and @handles replaced by [email], [phone] and [user]."""
    if not text or not isinstance(text, str):
        return text
    text = EMAIL.sub("[email]", text)
    text = PHONE.sub("[phone]", text)
    return HANDLE.sub("[user]", text)
