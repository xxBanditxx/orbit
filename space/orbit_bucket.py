from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Dict

from huggingface_hub import batch_bucket_files, download_bucket_files, get_bucket_paths_info


class OrbitBucketMemory:
    """Guarded persistence for Orbit's JSON state.

    Orbit only writes after it has successfully inspected the remote bucket.
    A network or permission failure therefore cannot blindly overwrite a
    previously valid remote memory file.
    """

    def __init__(self, bucket_id: str, local_path: Path, remote_path: str = "beliefs.json") -> None:
        self.bucket_id = bucket_id.strip()
        self.local_path = Path(local_path)
        self.remote_path = remote_path.strip().lstrip("/") or "beliefs.json"
        self.state = "not_checked"
        self.message = "Bucket memory has not been checked yet."
        self._remote_safe = False
        self._lock = threading.RLock()

    @classmethod
    def from_env(cls, local_path: Path) -> "OrbitBucketMemory":
        return cls(
            bucket_id=os.getenv("ORBIT_BUCKET_ID", ""),
            local_path=local_path,
            remote_path=os.getenv("ORBIT_BUCKET_PATH", "beliefs.json"),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.bucket_id)

    def restore(self) -> str:
        if not self.enabled:
            self.state = "disabled"
            self.message = "Bucket memory is disabled; using local runtime storage."
            return self.state

        with self._lock:
            try:
                matches = list(get_bucket_paths_info(self.bucket_id, [self.remote_path]))
                self._remote_safe = True

                if not matches:
                    self.state = "empty"
                    self.message = f"Bucket {self.bucket_id} is connected and empty."
                    return self.state

                self.local_path.parent.mkdir(parents=True, exist_ok=True)
                download_bucket_files(
                    self.bucket_id,
                    files=[(self.remote_path, self.local_path)],
                    raise_on_missing_files=True,
                )
                self.state = "restored"
                self.message = f"Restored memory from {self.bucket_id}/{self.remote_path}."
                return self.state
            except Exception as exc:
                self._remote_safe = False
                self.state = "error"
                self.message = f"Bucket restore failed: {type(exc).__name__}: {exc}"
                return self.state

    def backup(self) -> str:
        if not self.enabled:
            self.state = "disabled"
            self.message = "Bucket memory is disabled; changes remain local."
            return self.state

        if not self._remote_safe:
            self.state = "blocked"
            self.message = "Bucket write blocked because restore did not succeed."
            return self.state

        if not self.local_path.exists():
            self.state = "error"
            self.message = f"Local memory file is missing: {self.local_path}"
            return self.state

        with self._lock:
            try:
                batch_bucket_files(
                    self.bucket_id,
                    add=[(self.local_path, self.remote_path)],
                )
                self.state = "synced"
                self.message = f"Synced memory to {self.bucket_id}/{self.remote_path}."
                return self.state
            except Exception as exc:
                self.state = "error"
                self.message = f"Bucket backup failed: {type(exc).__name__}: {exc}"
                return self.state

    def status(self) -> Dict[str, object]:
        return {
            "enabled": self.enabled,
            "bucket_id": self.bucket_id or None,
            "remote_path": self.remote_path,
            "state": self.state,
            "message": self.message,
            "write_guard_open": self._remote_safe,
        }
