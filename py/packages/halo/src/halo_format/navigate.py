"""open_(envelope, store) -> Navigator(walk, fetch, fetch_many, root).

Every read verifies: read bytes, recompute hash under the bound alg, compare to the requested
handle, only then decode. walk returns a branch summary + child handles (no leaf data); fetch
returns one verified leaf; fetch_many resolves+verifies several refs in one call with per-ref
results. Accepts raw handles or map-scoped refs (m1.income).
"""
