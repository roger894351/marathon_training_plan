"""Dashboard generator — injects activity data into HTML template.

Reads activity_log.json, embeds it as JavaScript in the HTML template,
and writes a self-contained dashboard.html that can be opened directly.
"""

import json
import os
import webbrowser
from datetime import datetime
from pathlib import Path

from .activity_store import DEFAULT_STORE_PATH, load_store

TEMPLATE_PATH = Path(__file__).parent / "dashboard_template.html"
DEFAULT_OUTPUT = "running_data/dashboard.html"


def generate_dashboard(
    store_path: str = DEFAULT_STORE_PATH,
    output_path: str = DEFAULT_OUTPUT,
) -> str:
    """Generate a self-contained HTML dashboard from the activity store.

    Returns the output file path.
    """
    store = load_store(store_path)

    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()

    # Inject data
    data_json = json.dumps(store, ensure_ascii=False)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    last_sync = store.get("last_sync", "never")
    if last_sync and last_sync != "never":
        last_sync = last_sync[:16].replace("T", " ")
    activity_count = len(store.get("activities", []))

    html = template.replace("__DATA_JSON__", data_json)
    html = html.replace("__GENERATED_AT__", now)
    html = html.replace("__LAST_SYNC__", last_sync or "never")
    html = html.replace("__ACTIVITY_COUNT__", str(activity_count))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path


def open_dashboard(output_path: str = DEFAULT_OUTPUT) -> None:
    """Open the dashboard HTML in the default browser."""
    abs_path = os.path.abspath(output_path)
    webbrowser.open(f"file://{abs_path}")
