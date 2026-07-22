"""Shared prompt utilities for Doubao content filter compliance.

Terms normalization: fix writing errors where a word coincidentally matches
a commercial brand/trademark, causing false-positive content filtering.
These are NOT censorship — they correct genuine typos in source text.
The original text in the database is NEVER modified.
"""

# Map of problematic terms → correct Chinese equivalents.
# Keys are words that happen to match commercial brands/trademarks.
# Values are the correct ancient Chinese literary terms intended by the author.
TERM_NORMALIZATIONS: dict[str, str] = {
    # 曼联 = Manchester United FC (registered trademark)
    # Correct term: 幔帐 (ancient Chinese bed curtain / canopy)
    "曼联": "幔帐",
}


def normalize_prompt_terms(text: str) -> str:
    """Replace terms that coincidentally match commercial brands/trademarks
    with their correct ancient Chinese equivalents.

    Does NOT modify the original novel text — only normalizes the
    prompt sent to Doubao.
    """
    result = text
    for bad, good in TERM_NORMALIZATIONS.items():
        result = result.replace(bad, good)
    return result
