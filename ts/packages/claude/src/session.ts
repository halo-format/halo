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
  type JsonValue,
  type Store,
  type WalkResult,
  type FetchResult,
  type Alg,
  MemoryStore,
  Navigator,
  encode,
  extend,
} from "@halo-format/halo";
import { argJoin, type KeyOf } from "./accumulate.js";

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
   * Encode a tool result into the store and return the resulting envelope. Related calls (per keyOf)
   * fold into one entity map; unrelated calls each get a fresh map id `m1`, `m2`, ...
   */
  async ingest(toolName: string, toolInput: unknown, value: JsonValue): Promise<IngestResult> {
    const id = this.keyOf(toolName, toolInput) ?? `m${++this.synthetic}`;
    const prior = this.maps.get(id);
    const opts = { store: this.store, alg: this.alg };

    const { envelope } = prior
      ? await extend(prior.root, toolName, value, opts) // fold into the entity's existing map
      : await encode({ [toolName]: value }, opts); // first call for this entity, named by endpoint

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
