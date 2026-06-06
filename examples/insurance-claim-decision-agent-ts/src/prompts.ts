// Agent identity + model/prompt provenance. CLAUDE.md is the single source of
// truth for the operating instructions (shared verbatim with the Python example),
// so the canonical prompt_version_hash is sha256 over its raw bytes — a recorded
// decision pins exactly which prompt produced it, byte-identical across ports.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const CLAUDE_MD = join(__dirname, "..", "CLAUDE.md");

const FALLBACK =
  "You are the Insurance Claim Decision Agent. Act only through the payer tools. " +
  "The model orchestrates and reasons; the deterministic engine computes the money; " +
  "a human owns every denial, reduction, or pend.";

let bytes: Buffer;
try {
  bytes = readFileSync(CLAUDE_MD);
} catch {
  bytes = Buffer.from(FALLBACK, "utf8");
}

export const AGENT_ID = "insurance-claim-decision-agent";
export const MODEL_VERSION = process.env.AGENT_MODEL || "claude-sonnet-4-6";
export const SYSTEM_PROMPT = bytes.toString("utf8");
export const PROMPT_VERSION_HASH = "sha256:" + createHash("sha256").update(bytes).digest("hex");
