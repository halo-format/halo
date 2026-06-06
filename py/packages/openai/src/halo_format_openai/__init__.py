"""halo_format_openai — Halo host adapter for the OpenAI Agents SDK (Python).

The interception point is ``RunConfig.call_model_input_filter``. The OpenAI Agents SDK has no
tool-return output-replacement hook (``on_tool_end`` is observational), so this filter — which rewrites
the assembled model input before each model call — is the only generic, deterministic seam that catches
**every** tool, including external/MCP/hosted tools the app does not own. Above a size threshold it
encodes each large ``function_call_output`` into a shared store and replaces the output the model sees
with a SHAPE MAP (not the blob). One ``function_tool``, ``halo_fetch(refs)``, backed by the same store,
lets the model pull back the withheld leaves (and expand branches), verified on read.

``install_halo`` returns the augmented ``tools`` list, the ``call_model_input_filter`` to put on the
run, and the shared session::

    from agents import Agent, Runner, RunConfig
    from halo_format_openai import install_halo

    result = install_halo(tools=my_tools)
    agent = Agent(name="...", tools=result.tools)
    out = await Runner.run(
        agent, "…",
        run_config=RunConfig(call_model_input_filter=result.call_model_input_filter),
    )
    # result.session — the shared HaloSession (store + map registry), for audit swaps / inspection.

MANDATORY correctness rule: the filter must NOT re-encode the navigation tool's own output, or a fetched
leaf would be replaced by a new map and the model would never see the value. Enforced by correlating each
``function_call_output`` to its ``function_call`` (by ``call_id``) and skipping ``halo_fetch`` — see
``input_filter.py``.

Light vs. heavy: pass ``store=FileStore(dir)`` for cross-process persistence, and wrap navigation with
the L2 chain, without touching the control flow here."""

from typing import NamedTuple, Optional

from .accumulate import KeyOf, arg_join
from .constants import HALO_FETCH_TOOL, is_halo_nav_tool
from .input_filter import make_input_filter
from .nav_tool import create_halo_fetch_tool, halo_fetch
from .serialize import parse_tool_output, preview_of, serialize_envelope, shape_of, size_of
from .session import HaloSession


class InstallHaloResult(NamedTuple):
    tools: list  # your tools + halo_fetch, to pass to Agent(tools=...)
    call_model_input_filter: object  # put on RunConfig(call_model_input_filter=...) / Runner
    session: HaloSession  # the shared session (store + map registry), for audit swaps / inspection


def install_halo(
    *,
    tools: Optional[list] = None,
    threshold: int = 2048,
    store=None,
    key_of: Optional[KeyOf] = None,
    alg: str = "sha256",
    now=None,
    session: Optional[HaloSession] = None,
) -> InstallHaloResult:
    """Wire the Halo adapter into an OpenAI Agents SDK run.

    Append the returned ``tools`` to your ``Agent`` and pass ``call_model_input_filter`` on the run::

        result = install_halo(tools=my_tools)
        agent = Agent(name="...", tools=result.tools)
        await Runner.run(agent, "…",
                         run_config=RunConfig(call_model_input_filter=result.call_model_input_filter))
    """
    session = session if session is not None else HaloSession(
        store=store, key_of=key_of, alg=alg, now=now
    )
    fetch_tool = create_halo_fetch_tool(session)
    input_filter = make_input_filter(session, threshold)
    return InstallHaloResult(
        tools=[*(tools or []), fetch_tool],
        call_model_input_filter=input_filter,
        session=session,
    )


__all__ = [
    "install_halo",
    "InstallHaloResult",
    "make_input_filter",
    "create_halo_fetch_tool",
    "halo_fetch",
    "HaloSession",
    "arg_join",
    "KeyOf",
    "size_of",
    "parse_tool_output",
    "serialize_envelope",
    "shape_of",
    "preview_of",
    "HALO_FETCH_TOOL",
    "is_halo_nav_tool",
]
