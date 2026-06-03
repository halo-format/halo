// envelope: build + verify the root envelope.
//
//   { halo: "1", alg, root, view: { summary, branches }, source? }
//
// view inlines the root branch so a consumer navigates with zero fetches and can verify by
// re-hashing the reconstructed root against `root`. `source` is envelope-only identification
// metadata (id, tool, args, ts) and is NEVER hashed — it cannot affect handles or dedup.

export {};
