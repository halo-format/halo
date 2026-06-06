// Entity accumulation policy: which calls fold into one growing map (SDK architecture, Section 9.1).
//
// keyOf(toolName, toolInput) returns an entity key, or null to give the call its own fresh map. The
// default, argJoin, keys on the first scalar argument value, so normalized REST detail calls about
// one entity group together: get_customer({id:123}) and get_appointments({customerId:123}) both key
// on 123 and fold into one map, while search({query:"smith"}) keys on "smith" and stays its own list
// map until the first detail call. It keys on the argument VALUE, not the field name or any result
// id, which is what lets a list result land under the entity instead of fragmenting.
//
// argJoin's one real gap is value collision across entity types (customer 123 vs invoice 123, both
// passing 123). That is the single thing a generic heuristic cannot resolve alone; supply a domain
// keyOf (e.g. one that prefixes the resource type) when it matters, as it usually does for money or
// medical data.

import type { JsonValue } from "@halo-format/halo";

export type KeyOf = (toolName: string, toolInput: unknown) => string | null;

// A short scalar (number, or string up to this many chars) is treated as an id-like argument worth
// grouping on. Longer strings are typically free text (a query, a body) and are skipped.
const MAX_KEY_STRING_LENGTH = 128;

function scalarKey(value: unknown): string | null {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "string" && value.length > 0 && value.length <= MAX_KEY_STRING_LENGTH) {
    return value;
  }
  return null;
}

/**
 * Default policy: group by the first scalar argument value. Objects are scanned in key order, arrays
 * in index order; a bare scalar input is its own key. Returns null when no scalar argument is
 * present (e.g. a no-arg call), so that call gets a fresh synthetic map id.
 */
export const argJoin: KeyOf = (_toolName, toolInput) => {
  const direct = scalarKey(toolInput);
  if (direct !== null) return direct;
  if (Array.isArray(toolInput)) {
    for (const item of toolInput) {
      const k = scalarKey(item);
      if (k !== null) return k;
    }
    return null;
  }
  if (toolInput && typeof toolInput === "object") {
    for (const value of Object.values(toolInput as Record<string, JsonValue>)) {
      const k = scalarKey(value);
      if (k !== null) return k;
    }
  }
  return null;
};
