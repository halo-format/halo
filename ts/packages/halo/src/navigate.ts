// navigate: open(envelope, store) -> Navigator{ walk, fetch, fetchMany, root }, plus the free
// walk/fetch/fetchMany low-level path.
//
// Every read verifies: read bytes, recompute the hash under the bound alg, compare to the requested
// handle, and only then decode. That single check is what makes the store untrusted — substituted
// or corrupted bytes fail at the moment they are read, before their contents are used, and the
// guarantee propagates from the verified root down every branch to every leaf (the trust chain).
//
// walk returns a branch's summary + child handles (never leaf data); fetch returns one verified
// leaf; fetchMany verifies several in one call with per-ref results, so one unknown or tampered
// entry never sinks the batch. The Navigator additionally resolves map-scoped refs (e.g. m1.income
// or income / income.monthly against the opened envelope) to handles before verifying; raw handles
// always work and need no registration.

import type { Alg, Handle, JsonValue } from "./types.js";
import type { Store } from "./store.js";
import type { HaloEnvelope } from "./envelope.js";
import { decode, isBranch, isLeaf, branchNode, nodeHandle, type Node } from "./node.js";
import { hashBytes } from "./hash.js";
import { HaloError, UnknownHandle, HashMismatch, WrongKind } from "./errors.js";

export type WalkResult = { summary: string; branches: Record<string, Handle> };
export type FetchResult = { ok: true; value: JsonValue } | { ok: false; error: string };

function isRawHandle(ref: string): boolean {
  return ref.startsWith("h:");
}

// Read a handle's bytes and verify them against it before decoding. The load-bearing check.
async function readVerified(handle: Handle, store: Store, alg: Alg): Promise<Node> {
  const bytes = await store.get(handle); // throws UnknownHandle if absent
  if (hashBytes(bytes, alg) !== handle) throw new HashMismatch(handle);
  return decode(bytes);
}

async function getManyBytes(store: Store, handles: Handle[]): Promise<(Uint8Array | undefined)[]> {
  if (store.getMany) return store.getMany(handles);
  return Promise.all(
    handles.map(async (h) => {
      try {
        return await store.get(h);
      } catch (e) {
        if (e instanceof UnknownHandle) return undefined;
        throw e;
      }
    }),
  );
}

/** Verified walk of a branch handle: returns its summary and child handles, never leaf data. */
export async function walk(handle: Handle, store: Store, alg: Alg = "sha256"): Promise<WalkResult> {
  const node = await readVerified(handle, store, alg);
  if (!isBranch(node)) throw new WrongKind(`walk expects a branch: ${handle}`);
  return { summary: node.summary, branches: node.branches };
}

/** Verified fetch of a leaf handle: returns its value. */
export async function fetch(handle: Handle, store: Store, alg: Alg = "sha256"): Promise<JsonValue> {
  const node = await readVerified(handle, store, alg);
  if (!isLeaf(node)) throw new WrongKind(`fetch expects a leaf: ${handle}`);
  return node.value;
}

// Verify a batch of already-resolved (ref -> handle) pairs. Each entry is checked independently:
// missing bytes -> UnknownHandle, bad hash -> HashMismatch, branch where a leaf was asked ->
// WrongKind. One backend round trip when the store supports getMany.
async function verifyBatch(
  present: { ref: string; handle: Handle }[],
  store: Store,
  alg: Alg,
): Promise<Record<string, FetchResult>> {
  const out: Record<string, FetchResult> = {};
  const byteses = await getManyBytes(
    store,
    present.map((p) => p.handle),
  );
  present.forEach((p, j) => {
    const bytes = byteses[j];
    if (bytes === undefined) out[p.ref] = { ok: false, error: "UnknownHandle" };
    else if (hashBytes(bytes, alg) !== p.handle) out[p.ref] = { ok: false, error: "HashMismatch" };
    else {
      const node = decode(bytes);
      out[p.ref] = isLeaf(node)
        ? { ok: true, value: node.value }
        : { ok: false, error: "WrongKind" };
    }
  });
  return out;
}

/** Verified batch fetch over raw handles (the low-level path; each ref is treated as a handle). */
export async function fetchMany(
  refs: string[],
  store: Store,
  alg: Alg = "sha256",
): Promise<Record<string, FetchResult>> {
  return verifyBatch(
    refs.map((r) => ({ ref: r, handle: r })),
    store,
    alg,
  );
}

/**
 * A navigator bound to an envelope's algorithm, store, and root. Resolves map-scoped refs and
 * verifies every read. Register additional envelopes (by their `source.id`) to resolve refs across
 * several maps in one session, e.g. `m1.income` vs `m2.income`.
 */
export class Navigator {
  readonly root: Handle;
  private readonly alg: Alg;
  private readonly registry = new Map<string, HaloEnvelope>();

  constructor(
    private readonly primary: HaloEnvelope,
    private readonly store: Store,
  ) {
    this.alg = primary.alg;
    this.root = primary.root;
    this.registerEnvelope(primary);
  }

  private registerEnvelope(env: HaloEnvelope): void {
    if (env.source?.id) this.registry.set(env.source.id, env);
  }

  /** Register another envelope so its `mapId.branch` refs resolve in this session. */
  register(env: HaloEnvelope): this {
    this.registerEnvelope(env);
    return this;
  }

  /** Resolve a ref (raw handle, `mapId.branch[.child...]`, or a path on the opened envelope). */
  async resolve(ref: string): Promise<Handle> {
    if (isRawHandle(ref)) return ref;
    const parts = ref.split(".");
    const first = parts[0] ?? "";
    if (parts.length >= 2 && this.registry.has(first)) {
      const env = this.registry.get(first)!;
      return this.resolvePath(env.view.branches, parts.slice(1), ref);
    }
    return this.resolvePath(this.primary.view.branches, parts, ref);
  }

  private async resolvePath(
    branches: Record<string, Handle>,
    segs: string[],
    ref: string,
  ): Promise<Handle> {
    const head = segs[0];
    if (head === undefined) throw new UnknownHandle(`empty ref: ${ref}`);
    let handle = branches[head];
    if (handle === undefined) throw new UnknownHandle(`unknown ref: ${ref}`);
    for (let i = 1; i < segs.length; i++) {
      const node = await readVerified(handle, this.store, this.alg);
      if (!isBranch(node)) throw new WrongKind(`ref descends into a leaf: ${ref}`);
      const next = node.branches[segs[i]!];
      if (next === undefined) throw new UnknownHandle(`unknown ref: ${ref}`);
      handle = next;
    }
    return handle;
  }

  async walk(ref: string): Promise<WalkResult> {
    return walk(await this.resolve(ref), this.store, this.alg);
  }

  async fetch(ref: string): Promise<JsonValue> {
    return fetch(await this.resolve(ref), this.store, this.alg);
  }

  async fetchMany(refs: string[]): Promise<Record<string, FetchResult>> {
    const out: Record<string, FetchResult> = {};
    const present: { ref: string; handle: Handle }[] = [];
    await Promise.all(
      refs.map(async (r) => {
        try {
          present.push({ ref: r, handle: await this.resolve(r) });
        } catch (e) {
          // A resolution failure is surfaced per-entry (with its error name), never thrown.
          out[r] = { ok: false, error: e instanceof HaloError ? e.name : "UnknownHandle" };
        }
      }),
    );
    Object.assign(out, await verifyBatch(present, this.store, this.alg));
    return out;
  }
}

/** Open an envelope into a Navigator, verifying the root. Zero fetches for an honest branch root. */
export async function open(envelope: HaloEnvelope, store: Store): Promise<Navigator> {
  const alg = envelope.alg;
  // The inlined view lets us verify a branch root with no store read: re-hash the reconstructed
  // root node and compare to the claimed root handle.
  const reconstructed = branchNode(envelope.view.summary, envelope.view.branches);
  if (nodeHandle(reconstructed, alg) !== envelope.root) {
    // Either a leaf root (its value is not inlined in the view) or a tampered branch view. Read the
    // real root to tell them apart: a branch here means the view was tampered.
    const node = await readVerified(envelope.root, store, alg);
    if (isBranch(node)) {
      throw new HashMismatch(`envelope view does not match root: ${envelope.root}`);
    }
    // leaf root: nothing branch-navigable; a later fetch(root) re-verifies it.
  }
  return new Navigator(envelope, store);
}
