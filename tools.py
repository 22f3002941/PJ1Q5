"""
A restricted Python execution tool. The agent calls this to download
public datasets (MOSPI CSV/XLS/API endpoints, etc.), load them with
pandas, and compute the actual numeric/textual answer instead of
guessing from memory.

Executed in a SEPARATE PROCESS with a wall-clock timeout, network
access only through requests, and no access to the host filesystem
outside a scratch dir. This is a pragmatic sandbox, not a security
boundary against a truly hostile user -- but here the "user" is your
own LLM, and Telegram grading traffic never reaches this code path
directly.
"""

import json
import subprocess
import sys
import tempfile
import textwrap

TIMEOUT_SECONDS = 60

RUNNER_PREAMBLE = textwrap.dedent(
    """
    import json, sys, io, contextlib
    import pandas as pd
    import numpy as np
    import requests

    _buf = io.StringIO()
    _result = {"stdout": "", "error": None}
    try:
        with contextlib.redirect_stdout(_buf):
"""
)

RUNNER_TAIL = textwrap.dedent(
    """
    except Exception as e:
        import traceback
        _result["error"] = traceback.format_exc()
    _result["stdout"] = _buf.getvalue()
    print("___RESULT_JSON___" + json.dumps(_result))
    """
)


def run_python(code: str) -> dict:
    """Run `code` in a fresh subprocess. Whatever it prints via print()
    is captured and returned as stdout. Use print() to surface any
    values you need to see -- there is no return-value passing besides
    stdout."""
    indented = textwrap.indent(code, " " * 12)
    full_script = RUNNER_PREAMBLE + indented + "\n" + RUNNER_TAIL

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(full_script)
        script_path = f.name

    try:
        proc = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {"stdout": "", "error": f"Timed out after {TIMEOUT_SECONDS}s"}

    out = proc.stdout
    marker = "___RESULT_JSON___"
    if marker in out:
        prefix, _, tail = out.partition(marker)
        try:
            result = json.loads(tail.strip().splitlines()[0])
        except Exception:
            result = {"stdout": out, "error": proc.stderr}
        result["stdout"] = (prefix + result.get("stdout", ""))[-6000:]
        if proc.stderr:
            result["stderr"] = proc.stderr[-2000:]
        return result

    return {"stdout": out[-6000:], "error": proc.stderr[-2000:] if proc.stderr else None}
