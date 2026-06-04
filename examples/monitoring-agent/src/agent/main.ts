// ============================================================================
// Live monitoring agent on the Claude Agent SDK (TypeScript).
//
// Registers the `monitoring` MCP server (stdio subprocess), loads the project
// Skills, and runs one monitoring session. Real-world writes block on the
// human approval gate inside the MCP tools — resolve them from another terminal
// with `npm run oncall`.
//
//   npm run agent            (uses the default session prompt)
//   npm run agent -- "..."   (custom instruction)
//
// Uses the Claude Code runtime, so it runs with the local `claude` login or an
// ANTHROPIC_API_KEY. A seeded `monitoring` database must exist.
// ============================================================================
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";
import { randomUUID } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { query } from "@anthropic-ai/claude-agent-sdk";
import { installHalo } from "@halo-format/claude";
import { SYSTEM_PROMPT, MODEL } from "./prompts.js";

try { process.loadEnvFile(); } catch { /* env may come from the shell */ }

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = resolve(__dirname, "..", "..");
const SERVER_PATH = join(PROJECT_ROOT, "src", "mcp", "server.ts");
const TSX_BIN = join(PROJECT_ROOT, "node_modules", ".bin", "tsx");

// HALO here means OUR consumer-side adapter (@halo-format/claude), NOT the server's built-in Halo.
// In both arms the MCP server runs RAW (MONITORING_HALO=0), so the heavy results are full payloads;
// when ADAPTER_ON, installHalo's PostToolUse hook encodes them locally and exposes halo_walk/fetch.
const ADAPTER_ON = ["1", "true", "yes", "on"].includes((process.env.HALO ?? "").toLowerCase());
const FORMAT = (process.env.MONITORING_FORMAT || "json").toLowerCase(); // json | toon
const RUN_LABEL = process.env.RUN_LABEL || (ADAPTER_ON ? "halo" : FORMAT === "toon" ? "toon" : "baseline");

// TOON arm: the server serialises results as TOON (compact, still in context). Tell the model.
const TOON_NOTE = `

NOTE: Tool results are encoded in TOON — a compact, lossless JSON encoding. Nested objects use
indentation; a uniform array is written as \`name[N]{field1,field2,...}:\` followed by one
comma-separated row per item. Read it directly as the full data (no fetching needed).
`;

// The example's prompt bakes in server-side Halo guidance (its own halo_fetch / h:sha256 handles).
// Strip it; the server is raw here. For the adapter arm, substitute guidance for OUR halo_ tools.
const BASE_PROMPT = SYSTEM_PROMPT.replace(/TOOL DISCIPLINE — Halo:[\s\S]*?\n\nFLOW each run:/, "FLOW each run:");
const HALO_GUIDANCE = `TOOL DISCIPLINE — Halo (navigation):
- Large tool results come back as a halo ENVELOPE: { "halo":"1", "view":{ "summary", "branches":{ name: handle } }, "source":{ "id":"<mapId>" } } — the full data is held, verified, out of your context.
- Read view.summary and the branch names, then fetch ONLY the fields a step needs in ONE \`mcp__halo__halo_fetch\` call, passing refs like ["<mapId>.<field>"]. Use \`mcp__halo__halo_walk\` on a ref first only if a branch is itself large. Do not pull whole lists/log windows. Each value is verified.

`;

// Server tools only (the server's own halo_fetch/halo_fetch_many are unused — it runs raw).
const MONITORING_TOOLS = [
  "list_open_issues",
  "get_issue_detail",
  "search_logs",
  "list_incidents",
  "triage_note",
  "declare_incident",
  "acknowledge_incident",
  "resolve_incident",
  "assign_incident",
].map((t) => `mcp__monitoring__${t}`);
const HALO_NAV_TOOLS = ["mcp__halo__halo_walk", "mcp__halo__halo_fetch"];

async function run(userPrompt: string) {
  const sessionId = process.env.AGENT_SESSION_ID || randomUUID();
  const mode = ADAPTER_ON ? "HALO ADAPTER ON" : FORMAT === "toon" ? "TOON (compact, in-context)" : "BASELINE (raw JSON)";
  console.log(`=== Monitoring agent — session ${sessionId} — ${mode} ===\n`);

  const baseOptions = {
    model: MODEL,
    systemPrompt: ADAPTER_ON
      ? BASE_PROMPT.replace("FLOW each run:", HALO_GUIDANCE + "FLOW each run:")
      : FORMAT === "toon"
        ? BASE_PROMPT + TOON_NOTE
        : BASE_PROMPT,
    cwd: PROJECT_ROOT,
    settingSources: ["project" as const], // load project settings
    // Exclude the server's halo-navigation skill (it's for the server's Halo, which is off here).
    skills: ["triage", "diagnose", "incident-response"],
    allowedTools: [...MONITORING_TOOLS, "Skill", ...(ADAPTER_ON ? HALO_NAV_TOOLS : [])],
    // The server runs raw, so its built-in halo_fetch/halo_fetch_many hit an empty store — disallow
    // them so the model navigates only through OUR adapter's mcp__halo__ tools (no toolset mixups).
    disallowedTools: ["mcp__monitoring__halo_fetch", "mcp__monitoring__halo_fetch_many"],
    canUseTool: async (_toolName: string, input: Record<string, unknown>) => ({
      behavior: "allow" as const,
      updatedInput: input,
    }),
    mcpServers: {
      monitoring: {
        type: "stdio" as const,
        command: TSX_BIN,
        args: [SERVER_PATH],
        env: {
          ...process.env,
          MONITORING_HALO: "0", // server returns RAW; all Halo behaviour comes from our adapter
          MONITORING_FORMAT: FORMAT, // json (default) or toon serialization
          AGENT_SESSION_ID: sessionId,
          MONITORING_CHANNEL: process.env.MONITORING_CHANNEL || "cron",
        },
      },
    },
  };

  // The Halo arm: our consumer-side adapter wraps the options with a PostToolUse encode hook +
  // in-process halo_walk/halo_fetch tools. Nothing in the MCP server changes.
  const installed = ADAPTER_ON ? installHalo(baseOptions as never, { threshold: 2048 }) : null;
  const options = (installed ? installed.options : baseOptions) as never;
  const session = (installed?.session ?? null) as { store?: unknown } & Record<string, unknown> | null;

  const q = query({ prompt: userPrompt, options });

  const toolCalls: Record<string, number> = {};
  let usage: any = {};
  let cost: number | null = null;
  let numTurns: number | null = null;

  // Structured event timeline for the landing page: every assistant message, tool call, and tool
  // result (with byte sizes so the Halo "tiny map vs raw blob" contrast is visible), in order.
  const events: Array<Record<string, unknown>> = [];
  let step = 0;
  const CAP = 8000; // cap stored text so a 23 KB raw blob doesn't bloat the file; bytes is exact
  const toolName = new Map<string, string>(); // tool_use_id -> tool name, to label results

  const textOf = (content: unknown): string => {
    if (typeof content === "string") return content;
    if (Array.isArray(content)) {
      return content
        .map((b: any) => (typeof b === "string" ? b : b?.type === "text" ? b.text : JSON.stringify(b)))
        .join("");
    }
    return content == null ? "" : JSON.stringify(content);
  };
  const isHaloEnvelope = (t: string): boolean => t.includes('"halo"') || t.startsWith("[halo]");

  for await (const message of q) {
    if (message.type === "assistant") {
      for (const block of message.message.content) {
        if (block.type === "text") {
          process.stdout.write(block.text);
          if (block.text.trim()) events.push({ step: step++, role: "assistant", type: "text", text: block.text });
        } else if (block.type === "tool_use") {
          toolCalls[block.name] = (toolCalls[block.name] || 0) + 1;
          toolName.set(block.id, block.name);
          process.stdout.write(`\n  → ${block.name}(${JSON.stringify(block.input)})\n`);
          events.push({ step: step++, role: "assistant", type: "tool_call", id: block.id, name: block.name, input: block.input });
        }
      }
    } else if (message.type === "user") {
      // Tool results come back as user-role messages with tool_result blocks.
      const content = (message as any).message?.content;
      if (Array.isArray(content)) {
        for (const block of content) {
          if (block?.type === "tool_result") {
            const text = textOf(block.content);
            events.push({
              step: step++,
              role: "tool",
              type: "tool_result",
              tool_use_id: block.tool_use_id,
              tool: toolName.get(block.tool_use_id) ?? null,
              is_error: !!block.is_error,
              bytes: Buffer.byteLength(text, "utf8"),
              halo_envelope: isHaloEnvelope(text),
              text: text.length > CAP ? text.slice(0, CAP) + `\n…[truncated, ${text.length} chars total]` : text,
            });
          }
        }
      }
    } else if (message.type === "result") {
      usage = (message as any).usage ?? {};
      cost = (message as any).total_cost_usd ?? null;
      numTurns = (message as any).num_turns ?? null;
      events.push({ step: step++, type: "result", subtype: (message as any).subtype });
    }
  }

  const tokens = {
    input: usage.input_tokens ?? 0,
    output: usage.output_tokens ?? 0,
    cache_read: usage.cache_read_input_tokens ?? 0,
    cache_creation: usage.cache_creation_input_tokens ?? 0,
  };
  const total = tokens.input + tokens.output + tokens.cache_read + tokens.cache_creation;
  const haloMaps = session ? (session.maps as Map<string, unknown> | undefined)?.size ?? 0 : null;
  const summary = {
    label: RUN_LABEL,
    halo_adapter: ADAPTER_ON,
    format: FORMAT,
    model: MODEL,
    tokens: { ...tokens, total },
    total_cost_usd: cost,
    num_turns: numTurns,
    tool_calls: toolCalls,
    halo_maps_encoded: haloMaps,
  };
  const runsDir = join(PROJECT_ROOT, "runs");
  mkdirSync(runsDir, { recursive: true });
  writeFileSync(join(runsDir, `${RUN_LABEL}.json`), JSON.stringify(summary, null, 2));

  // Full event timeline for the landing page: ordered steps with byte sizes per tool result, so the
  // "tiny halo map vs raw blob" contrast renders directly.
  const heavyReads = events.filter(
    (e) => e.type === "tool_result" && typeof e.bytes === "number" && (e.bytes as number) > 1000,
  );
  const eventLog = {
    label: RUN_LABEL,
    mode,
    halo_adapter: ADAPTER_ON,
    format: FORMAT,
    model: MODEL,
    summary: { tokens: { ...tokens, total }, total_cost_usd: cost, num_turns: numTurns, tool_calls: toolCalls },
    highlights: {
      tool_results_seen: events.filter((e) => e.type === "tool_result").length,
      halo_envelopes: events.filter((e) => e.halo_envelope).length,
      bytes_in_largest_result: heavyReads.reduce((m, e) => Math.max(m, e.bytes as number), 0),
    },
    events,
  };
  writeFileSync(join(runsDir, `${RUN_LABEL}.events.json`), JSON.stringify(eventLog, null, 2));

  console.log(`\n\n=== run complete — ${mode} ===`);
  console.log("=== TOKENS ===");
  console.log(`  label          : ${RUN_LABEL}`);
  console.log(`  input          : ${tokens.input.toLocaleString()}`);
  console.log(`  output         : ${tokens.output.toLocaleString()}`);
  console.log(`  cache_read     : ${tokens.cache_read.toLocaleString()}`);
  console.log(`  cache_creation : ${tokens.cache_creation.toLocaleString()}`);
  console.log(`  TOTAL tokens   : ${total.toLocaleString()}`);
  console.log(`  cost (usd)     : ${cost}`);
  console.log(`  turns          : ${numTurns}`);
  console.log(`  tool calls     : ${JSON.stringify(toolCalls)}`);
  console.log(`  events log      : runs/${RUN_LABEL}.events.json (${events.length} steps)`);
}

const prompt =
  process.argv.slice(2).join(" ") ||
  "Run a monitoring pass: triage the open issues, diagnose the highest-impact one, and if it " +
    "warrants it, declare an incident (wait for the human gate) and state the outcome.";

run(prompt).catch((e) => {
  console.error(e);
  process.exit(1);
});
