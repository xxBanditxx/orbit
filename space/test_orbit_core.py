import tempfile
import unittest
from pathlib import Path

from orbit_core import OrbitStore, decision_gate, required_confidence


class OrbitCoreTests(unittest.TestCase):
    def make_store(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        return OrbitStore(Path(tempdir.name) / "beliefs.json")

    def test_evidence_keeps_provenance(self):
        store = self.make_store()
        belief = store.record_evidence(
            subject="Bike",
            predicate="weighs",
            obj="330 lb",
            context="current configuration",
            claim_type="personal_report",
            relation="support",
            source_type="firsthand_report",
            speaker="Thomas",
            quote="She's not fat. 330 lbs",
            reliability=0.70,
        )
        self.assertEqual(belief.evidence[0].speaker, "Thomas")
        self.assertEqual(belief.evidence[0].quote, "She's not fat. 330 lbs")
        self.assertEqual(belief.claim_type, "personal_report")

    def test_contradiction_increases_pressure(self):
        store = self.make_store()
        first = store.record_evidence(
            subject="Glass",
            predicate="is",
            obj="fragile",
            relation="support",
            source_type="direct_measurement",
            reliability=0.90,
        )
        before = first.pressure
        after = store.record_evidence(
            subject="Glass",
            predicate="is",
            obj="fragile",
            relation="contradict",
            source_type="direct_measurement",
            reliability=0.90,
        )
        self.assertGreater(after.pressure, before)
        self.assertEqual(after.status, "contested")

    def test_round_trip(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        path = Path(tempdir.name) / "beliefs.json"
        original = OrbitStore(path)
        recorded = original.record_evidence(
            subject="Orbit",
            predicate="preserves",
            obj="revision",
            relation="support",
            source_type="primary_document",
            reliability=0.85,
        )
        loaded = OrbitStore(path)
        self.assertEqual(loaded.get(recorded.id).statement, recorded.statement)

    def test_high_stakes_irreversible_guardrail(self):
        self.assertEqual(required_confidence("high", "low", "high"), 0.85)
        result = decision_gate(0.84, "high", "low", "high")
        self.assertFalse(result["permitted"])


if __name__ == "__main__":
    unittest.main()
