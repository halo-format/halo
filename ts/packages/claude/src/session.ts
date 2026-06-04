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
  type Store,
  type WalkResult,
  type FetchResult,
  type Alg,
  MemoryStore,
  Navigator,
  encode,
  branchNode,
  serialize,
  deriveSummary,
  decode,
  buildEnvelope,
} from "@halo-format/halo";
import { argJoin, type KeyOf } from "./accumulate.js";

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

  /** Verified walk of a branch ref (raw handle or `mapId.branch[.child]`). */
  async walk(ref: string): Promise<WalkResult> {
    if (!this.navigator) throw new Error("no halo maps in this session yet");
    return this.navigator.walk(ref);
  }

  /** Verified batch fetch; one bad ref never sinks the others (per-ref ok/error). */
  async fetch(refs: string[]): Promise<Record<string, FetchResult>> {
    if (!this.navigator) {
      const out: Record<string, FetchResult> = {};
      for (const r of refs) out[r] = { ok: false, error: "UnknownHandle" };
      return out;
    }
    return this.navigator.fetchMany(refs);
  }
}
