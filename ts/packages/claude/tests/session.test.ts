import { describe, it, expect } from "vitest";
import { HaloSession } from "../src/session.js";

const big = "x".repeat(2000); // pads a value past the carve inline threshold so it splits per key

function customer(monthly: number) {
  return {
    income: { monthly, currency: "USD" },
    debts: { monthly: 2604, currency: "USD" },
    name: "Jane Smith",
    notes: big,
  };
}

describe("HaloSession.ingest + navigate", () => {
  it("encodes a result into a navigable map and round-trips a leaf", async () => {
    const s = new HaloSession({ now: () => "T" });
    const { id } = await s.ingest("get_customer", {}, customer(4200));
    expect(id).toBe("m1"); // no scalar arg -> synthetic id

    const branch = await s.walk(`${id}.get_customer`);
    expect(Object.keys(branch.branches).sort()).toEqual(["debts", "income", "name", "notes"]);

    const got = await s.fetch([`${id}.get_customer.income`, `${id}.get_customer.debts`]);
    expect(got[`${id}.get_customer.income`]).toEqual({ ok: true, value: { monthly: 4200, currency: "USD" } });
    expect(got[`${id}.get_customer.debts`]).toEqual({ ok: true, value: { monthly: 2604, currency: "USD" } });
  });

  it("stamps source (id/tool/args/ts) without affecting the content hash", async () => {
    const s = new HaloSession({ now: () => "2026-06-03T00:00:00Z" });
    const a = await s.ingest("t", {}, customer(1)); // m1
    const b = await s.ingest("t", {}, customer(1)); // m2, identical content
    expect(a.id).toBe("m1");
    expect(b.id).toBe("m2");
    expect(a.envelope.root).toBe(b.envelope.root); // source is never hashed
    expect(a.envelope.source).toEqual({ id: "m1", tool: "t", args: {}, ts: "2026-06-03T00:00:00Z" });
  });
});

describe("HaloSession entity accumulation (one entity, one map)", () => {
  it("folds detail calls sharing an argument value into one growing map", async () => {
    const s = new HaloSession();
    const first = await s.ingest("get_customer", { id: 7 }, customer(5000));
    const second = await s.ingest("get_appointments", { customerId: 7 }, [
      { when: "2026-07-01", kind: "checkup" },
      { when: "2026-08-01", kind: "followup" },
    ]);

    expect(first.id).toBe("7");
    expect(second.id).toBe("7"); // same entity -> same map

    // The root view (already in the envelope) carries both endpoints' branches.
    expect(Object.keys(second.envelope.view.branches).sort()).toEqual([
      "get_appointments",
      "get_customer",
    ]);
    // A sub-branch is navigable with a map-scoped ref.
    const customerBranch = await s.walk("7.get_customer");
    expect(Object.keys(customerBranch.branches).sort()).toEqual(["debts", "income", "name", "notes"]);

    const got = await s.fetch(["7.get_appointments", "7.get_customer.income"]);
    expect(got["7.get_appointments"]).toEqual({
      ok: true,
      value: [
        { when: "2026-07-01", kind: "checkup" },
        { when: "2026-08-01", kind: "followup" },
      ],
    });
    expect(got["7.get_customer.income"]).toEqual({ ok: true, value: { monthly: 5000, currency: "USD" } });
  });

  it("resolves refs across several maps in one batch", async () => {
    const s = new HaloSession();
    await s.ingest("get_customer", { id: 1 }, customer(100));
    await s.ingest("get_customer", { id: 2 }, customer(200));
    const got = await s.fetch(["1.get_customer.income", "2.get_customer.income"]);
    expect(got["1.get_customer.income"]).toEqual({ ok: true, value: { monthly: 100, currency: "USD" } });
    expect(got["2.get_customer.income"]).toEqual({ ok: true, value: { monthly: 200, currency: "USD" } });
  });
});

describe("HaloSession before any map exists", () => {
  it("fetch returns per-ref UnknownHandle and walk throws", async () => {
    const s = new HaloSession();
    expect(await s.fetch(["m1.x"])).toEqual({ "m1.x": { ok: false, error: "UnknownHandle" } });
    await expect(s.walk("m1.x")).rejects.toThrow();
  });
});
