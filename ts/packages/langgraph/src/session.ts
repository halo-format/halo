// HaloSession holds the one piece of shared state in the adapter — the store and the per-entity map
// registry — and exposes the three operations the hook and the navigation tools sit on:
//
//   ingest(toolName, toolInput, value) -> envelope   (producer; folds into the entity's map)
//   walk(ref)                          -> branch summary + child handles
//   fetch(refs[])                      -> verified leaves, per-ref
//
// One entity, one map (SDK architecture, Section 9.1): keyOf decides which calls share a map id. A
// first call for an id `encode`s `{ [tool]: value }`; later calls for the same id `extend` that
// map's root with a branch named after the tool, so a customer assembled across several endpoints
// becomes one growing map rather than several fragments. Because extend reuses unchanged child
// handles and retains the prior root, each entity map also carries its own version history for free.
//
// Every read is verified by the core Navigator, so the store stays untrusted. The Navigator resolves
// map-scoped refs (`m1.income`, `123.get_appointments`) against the registered envelopes; raw
// handles always work without registration.

import {
  type HaloEnvelope,
  type Handle,
  type JsonValue,
  type Node,
  type Store,
  type WalkResult,
  type Alg,
  MemoryStore,
  Navigator,
  HashMismatch,
  WrongKind,
  encode,
  branchNode,
  serialize,
  deriveSummary,
  decode,
  isBranch,
  isLeaf,
  hashBytes,
  buildEnvelope,
} from "@halo-format/halo";
import { argJoin, type KeyOf } from "./accumulate.js";
import { type FieldHint, shapeOf, previewOf } from "./serialize.js";

/** A short branch label for an accumulated tool: strip the `mcp__<server>__` prefix. */
function branchName(toolName: string): string {
  if (toolName.startsWith("mcp__")) {
    const parts = toolName.split("__");
    if (parts.length >= 3) return parts.slice(2).join("__");
  }
  return toolName;
}

export type SessionOptions = {
  store?: Store;
  keyOf?: KeyOf;
  alg?: Alg;
  now?: () => string;
};

export type IngestResult = { envelope: HaloEnvelope; id: string };

/**
 * One batch-fetch entry. A leaf ref returns its value. A ref that lands on a BRANCH does not fail —
 * it returns that branch's sub-shape (its child refs + hints), so the single halo_fetch tool both
 * pulls leaves and expands branches and the model never needs a separate walk tool. A bad ref is a
 * per-entry error and never sinks the rest of the batch.
 */
export type FetchEntry =
  | { ok: true; value: JsonValue }
  | { ok: true; kind: "branch"; note: string; fields: FieldHint[] }
  | { ok: false; error: string };

export class HaloSession {
  readonly store: Store;
  private readonly keyOf: KeyOf;
  private readonly alg: Alg;
  private readonly now: () => string;

  // id -> latest envelope for that entity, for ref resolution and accumulation.
  private readonly maps = new Map<string, HaloEnvelope>();
  // id -> { branchName: subtreeRootHandle }: the per-tool trees folded into each entity map.
  private readonly entityTools = new Map<string, Record<string, Handle>>();
  // One navigator, seeded by the first map and extended with register() as maps appear.
  private navigator: Navigator | null = null;
  private synthetic = 0;

  constructor(opts: SessionOptions = {}) {
    this.store = opts.store ?? new MemoryStore();
    this.keyOf = opts.keyOf ?? argJoin;
    this.alg = opts.alg ?? "sha256";
    this.now = opts.now ?? (() => new Date().toISOString());
  }

  /**
   * Encode a tool result into the store and return the resulting envelope.
   *
   * A map's FIRST result is encoded flat — the value's own fields become the top-level branches, so
   * the model sees them in the envelope and can batch-fetch leaves with no extra walk. Only when a
   * SECOND tool result accumulates into the same entity map (per keyOf) do we namespace each tool's
   * tree under its (short) name, since then the field names would otherwise collide.
   */
  async ingest(toolName: string, toolInput: unknown, value: JsonValue): Promise<IngestResult> {
    const id = this.keyOf(toolName, toolInput) ?? `m${++this.synthetic}`;
    const opts = { store: this.store, alg: this.alg };

    // Encode the value's own tree once; reuse its root as this tool's subtree under the entity.
    const sub = await encode(value, opts);
    const tools = this.entityTools.get(id) ?? {};
    tools[branchName(toolName)] = sub.handle;
    this.entityTools.set(id, tools);

    let envelope: HaloEnvelope;
    if (Object.keys(tools).length === 1) {
      // Single result: the map IS the value's tree — fields are top-level, no walk needed.
      envelope = sub.envelope;
    } else {
      // Accumulation: namespace each tool's tree under its name (reusing every subtree handle; only
      // the new root node is stored).
      const root = await this.store.put(serialize(branchNode(deriveSummary(null, tools), tools)));
      envelope = buildEnvelope(root, decode(await this.store.get(root)), this.alg);
    }

    // source identifies the map and traces it to the call; it is envelope-only and never hashed.
    envelope.source = { id, tool: toolName, args: toolInput as JsonValue, ts: this.now() };
    this.maps.set(id, envelope);
    this.registerEnvelope(envelope);
    return { envelope, id };
  }

  private registerEnvelope(envelope: HaloEnvelope): void {
    if (this.navigator) this.navigator.register(envelope);
    else this.navigator = new Navigator(envelope, this.store);
  }

  /** Verified walk of a branch ref (raw handle or `mapId.branch[.child]`). Internal — not a tool. */
  async walk(ref: string): Promise<WalkResult> {
    if (!this.navigator) throw new Error("no halo maps in this session yet");
    return this.navigator.walk(ref);
  }

  /**
   * Verified batch fetch — the single navigation surface. Leaves return their value; a ref that
   * lands on a branch returns the branch's sub-shape instead of a WrongKind error, so one tool
   * covers both pulling and expanding. One bad ref never sinks the others.
   */
  async fetch(refs: string[]): Promise<Record<string, FetchEntry>> {
    const out: Record<string, FetchEntry> = {};
    if (!this.navigator) {
      for (const r of refs) out[r] = { ok: false, error: "UnknownHandle" };
      return out;
    }
    // The core batch verifies every leaf in one round trip; branch refs come back WrongKind, which
    // we turn into a sub-shape expansion below rather than surfacing as an error.
    const base = await this.navigator.fetchMany(refs);
    await Promise.all(
      refs.map(async (r) => {
        const res = base[r]!;
        if (res.ok) {
          out[r] = { ok: true, value: res.value };
        } else if (res.error === "WrongKind") {
          try {
            out[r] = await this.expand(r);
          } catch {
            out[r] = res;
          }
        } else {
          out[r] = res;
        }
      }),
    );
    return out;
  }

  /**
   * Describe an envelope's top-level fields for the shape map the model sees: one FieldHint per
   * branch, classified (leaf vs branch) and previewed by reading each child node. Sorted by ref so
   * the listing order is deterministic (matching the structural summary's sorted names).
   */
  async describe(envelope: HaloEnvelope): Promise<FieldHint[]> {
    const id = envelope.source?.id ?? "";
    const hints = await Promise.all(
      Object.entries(envelope.view.branches).map(async ([name, handle]) => {
        const ref = id ? `${id}.${name}` : name;
        try {
          return await this.hintFor(ref, handle);
        } catch {
          return { ref, kind: "leaf" as const, shape: "?" };
        }
      }),
    );
    return hints.sort((a, b) => (a.ref < b.ref ? -1 : a.ref > b.ref ? 1 : 0));
  }

  // Expand a branch ref into a FetchEntry carrying its child refs + hints (the in-fetch fallback so
  // a mis-fetched branch self-corrects in the same call instead of dead-ending on WrongKind).
  private async expand(ref: string): Promise<FetchEntry> {
    const handle = await this.navigator!.resolve(ref);
    const node = await this.read(handle);
    if (!isBranch(node)) throw new WrongKind(`expand expects a branch: ${ref}`);
    const fields = await Promise.all(
      Object.entries(node.branches).map(([name, h]) => this.hintFor(`${ref}.${name}`, h)),
    );
    fields.sort((a, b) => (a.ref < b.ref ? -1 : a.ref > b.ref ? 1 : 0));
    return {
      ok: true,
      kind: "branch",
      note: "This ref is a branch, not a value. halo_fetch the leaf refs below to read it.",
      fields,
    };
  }

  // Classify one child handle into a FieldHint: a leaf gets its shape + a bounded value preview; a
  // branch gets a "[branch]" shape and its child names as the preview (one level, bounded).
  private async hintFor(ref: string, handle: Handle): Promise<FieldHint> {
    const node = await this.read(handle);
    if (isLeaf(node)) {
      return { ref, kind: "leaf", shape: shapeOf(node.value), preview: previewOf(node.value) };
    }
    const childNames = Object.keys(node.branches);
    const arrayLike = childNames.length > 0 && childNames.every((n) => /^\d+$/.test(n));
    const shape = `[branch] ${arrayLike ? "array" : "object"}{${childNames.length}}`;
    const shown = childNames.slice(0, MAX_CHILD_NAMES).join(", ");
    const more = childNames.length > MAX_CHILD_NAMES ? ", …" : "";
    return { ref, kind: "branch", shape, preview: `↳ ${shown}${more}` };
  }

  // A verified read of a handle from the store: re-hash the bytes under the bound alg before decode,
  // so the shape map can never describe substituted bytes. Same check the Navigator makes on fetch.
  private async read(handle: Handle): Promise<Node> {
    const bytes = await this.store.get(handle);
    if (hashBytes(bytes, this.alg) !== handle) throw new HashMismatch(handle);
    return decode(bytes);
  }
}

const MAX_CHILD_NAMES = 10;
