# @halo-format/openai

Halo host adapter for the [OpenAI Agents SDK](https://github.com/openai/openai-agents-js)
(`@openai/agents`). `installHalo()` wires it in one call:

- a **Model wrapper** — the interception seam on this host. The Python `openai-agents` SDK has a
  `call_model_input_filter`; the released JS SDK (0.1.x) does **not**, so this adapter intercepts one
  layer down, at the `Model` boundary: `wrapModel` / `wrapModelProvider` rewrite the tool-result items
  in `request.input` before delegating to the real model. Same interception point in the pipeline (right
  before the model call), and equally **generic** — every tool's output (built-in, function,
  external/MCP/hosted) flows through the model request, so all of it is caught. Above a size threshold a
  large result becomes a halo **shape map** (root kind + one line per field: ref, kind, bounded
  preview), so the payload stays out of the model's context;
- a single **`halo_fetch`** function tool the model uses to pull back only the leaves it needs, verified
  on read — a ref that lands on a branch returns that branch's sub-refs, so one batch API both pulls and
  expands (there is no separate `halo_walk`).

```ts
import { Agent, Runner } from "@openai/agents";
import { installHalo } from "@halo-format/openai";

const { tools, wrapModelProvider, session } = installHalo({ tools: myTools });

// a) wrap the provider when the agent names its model by string:
const runner = new Runner({ modelProvider: wrapModelProvider(myProvider) });
await runner.run(new Agent({ name: "assistant", model: "gpt-4.1", tools }), input);

// b) or wrap a Model instance directly:
//   const agent = new Agent({ name, model: wrapModel(myModel), tools });
// session holds the shared store for audit/inspection
```

Because the wrapper fires before every model call over the whole input list (not once per tool return),
it caches each encoded result by `callId` so repeated firings stay idempotent (refs the model already
saw never shift), and it reads the call `arguments` from the matching `function_call` item to feed entity
accumulation. The wrapper is deterministic plumbing (it always runs, for every tool); the Halo Skill (or
prompt-mode guidance) is the navigation behavior. Pass `store: new FileStore(dir)` for the
heavy/persistent deployment. The core engine is
[`@halo-format/halo`](https://www.npmjs.com/package/@halo-format/halo); this package is only the shim.
