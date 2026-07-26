"""
tds-bot: a data-analyst Telegram bot backed by an LLM agent with a
sandboxed Python-execution tool.

Flow per incoming Telegram message:
  1. Telegram POSTs the update to /webhook
  2. We append the message to that chat's short history
  3. agent.run_agent() drives an LLM tool-calling loop:
       - model can call `run_python(code)` to fetch data / compute
       - every step (LLM call, tool call, tool result) is appended
         to logs/<chat_id>.jsonl
       - model finishes by returning ONLY the final JSON object
         the user asked for (we inject log_url before sending)
  4. We reply to Telegram with that exact JSON string
  5. The log file is servable at /logs/<chat_id>.jsonl (public, wget-able)
"""

import json
import os
import threading
import time
import traceback

from flask import Flask, request, jsonify, Response, abort

from agent import run_agent
from logger import log_event, log_path

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
PUBLIC_BASE_URL = os.environ["PUBLIC_BASE_URL"].rstrip("/")  # e.g. https://yourapp.onrender.com
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# very small in-memory per-chat history: [{"role": "user"/"assistant", "content": str}, ...]
# fine for grading-scale traffic; swap for redis/sqlite if you need durability
HISTORY = {}
MAX_HISTORY_MESSAGES = 8


def send_message(chat_id, text):
    import requests
    r = requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=30,
    )
    return r.json()


@app.route("/", methods=["GET"])
def health():
    return "ok"


@app.route("/logs/<path:chat_id>.jsonl", methods=["GET"])
def serve_log(chat_id):
    path = log_path(chat_id)
    if not os.path.exists(path):
        abort(404)
    with open(path, "r") as f:
        content = f.read()
    return Response(content, mimetype="application/jsonl")


def _process_and_reply(chat_id, history, log_url):
    """Runs off the request thread so we can ack Telegram immediately --
    Telegram's webhook read-timeout is much shorter than an agent run
    (LLM calls + data fetching) can take."""
    try:
        answer_obj = run_agent(chat_id, history, log_url)
        reply_text = json.dumps(answer_obj, ensure_ascii=False)
    except Exception as e:
        log_event(chat_id, {"type": "error", "error": str(e), "trace": traceback.format_exc()})
        reply_text = json.dumps({"answer": None, "log_url": log_url, "error": str(e)})

    history.append({"role": "assistant", "content": reply_text})
    log_event(chat_id, {"type": "telegram_out", "text": reply_text, "ts": time.time()})

    try:
        send_message(chat_id, reply_text)
    except Exception as e:
        log_event(chat_id, {"type": "error", "error": f"send_message failed: {e}"})


@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(force=True, silent=True) or {}
    msg = update.get("message") or update.get("edited_message")
    if not msg or "text" not in msg:
        return jsonify({"ok": True})  # ignore non-text updates

    chat_id = str(msg["chat"]["id"])
    text = msg["text"]

    history = HISTORY.setdefault(chat_id, [])
    history.append({"role": "user", "content": text})
    history[:] = history[-MAX_HISTORY_MESSAGES:]

    log_event(chat_id, {"type": "telegram_in", "text": text, "ts": time.time()})

    log_url = f"{PUBLIC_BASE_URL}/logs/{chat_id}.jsonl"

    # kick off the (possibly slow) agent run in the background and
    # ack Telegram right away so it doesn't time out the webhook
    threading.Thread(
        target=_process_and_reply, args=(chat_id, history, log_url), daemon=True
    ).start()

    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
