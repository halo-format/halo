// The Model wrapper / rewriteInput: it rewrites a large function_call_result output into a shape map,
// reads the call arguments from the matching function_call item (for keyOf), excludes the navigation
// tool's own output (the mandatory no-re-encode rule), passes small/already-encoded results through,
// and — because it fires every model call over the whole list — stays idempotent across firings via a
// per-callId cache.

import { describe, it, expect } from "vitest";
import { HaloSession } from "../src/session.js";
import { rewriteInput, wrapModel } from "../src/model-wrapper.js";

const BIG = JSON.stringify({
  profile: { income: { monthly: 4200 }, debts: { monthly: 2604 } },
  filler: "x".repeat(3000),
});

function call(callId: string, name: string, args: string) {
  return { type: "function_call", callId, name, arguments: args };
}
function result(callId: string, name: string, text: string) {
  return { type: "function_call_result", callId, name, output: { type: "text", text } };
}

function session() {
  return new HaloSession({ now: () => "T" });
}

function outputText(items: unknown[], callId: string): string {
  const it = (items as { type?: string; callId?: string; output?: { text?: string } }[]).find(
    (x) => x.type === "function_call_result" && x.callId === callId,
  );
  if (!it?.output?.text) throw new Error("no output for " + callId);
  return it.output.text;
}

describe("rewriteInput", () => {
  it("rewrites a large result into a shape map and stores the payload", async () => {
    const s = session();
    const cache = new Map<string, string>();
    const input = [call("c1", "bureau", '{"applicant":99}'), result("c1", "bureau", BIG)];
    const out = (await rewriteInput(s, cache, 2048, input)) as unknown[];

    expect(outputText(out, "c1")).toMatch(/^\[halo\] map "99"/); // argJoin keyed on applicant=99
    const fetched = await s.fetch(["99.profile"]);
    expect(fetched["99.profile"]!.ok).toBe(true);
  });

  it("leaves the function_call item untouched", async () => {
    const s = session();
    const c = call("c1", "bureau", '{"applicant":99}');
    const out = (await rewriteInput(s, new Map(), 2048, [c, result("c1", "bureau", BIG)])) as unknown[];
    expect(out[0]).toBe(c);
  });

  it("excludes the navigation tool's own output (mandatory)", async () => {
    const s = session();
    const input = [call("c1", "halo_fetch", '{"refs":["x"]}'), result("c1", "halo_fetch", BIG)];
    const out = (await rewriteInput(s, new Map(), 2048, input)) as unknown[];
    expect(outputText(out, "c1")).toBe(BIG); // untouched
  });

  it("passes a small result through", async () => {
    const s = session();
    const input = [call("c1", "ping", "{}"), result("c1", "ping", '{"ok":true}')];
    const out = (await rewriteInput(s, new Map(), 2048, input)) as unknown[];
    expect(outputText(out, "c1")).toBe('{"ok":true}');
  });

  it("returns the original input array when nothing changes", async () => {
    const s = session();
    const input = [call("c1", "ping", "{}"), result("c1", "ping", "{}")];
    const out = await rewriteInput(s, new Map(), 2048, input);
    expect(out).toBe(input);
  });

  it("passes a string input (first user turn) through unchanged", async () => {
    const s = session();
    const out = await rewriteInput(s, new Map(), 2048, "hello" as never);
    expect(out).toBe("hello");
  });

  it("is idempotent across repeated firings for a synthetic id", async () => {
    // The sharp case: a no-id-arg tool gets a synthetic map id (m1). Without the per-callId cache, a
    // second firing would re-ingest and assign m2, shifting refs the model already saw.
    const s = session();
    const cache = new Map<string, string>();
    const mk = () => [call("c1", "list_logs", "{}"), result("c1", "list_logs", BIG)];

    const first = outputText((await rewriteInput(s, cache, 2048, mk())) as unknown[], "c1");
    expect(first).toMatch(/^\[halo\] map "m1"/);
    const second = outputText((await rewriteInput(s, cache, 2048, mk())) as unknown[], "c1");
    expect(second).toBe(first); // same string, m2 never minted
  });

  it("leaves an already-encoded shape map alone without a cache entry", async () => {
    const s = session();
    const shapeMap = '[halo] map "m1" — object, 2 fields, stored out of context. ...';
    const input = [call("c1", "list_logs", "{}"), result("c1", "list_logs", shapeMap)];
    const out = (await rewriteInput(s, new Map(), 2048, input)) as unknown[];
    expect(outputText(out, "c1")).toBe(shapeMap);
  });

  it("folds shared-id calls into one growing map (entity accumulation)", async () => {
    const s = session();
    const cache = new Map<string, string>();
    const a = JSON.stringify({ id: 123, a: "x".repeat(3000) });
    const b = JSON.stringify({ id: 123, b: "y".repeat(3000) });
    await rewriteInput(s, cache, 2048, [call("c1", "get_customer", '{"id":123}'), result("c1", "get_customer", a)]);
    const out = (await rewriteInput(s, cache, 2048, [
      call("c2", "get_appointments", '{"id":123}'),
      result("c2", "get_appointments", b),
    ])) as unknown[];
    const text = outputText(out, "c2");
    expect(text).toMatch(/^\[halo\] map "123"/);
    expect(text).toContain("get_customer");
    expect(text).toContain("get_appointments");
  });
});

describe("wrapModel", () => {
  it("rewrites request.input before delegating to the underlying model", async () => {
    const s = session();
    const seen: unknown[] = [];
    const fake = {
      async getResponse(req: { input: unknown }) {
        seen.push(req.input);
        return { output: [], usage: {} } as never;
      },
      getStreamedResponse() {
        return (async function* () {})();
      },
    };
    const wrapped = wrapModel(fake as never, s, 2048);
    const input = [call("c1", "bureau", '{"applicant":99}'), result("c1", "bureau", BIG)];
    await wrapped.getResponse({ input } as never);

    const passed = seen[0] as unknown[];
    expect(outputText(passed, "c1")).toMatch(/^\[halo\] map "99"/); // model saw the shape map, not BIG
  });
});
