"""
Quick local smoke test that bypasses Telegram entirely: it calls
run_agent() directly with a sample question, so you can iterate fast.

Usage:
    ANTHROPIC_API_KEY=... python test_local.py
"""
import os
os.environ.setdefault("PUBLIC_BASE_URL", "http://localhost:8080")

from agent import run_agent  # noqa: E402

QUESTION = (
    'Which state has the highest maternal mortality rate based on MOSPI data? '
    'Reply with ONLY this JSON object and nothing else: '
    '{"answer": {"state": "<state name>"}, "log_url": "<public wget-able URL to your agent log>"}'
)

if __name__ == "__main__":
    history = [{"role": "user", "content": QUESTION}]
    out = run_agent("local-test", history, "http://localhost:8080/logs/local-test.jsonl")
    print(out)
