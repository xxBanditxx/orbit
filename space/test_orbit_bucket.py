import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orbit_bucket import OrbitBucketMemory


class OrbitBucketMemoryTests(unittest.TestCase):
    def make_memory(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        path = Path(tempdir.name) / "beliefs.json"
        return OrbitBucketMemory("xxbanditxx/orbit-memory", path), path

    def test_disabled_bucket_uses_local_storage(self):
        memory = OrbitBucketMemory("", Path("beliefs.json"))
        self.assertEqual(memory.restore(), "disabled")
        self.assertFalse(memory.status()["enabled"])

    @patch("orbit_bucket.batch_bucket_files")
    @patch("orbit_bucket.get_bucket_paths_info")
    def test_empty_bucket_can_receive_first_snapshot(self, paths_info, batch_upload):
        memory, path = self.make_memory()
        paths_info.return_value = iter([])
        path.write_text('{"schema_version": 2, "beliefs": []}', encoding="utf-8")

        self.assertEqual(memory.restore(), "empty")
        self.assertEqual(memory.backup(), "synced")
        batch_upload.assert_called_once_with(
            "xxbanditxx/orbit-memory",
            add=[(path, "beliefs.json")],
        )

    @patch("orbit_bucket.download_bucket_files")
    @patch("orbit_bucket.get_bucket_paths_info")
    def test_existing_snapshot_is_restored(self, paths_info, download):
        memory, path = self.make_memory()
        paths_info.return_value = iter([object()])

        self.assertEqual(memory.restore(), "restored")
        download.assert_called_once_with(
            "xxbanditxx/orbit-memory",
            files=[("beliefs.json", path)],
            raise_on_missing_files=True,
        )

    @patch("orbit_bucket.batch_bucket_files")
    @patch("orbit_bucket.get_bucket_paths_info")
    def test_failed_restore_blocks_remote_overwrite(self, paths_info, batch_upload):
        memory, path = self.make_memory()
        paths_info.side_effect = RuntimeError("network unavailable")
        path.write_text('{"schema_version": 2, "beliefs": []}', encoding="utf-8")

        self.assertEqual(memory.restore(), "error")
        self.assertEqual(memory.backup(), "blocked")
        batch_upload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
