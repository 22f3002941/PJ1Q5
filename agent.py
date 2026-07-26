import json
import os

import anthropic

from logger import log_event
from tools import run_python

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-4-6")
MAX_TOOL_ROUNDS = 8

SYSTEM_PROMPT = """You are a rigorous data analyst agent operating over Telegram.

You will be given the most recent user messages (a short conversation).
Answer only the LAST user message; earlier messages are context for a
possible multi-turn task.

The user's message will specify:
  - a data-analysis question (may embed data inline, or point at a
    public dataset such as MOSPI - mospi.gov.in - or similar), and
  - the EXACT JSON shape to reply with, e.g.
    {"answer": {"state": "<state name>"}, "log_url": "<...>"}

Rules:
1. Never guess a factual/numeric answer from memory alone if the
   question references an external dataset. Use the run_python tool
   to actually fetch (requests/pandas) and compute it. pandas, numpy,
   and requests are pre-imported in that tool's execution environment.
2. Use print() inside run_python to see any values -- the tool only
   returns what was printed plus errors.
3. If a dataset URL isn't given, search your own knowledge for the
   correct MOSPI (or other official) source page/API/download link
   and fetch it with requests inside run_python. Try a couple of
   plausible URLs/endpoints if the first fails.
4. When you have the final answer, respond with ONLY the JSON object
   in the exact shape the user requested -- no markdown fences, no
   explanation, no extra keys beyond what was asked plus log_url.
   Do not wrap it in prose. This final message must be valid JSON,
   parseable by json.loads, and nothing else.
5. Use the exact "log_url" value given to you in the tool context;
   do not invent your own.
"""

TOOLS = [
    {
        "name": "run_python",
        "description": (
            "Execute a Python snippet in a fresh sandboxed process. "
            "pandas as pd, numpy as np, requests, and json are pre-imported. "
            "Use print() for anything you need to observe. Returns "
            "{'stdout': ..., 'error': ...}."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to run"}
            },
            "required": ["code"],
        },
    }
]


def _extract_json_object(text: str):
    """Best-effort: pull the first top-level {...} JSON object out of text."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model output")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("Unbalanced JSON in model output")


def run_agent(chat_id: str, history: list, log_url: str) -> dict:
    convo = [{"role": h["role"], "content": h["content"]} for h in history]
    # give the model the log_url to embed verbatim
    convo[-1] = {
        "role": "user",
        "content": convo[-1]["content"]
        + f"\n\n[context: use this exact log_url in your final JSON: {log_url}]",
    }

    for round_i in range(MAX_TOOL_ROUNDS):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=convo,
        )

        log_event(
            chat_id,
            {
                "type": "llm_response",
                "round": round_i,
                "stop_reason": resp.stop_reason,
                "content": [b.model_dump() for b in resp.content],
            },
        )

        tool_uses = [b for b in resp.content if b.type == "tool_use"]

        if not tool_uses:
            # model is done -- extract final JSON text
            text_blocks = [b.text for b in resp.content if b.type == "text"]
            final_text = "\n".join(text_blocks)
            answer_obj = _extract_json_object(final_text)
            answer_obj.setdefault("log_url", log_url)
            return answer_obj

        # execute each requested tool call, feed results back
        convo.append({"role": "assistant", "content": resp.content})
        tool_result_blocks = []
        for tu in tool_uses:
            code = tu.input.get("code", "")
            result = run_python(code)
            log_event(
                chat_id,
                {"type": "tool_call", "round": round_i, "code": code, "result": result},
            )
            tool_result_blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps(result)[:8000],
                }
            )
        convo.append({"role": "user", "content": tool_result_blocks})

    raise RuntimeError("Agent did not converge to a final answer within max rounds")
