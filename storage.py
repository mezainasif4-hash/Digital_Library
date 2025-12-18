import json
from pathlib import Path

DATA_FILE = Path("library_state.json")


def load_state() -> dict:
    if not DATA_FILE.exists():
        return {"books": {}, "orders": []}
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"books": {}, "orders": []}


def save_state(books_dict: dict, orders_list: list):
    state = {
        "books": books_dict,
        "orders": orders_list,
    }
    DATA_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
