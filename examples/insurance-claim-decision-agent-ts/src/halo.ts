// ============================================================================
// Halo for the raw-API loop — the encode step the Agent SDK adapter does via a
// PostToolUse hook, driven by hand here (the raw Messages API has no hooks).
//
// A large tool result is encoded into a content-addressed store; the model is
// handed a SHAPE MAP (root kind + per-field ref/kind/preview) instead of the
// payload, and pulls back the fields it needs with halo_fetch — verified on read.
// Built on the published @halo-format/halo core (encode / open / MemoryStore),
// so handles are byte-identical to every other Halo port.
// ============================================================================
import {
  encode,
  open,
  MemoryStore,
  decode,
  isLeaf,
  type HaloEnvelope,
  type Store,
} from "@halo-format/halo";

const PREVIEW_MAX = 80;

export class HaloSession {
  store: Store = new MemoryStore();
  maps = new Map<string, HaloEnvelope>(); // id -> envelope, for ref resolution

  /** Encode a tool result and return the shape map the model should see in its place. */
  async ingest(id: string, value: unknown): Promise<string> {
    const { envelope } = await encode(value as any, { store: this.store });
    this.maps.set(id, envelope);
    return await this.shapeMap(id, envelope);
  }

  /** Verified batch fetch. ref is "id.field"; a leaf returns its value, a branch its sub-shape. */
  async fetch(refs: string[]): Promise<Record<string, unknown>> {
    const out: Record<string, unknown> = {};
    for (const ref of refs) {
      const dot = ref.indexOf(".");
      const id = dot >= 0 ? ref.slice(0, dot) : ref;
      const field = dot >= 0 ? ref.slice(dot + 1) : "";
      const env = this.maps.get(id);
      if (!env) {
        out[ref] = { ok: false, error: "UnknownMap" };
        continue;
      }
      try {
        const nav = await open(env, this.store);
        out[ref] = { ok: true, value: field ? await nav.fetch(field) : await nav.fetch(id) };
      } catch (e: any) {
        out[ref] = { ok: false, error: String(e?.message ?? e) };
      }
    }
    return out;
  }

  private async shapeMap(id: string, env: HaloEnvelope): Promise<string> {
    const branches = env.view.branches;
    const names = Object.keys(branches).sort();
    const lines: string[] = [];
    for (const name of names) {
      const node = decode(await this.store.get(branches[name]));
      let kind: string;
      let preview: string;
      if (isLeaf(node)) {
        const v = (node as any).value;
        kind = Array.isArray(v) ? `array[${v.length}]` : typeof v;
        preview = bounded(JSON.stringify(v));
      } else {
        const childNames = Object.keys((node as any).branches);
        const arrayLike = childNames.length > 0 && childNames.every((n) => /^\d+$/.test(n));
        kind = `[branch] ${arrayLike ? "array" : "object"}{${childNames.length}}`;
        preview = "↳ " + childNames.slice(0, 10).join(", ") + (childNames.length > 10 ? ", …" : "");
      }
      lines.push(`  ${id}.${name}  ${kind}  ${preview}`);
    }
    return (
      `[halo] map "${id}" — object, ${names.length} fields, stored out of context. ` +
      `Pull only the fields you need with ONE halo_fetch call (refs like ["${id}.${names[0]}"]); ` +
      `each value is verified on read.\nFields:\n${lines.join("\n")}`
    );
  }
}

function bounded(s: string): string {
  return s.length > PREVIEW_MAX ? s.slice(0, PREVIEW_MAX) + "…" : s;
}
