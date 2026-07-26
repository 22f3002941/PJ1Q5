import json
import os

LOG_DIR = os.environ.get("LOG_DIR", "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def log_path(chat_id: str) -> str:
    safe = "".join(c for c in str(chat_id) if c.isalnum() or c in ("-", "_"))
    return os.path.join(LOG_DIR, f"{safe}.jsonl")


def log_event(chat_id: str, event: dict):
    """Append one JSON object (one line) to logs/<chat_id>.jsonl."""
    path = log_path(chat_id)
    with open(path, "a") as f:
        f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
