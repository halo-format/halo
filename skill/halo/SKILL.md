---
name: halo
description: >
  Use when a tool or API returns a large or verbose result and you do not need
  all of it, or when you need a verifiable record of which parts of a result a
  decision used. Encodes the result into a small content-addressed map (a halo)
  so only the map enters context and you fetch individual fields on demand,
  verified on read. Triggers on large JSON tool outputs, big API responses,
  keeping context lean, and auditable tool data.
---

# Halo: lazy, verified navigation of large tool results

When a tool or API returns a large result, do not read the whole payload into
your reasoning. Route it through the helper in `scripts/halo.ts` so only a small
map enters context.

## When to use this

- A tool result is large, or you only need a few fields from it.
- You are about to make a decision and want a record of exactly which fields it
  rested on.

If a result is already small and you need all of it, skip this. Halo is for the
cases where the payload is bigger than what you actually need.

## Workflow

1. Take the raw result and pass it to `encode(result)`. You get back a halo: a
   short summary plus a set of named handles. The full data now lives in local
   scratch, not in your context.
2. Read the summary and the handle names. Decide which branches you actually
   need for the task.
3. Collect every ref you need and fetch them together in one `fetchMany([...])`
   call (use `fetch(ref)` only for a single leaf). Do not fetch one at a time:
   each call is a separate round trip, so batching the refs for a step into a
   single call is much faster. Each value is verified automatically; a
   `HashMismatch` on any entry means that data was altered and must not be
   trusted.
4. You can address a branch by its readable ref (for example `m1.income`)
   instead of copying the long handle.
5. Reason over only the values you fetched. Do not fetch branches you do not
   need.
6. If a branch is itself large, call `walk(handle)` to see its sub-structure and
   summary before fetching deeper.
7. If several results are about the same thing (for example a customer looked up
   then their appointments), they may already be folded into one growing map.
   Navigate that single map rather than expecting a separate one per call.

## What this buys you

- Context stays small: only the map and the leaves you opened are ever in
  context, not the whole payload.
- The handles you fetched are a precise record of what you used. If an audit
  layer is enabled, that record is captured automatically.

See `reference/format.md` for the node and envelope format if you need the
details.
