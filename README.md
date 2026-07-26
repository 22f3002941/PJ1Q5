# tds-data-analyst-bot

A Telegram bot backed by an LLM agent that answers data-analysis
questions (MOSPI and similar public datasets) and replies with a
single JSON object, per the assignment spec.

## How it works

```
Telegram message
      │
      ▼
 POST /webhook  (app.py)
      │  append to per-chat history
      ▼
 run_agent()    (agent.py)
      │  Anthropic tool-calling loop:
      │    - model calls run_python(code) to fetch/compute over
      │      real data (pandas/requests, sandboxed subprocess)
      │    - every LLM turn + tool call/result is appended to
      │      logs/<chat_id>.jsonl
      │  model's final turn = the JSON object requested by the user
      ▼
 reply {"answer": ..., "log_url": "https://<host>/logs/<chat_id>.jsonl"}
```

`logs/<chat_id>.jsonl` is served publicly (read-only) at
`GET /logs/<chat_id>.jsonl`, which is exactly the `log_url` returned
in the bot's answer — so it's wget-able out of the box, no separate
bucket/Drive needed. (You can swap in S3/GCS/Drive later if you want
logs to survive redeploys; see "Persisting logs" below.)

## 1. Local setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...
python test_local.py   # sanity-check the agent loop without Telegram
```

## 2. Create the bot with BotFather

1. Message `@BotFather` on Telegram → `/newbot`
2. Pick a name and a username ending in `bot`, e.g. `my_data_analyst_bot`
3. Save the token it gives you → this is `TELEGRAM_BOT_TOKEN`

## 3. Deploy

Any host that gives you a public HTTPS URL and lets you run a small
persistent web service works: Render, Railway, Fly.io, a VPS, etc.
Below is Render (has a working free tier for this size of app).

1. Push this repo to a **public GitHub repo**.
2. On [render.com](https://render.com): New → Web Service → connect
   the repo. It will pick up `render.yaml` automatically (or set
   manually: build `pip install -r requirements.txt`, start
   `gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120`).
3. Set environment variables in the Render dashboard:
   - `TELEGRAM_BOT_TOKEN`
   - `ANTHROPIC_API_KEY`
   - `PUBLIC_BASE_URL` = the URL Render gives you, e.g.
     `https://tds-data-analyst-bot.onrender.com`
4. Deploy. Once it's live, register the webhook once:

   ```bash
   TELEGRAM_BOT_TOKEN=xxx PUBLIC_BASE_URL=https://tds-data-analyst-bot.onrender.com \
     python set_webhook.py
   ```

5. Message your bot on Telegram from a **real user account** (not
   another bot) to confirm it replies with a single JSON object.

Note on free tiers: free web services on Render/Railway can spin down
after idle periods and take ~30-60s to wake on the next request.
That's fine here since Telegram will just get a delayed webhook
response — but if grading is time-sensitive, use a paid/always-on
instance, or a small always-on VPS (e.g. a $5 droplet running
`gunicorn` behind `systemd` + `nginx`, or just `python app.py` behind
a tunnel is NOT recommended for grading since it must "stay
reachable" continuously).

## 4. Test against the official grading harness

```bash
git clone https://github.com/Jivraj-18/tds-p1-t2-2026-telegram-bot
cd tds-p1-t2-2026-telegram-bot
# follow its README to point it at your bot username,
# add sample questions to evals/questions.json, run it
```

## 5. Persisting logs (optional, recommended)

The default `/logs/<chat_id>.jsonl` route reads straight off local
disk. On most PaaS free tiers this disk is ephemeral (wiped on
redeploy/restart), which is fine mid-grading-session but not
permanent. If you want durability, change `logger.py` to also (or
instead) upload each line to:
- a public GCS/S3 bucket object, or
- a public Gist via the GitHub API, or
- Google Drive (share link, "anyone with the link"),

and change `PUBLIC_BASE_URL`/`log_url` construction in `app.py`
accordingly. The interface (`log_event`, `log_path`) is intentionally
small so this swap is a one-file change.

## Files

- `app.py` — Flask server: `/webhook` (Telegram), `/logs/<id>.jsonl` (public log)
- `agent.py` — LLM tool-calling loop (Anthropic Messages API)
- `tools.py` — sandboxed `run_python` tool (pandas/numpy/requests)
- `logger.py` — JSONL append-only logger
- `set_webhook.py` — one-time Telegram webhook registration
- `test_local.py` — smoke test bypassing Telegram
- `render.yaml` — Render deployment config
