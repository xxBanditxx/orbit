from __future__ import annotations

import os
from pathlib import Path

from orbit_bucket import OrbitBucketMemory


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("ORBIT_DATA_DIR", APP_DIR / "data"))
DATA_FILE = DATA_DIR / "beliefs.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)

BUCKET_MEMORY = OrbitBucketMemory.from_env(DATA_FILE)
STARTUP_STATE = BUCKET_MEMORY.restore()

# Import only after the bucket restore attempt so OrbitStore sees the durable
# memory file before it decides whether to seed a new graph.
import app as orbit_app  # noqa: E402


if STARTUP_STATE == "empty":
    # The remote bucket was read successfully and contained no memory file.
    # Seeded local state can therefore become the first authoritative snapshot.
    BUCKET_MEMORY.backup()


_original_record_evidence = orbit_app.STORE.record_evidence


def persistent_record_evidence(*args, **kwargs):
    belief = _original_record_evidence(*args, **kwargs)
    state = BUCKET_MEMORY.backup()
    print(f"[ORBIT MEMORY] {state}: {BUCKET_MEMORY.message}", flush=True)
    return belief


# All UI and MCP record operations pass through the same store instance, so
# wrapping this method makes persistence consistent across both interfaces.
orbit_app.STORE.record_evidence = persistent_record_evidence


_original_overview_markdown = orbit_app.overview_markdown


def overview_markdown_with_memory() -> str:
    status = BUCKET_MEMORY.status()
    return (
        _original_overview_markdown()
        + "\n\n"
        + f"**Memory vault:** `{status['state']}` · {status['message']}"
    )


orbit_app.overview_markdown = overview_markdown_with_memory

demo = orbit_app.demo


if __name__ == "__main__":
    print(
        f"[ORBIT MEMORY] {BUCKET_MEMORY.state}: {BUCKET_MEMORY.message}",
        flush=True,
    )
    demo.launch(mcp_server=True, css=orbit_app.CSS)
