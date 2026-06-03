"""summarize(value, branches) -> str, deterministic.

The summary is part of the hashed node, so it MUST be a pure function of structural facts and never
LLM prose, or the same value would yield different handles and content-addressing breaks.
derive_summary depends only on the branch names (count + sorted names), which makes it identical for
encode, extend, and merge alike — none of those reconstruct the aggregate value.

Names are sorted by UTF-16 code unit (via the UTF-16-BE encoding as the sort key), matching JCS key
ordering, so the string is byte-identical to the TypeScript port (whose default sort is already by
UTF-16 code unit). Plain code-point sorting would diverge on astral characters.
"""


def derive_summary(value, branches):
    """Deterministic structural summary of a branch: "<n> branches: <sorted names>"."""
    names = sorted(branches.keys(), key=lambda s: s.encode("utf-16-be"))
    n = len(names)
    if n == 0:
        return "0 branches"
    if n == 1:
        return f"1 branch: {names[0]}"
    return f"{n} branches: {', '.join(names)}"
