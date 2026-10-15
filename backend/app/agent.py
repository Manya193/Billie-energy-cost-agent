from __future__ import annotations

import asyncio
import json
import urllib.request
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen2.5:3b"
MCP_URL = "http://127.0.0.1:8766/mcp"

# Only read-only tools are available to the LLM.
# State-changing actions are deliberately excluded.
ALLOWED_TOOLS = {
    "get_current_energy_usage",
    "get_bill_history",
    "get_tariff",
    "get_appliance_usage",
    "get_user_baseline",
    "detect_energy_anomaly",
    "estimate_cost_impact",
    "explain_bill",
    "evaluate_alert_policy",
    "verify_intervention",
}

SYSTEM_PROMPT = """You are Billie, an agentic energy cost intelligence assistant.

Investigate questions using relevant MCP tools. Do not merely summarize the first result.
For electricity-bill increase questions, compare current and previous bills, inspect appliance
usage and baselines, check relevant tariffs or anomalies, and use explain_bill to cross-check.
Continue investigating if important evidence is missing. For other questions, use only relevant
tools; do not call every tool blindly.

Rules:
- Tool outputs are the source of truth. Never invent figures, causes, or savings.
- Correlation does not prove causation; distinguish facts from estimates.
- Never claim an action was performed unless verified.
- Never initiate state-changing actions. If asked to apply or confirm an action, explain that this chat agent cannot execute it and direct the user to the simulator's explicit action flow.
- Never assume the appliance is AC unless the user's question explicitly names AC. Use the appliance identified by the user's question and returned tool evidence.
- Keep user-facing answers under 65 words, using at most 3 short spoken-friendly sentences. Never repeat the same conclusion. Discuss only appliances supported by the returned data; do not default to the AC or list every appliance when unnecessary. Use Indian rupees (₹ INR) consistently for all cost figures.
- For questions about recent simulated hours, report the interval only if tool evidence identifies that interval. Otherwise clearly say the readings are accumulated since simulation reset; never label totals as the last two hours.
- When recommending savings, name one specific appliance and a realistic schedule change. Calculate estimated savings from the configured tariff and the difference between its current scheduled hours and baseline hours. State the amount per day and, if useful, per 30-day month. Do not assume every above-baseline hour is avoidable without saying this is an estimate.
- Distinguish increased appliance costs from reductions caused by appliances being off. Do not recommend reducing essential fridge usage.
- Avoid repeating tool outputs or mentioning historical alerts/interventions unless directly relevant.
- Always finish with a complete sentence; never stop mid-sentence.

For bill increases, briefly report:
- Current and previous bill amounts, total increase, and consumption change when available.
- The largest estimated contributors.
- The amount still unexplained.

Do not claim appliance estimates explain the entire increase unless the evidence supports that conclusion.
Do not present historical interventions as newly performed actions.
"""


def ollama_chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> dict[str, Any]:
    """Send a non-streaming request to Ollama."""
    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": tools,
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 450,
        },
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    print(
        f"\n[Billie] Sending request to Ollama "
        f"({len(tools)} tools, {len(messages)} messages)...",
        flush=True,
    )

    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.loads(response.read().decode("utf-8"))

    print("[Billie] Ollama response received.", flush=True)
    return result


def result_to_text(result: Any) -> str:
    """Convert an MCP result into text the model can understand."""
    structured = getattr(
        result,
        "structuredContent",
        getattr(result, "structured_content", None),
    )

    if structured is not None:
        return json.dumps(structured, ensure_ascii=False, default=str)

    parts = []
    for item in getattr(result, "content", []):
        if hasattr(item, "text"):
            parts.append(item.text)

    return "\n".join(parts) or str(result)


def is_bill_increase_question(message: str) -> bool:
    """Identify questions that require bill-increase investigation."""
    text = message.lower()

    mentions_bill = any(
        word in text
        for word in ("bill", "electricity cost", "electricity charges")
    )
    asks_about_increase = any(
        word in text
        for word in (
            "why",
            "increase",
            "increased",
            "increasing",
            "higher",
            "high",
            "went up",
            "going up",
        )
    )
    return mentions_bill and asks_about_increase


async def call_and_record(
    session: ClientSession,
    name: str,
    arguments: dict[str, Any],
    trace: list[dict[str, Any]],
) -> dict[str, Any]:
    """Call an allowlisted MCP tool and record its result."""
    if name not in ALLOWED_TOOLS:
        output = {"error": "Tool is not permitted."}
    else:
        try:
            result = await session.call_tool(name, arguments)
            output = {
                "is_error": result.is_error,
                "result": result_to_text(result),
            }
        except Exception as exc:
            output = {"error": str(exc)}

    trace.append({
        "tool": name,
        "arguments": arguments,
        "result": output,
    })
    return output


def _answer_looks_truncated(reply: str, done_reason: str | None = None) -> bool:
    """Detect obvious truncation without retrying normal concise answers."""
    if done_reason == "length":
        return True

    text = reply.strip()
    if not text:
        return True

    # A sentence-ending punctuation mark or closing quote/bracket is normal.
    if text[-1] in ".!?\"'”’)]}":
        return False

    # Common incomplete endings seen in model responses.
    lower = text.lower()
    incomplete_endings = (
        "with the remaining",
        "because the",
        "which means the",
        "in conclusion,",
        "the main reason is",
        "with the remaining unexplained",
        "and the remaining",
    )
    return lower.endswith(incomplete_endings)


async def _finalize_answer(
    messages: list[dict[str, Any]],
    assistant_message: dict[str, Any],
) -> str:
    """Return a final answer, with at most one repair generation."""
    reply = (assistant_message.get("content") or "").strip()
    done_reason = assistant_message.get("done_reason")

    if _answer_looks_truncated(reply, done_reason):
        repair_messages = list(messages)
        repair_messages.append({
            "role": "user",
            "content": (
                "Write the complete final answer now in 4-6 concise sentences. "
                "Use only the evidence already present in this conversation. "
                "Include current and previous bill amounts, the consumption "
                "change, estimated contributors, the unexplained remainder, "
                "and that the records are synthetic. Do not invent a cause. "
                "Do not call tools. End with a complete sentence."
            ),
        })

        try:
            retry_response = await asyncio.to_thread(
                ollama_chat,
                repair_messages,
                [],
            )
            retry_message = retry_response.get("message", {})
            retry_reply = (retry_message.get("content") or "").strip()
            if retry_reply and not _answer_looks_truncated(
                retry_reply, retry_message.get("done_reason")
            ):
                return retry_reply
            if retry_reply:
                reply = retry_reply
        except Exception:
            # Preserve the original answer if the repair request fails.
            pass

    if not reply:
        return (
            "I gathered evidence, but couldn't generate a final answer. "
            "Please retry the question."
        )

    # If the model still ends abruptly, provide a safe evidence-based fallback
    # rather than presenting an obviously unfinished sentence.
    if _answer_looks_truncated(reply, done_reason):
        return (
            "I could not produce a complete evidence-based summary from the available results. "
            "Please retry the bill analysis; I will not guess appliance contributors or costs."
        )

    return reply


async def investigate(user_message: str) -> dict[str, Any]:
    """Run a bounded LLM-driven MCP investigation."""
    trace: list[dict[str, Any]] = []
    needs_bill_investigation = is_bill_increase_question(user_message)

    async with streamable_http_client(MCP_URL) as (
        read_stream,
        write_stream,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            initialization = await session.initialize()
            discovered = await session.list_tools()

            ollama_tools = []
            for tool in discovered.tools:
                if tool.name not in ALLOWED_TOOLS:
                    continue

                schema = getattr(tool, "inputSchema", None) or {
                    "type": "object",
                    "properties": {},
                }
                ollama_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or tool.name,
                        "parameters": schema,
                    },
                })

            messages: list[dict[str, Any]] = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]

            # Bounded tool-calling loop.
            for _ in range(8):
                response = await asyncio.to_thread(
                    ollama_chat,
                    messages,
                    ollama_tools,
                )
                assistant_message = response.get("message", {})
                messages.append(assistant_message)
                tool_calls = assistant_message.get("tool_calls", [])

                # Ensure bill-increase questions gather the minimum evidence.
                if not tool_calls and needs_bill_investigation:
                    completed = {
                        item["tool"]
                        for item in trace
                        if not item["result"].get("error")
                        and not item["result"].get("is_error", False)
                    }

                    missing_tool = None
                    if "get_bill_history" not in completed:
                        missing_tool = "get_bill_history"
                    elif "get_appliance_usage" not in completed:
                        missing_tool = "get_appliance_usage"
                    elif "explain_bill" not in completed:
                        missing_tool = "explain_bill"

                    if missing_tool:
                        default_arguments = {
                            "get_bill_history": {},
                            "get_appliance_usage": {
                                "period_label": "current",
                            },
                            "explain_bill": {},
                        }
                        arguments = default_arguments[missing_tool]
                        output = await call_and_record(
                            session,
                            missing_tool,
                            arguments,
                            trace,
                        )
                        messages.append({
                            "role": "user",
                            "content": (
                                f"Additional evidence from {missing_tool}:\n"
                                f"{json.dumps(output, ensure_ascii=False)}\n"
                                "Use this evidence in your reasoning. Do not "
                                "claim it proves causation. Continue only if "
                                "important evidence is missing, then give a "
                                "complete final answer."
                            ),
                        })
                        continue

                # Final response: preserve trace and repair incomplete output once.
                if not tool_calls:
                    reply = await _finalize_answer(messages, assistant_message)
                    return {
                        "reply": reply,
                        "trace": trace,
                        "model": MODEL,
                        "protocol_version": getattr(
                            initialization,
                            "protocolVersion",
                            getattr(
                                initialization,
                                "protocol_version",
                                "unknown",
                            ),
                        ),
                    }

                # Execute only allowlisted tools and return their results to Ollama.
                for call in tool_calls:
                    function = call.get("function", {})
                    name = function.get("name")
                    arguments = function.get("arguments", {})

                    try:
                        if isinstance(arguments, str):
                            arguments = json.loads(arguments)
                        if not isinstance(arguments, dict):
                            raise ValueError(
                                "Tool arguments must be a JSON object."
                            )

                        output = await call_and_record(
                            session,
                            name,
                            arguments,
                            trace,
                        )
                    except Exception as exc:
                        output = {"error": str(exc)}
                        trace.append({
                            "tool": name,
                            "arguments": arguments,
                            "result": output,
                        })

                    messages.append({
                        "role": "tool",
                        "name": name or "unknown_tool",
                        "content": json.dumps(
                            output,
                            ensure_ascii=False,
                            default=str,
                        ),
                    })

            return {
                "reply": (
                    "I reached the investigation limit before completing "
                    "the analysis. Please narrow the question and try again."
                ),
                "trace": trace,
                "model": MODEL,
            }


def investigate_sync(user_message: str) -> dict[str, Any]:
    """Synchronous entry point for the existing web server."""
    return asyncio.run(investigate(user_message))


if __name__ == "__main__":
    question = input("Ask Billie: ").strip()

    if not question:
        print("Please enter a question.")
    else:
        try:
            result = investigate_sync(question)
            print("\nBILLIE:")
            print(result["reply"])
            print("\nTOOL TRACE:")
            print(json.dumps(result["trace"], indent=2, ensure_ascii=False))
            print("\nMODEL:", result["model"])
            print("MCP PROTOCOL:", result.get("protocol_version", "unknown"))
        except BaseException as exc:
            print(f"\nError type: {type(exc).__name__}")
            print(f"Error details: {exc!r}")
            if hasattr(exc, "exceptions"):
                for i, sub_exc in enumerate(exc.exceptions, start=1):
                    print(
                        f"Sub-exception {i}: "
                        f"{type(sub_exc).__name__}: {sub_exc!r}"
                    )
            import traceback
            traceback.print_exc()
