// navigate: open(envelope, store) -> Navigator{ walk, fetch, fetchMany, root }.
//
// Every read verifies: read bytes, recompute hash under the bound alg, compare to the
// requested handle, only then decode. walk returns a branch summary + child handles (no leaf
// data); fetch returns one verified leaf; fetchMany resolves+verifies several refs in one
// call, per-ref results so one bad entry does not sink the batch. Accepts raw handles or
// map-scoped refs (m1.income), resolved against registered envelopes.

export {};
