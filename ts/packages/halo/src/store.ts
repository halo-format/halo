// store: the Store interface plus MemoryStore and FileStore.
//
//   put(bytes) -> Handle  (content-addressed, idempotent, stores once)
//   get(handle) -> Bytes  (throws UnknownHandle if absent)
//   has(handle) -> boolean
//   getMany?(handles) -> (Bytes | undefined)[]   (optional multi-get)
//
// Untrusted by design: every read verifies, so a buggy/hostile store cannot substitute data
// undetected. MemoryStore = in-process Map (the light deployment); FileStore = one file per
// handle under a dir (cross-step persistence in a sandbox).

import { mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import type { Alg, Handle } from "./types.js";
import { hashBytes } from "./hash.js";
import { UnknownHandle, StoreError } from "./errors.js";

export interface Store {
  put(bytes: Uint8Array): Promise<Handle>;
  get(handle: Handle): Promise<Uint8Array>;
  has(handle: Handle): Promise<boolean>;
  getMany?(handles: Handle[]): Promise<(Uint8Array | undefined)[]>;
}

// A handle is "h:" + hex; the hex alone is the on-disk filename for FileStore.
function hexOf(handle: Handle): string {
  return handle.startsWith("h:") ? handle.slice(2) : handle;
}

/** In-process content-addressed store — the light deployment and the default for tests. */
export class MemoryStore implements Store {
  private map = new Map<Handle, Uint8Array>();
  constructor(private readonly alg: Alg = "sha256") {}

  async put(bytes: Uint8Array): Promise<Handle> {
    const handle = hashBytes(bytes, this.alg);
    // Idempotent + immutable: first writer wins, identical content is a no-op.
    if (!this.map.has(handle)) this.map.set(handle, bytes);
    return handle;
  }

  async get(handle: Handle): Promise<Uint8Array> {
    const bytes = this.map.get(handle);
    if (bytes === undefined) throw new UnknownHandle(handle);
    return bytes;
  }

  async has(handle: Handle): Promise<boolean> {
    return this.map.has(handle);
  }

  async getMany(handles: Handle[]): Promise<(Uint8Array | undefined)[]> {
    return handles.map((h) => this.map.get(h));
  }

  /** Node count — for tests and diagnostics; not part of the Store interface. */
  get size(): number {
    return this.map.size;
  }
}

/** One file per handle under a directory — cross-step persistence inside a sandbox. */
export class FileStore implements Store {
  constructor(private readonly dir: string, private readonly alg: Alg = "sha256") {
    try {
      mkdirSync(dir, { recursive: true });
    } catch (e) {
      throw new StoreError(`could not create store dir ${dir}: ${(e as Error).message}`);
    }
  }

  private pathFor(handle: Handle): string {
    return join(this.dir, hexOf(handle));
  }

  async put(bytes: Uint8Array): Promise<Handle> {
    const handle = hashBytes(bytes, this.alg);
    const path = this.pathFor(handle);
    if (!existsSync(path)) writeFileSync(path, bytes); // immutable: never overwrite
    return handle;
  }

  async get(handle: Handle): Promise<Uint8Array> {
    try {
      return readFileSync(this.pathFor(handle));
    } catch (e) {
      if ((e as NodeJS.ErrnoException).code === "ENOENT") throw new UnknownHandle(handle);
      throw new StoreError(`could not read ${handle}: ${(e as Error).message}`);
    }
  }

  async has(handle: Handle): Promise<boolean> {
    return existsSync(this.pathFor(handle));
  }

  async getMany(handles: Handle[]): Promise<(Uint8Array | undefined)[]> {
    return Promise.all(
      handles.map(async (h) => {
        try {
          return await this.get(h);
        } catch (e) {
          if (e instanceof UnknownHandle) return undefined;
          throw e;
        }
      }),
    );
  }
}
