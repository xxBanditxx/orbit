from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


CLAIM_TYPES = (
    "world_claim",
    "personal_report",
    "opinion",
    "preference",
    "emotion",
    "intention",
    "prediction",
    "hypothesis",
    "inference",
    "instruction",
    "fiction",
)

RELATIONS = ("support", "contradict")

SOURCE_TYPES = (
    "direct_measurement",
    "primary_document",
    "firsthand_report",
    "secondary_source",
    "model_output",
    "conversation",
    "unknown",
)

DEFAULT_RELIABILITY = {
    "direct_measurement": 0.95,
    "primary_document": 0.85,
    "firsthand_report": 0.70,
    "secondary_source": 0.60,
    "model_output": 0.45,
    "conversation": 0.45,
    "unknown": 0.35,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


@dataclass
class Evidence:
    id: str
    relation: str
    source_type: str
    source_ref: str = ""
    speaker: str = ""
    quote: str = ""
    note: str = ""
    reliability: float = 0.5
    observed_at: str = ""
    submitted_at: str = field(default_factory=utc_now)

    def validate(self) -> None:
        if self.relation not in RELATIONS:
            raise ValueError(f"relation must be one of: {', '.join(RELATIONS)}")
        if self.source_type not in SOURCE_TYPES:
            raise ValueError(f"source_type must be one of: {', '.join(SOURCE_TYPES)}")
        self.reliability = round(clamp(float(self.reliability)), 3)


@dataclass
class Belief:
    id: str
    subject: str
    predicate: str
    obj: str
    context: str = ""
    claim_type: str = "world_claim"
    evidence: List[Evidence] = field(default_factory=list)
    revision_triggers: List[str] = field(default_factory=list)
    instrument_limits: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def validate(self) -> None:
        if not self.subject.strip() or not self.predicate.strip() or not self.obj.strip():
            raise ValueError("subject, predicate, and object are required")
        if self.claim_type not in CLAIM_TYPES:
            raise ValueError(f"claim_type must be one of: {', '.join(CLAIM_TYPES)}")
        for item in self.evidence:
            item.validate()

    @property
    def statement(self) -> str:
        return f"{self.subject} {self.predicate} {self.obj}".strip()

    @property
    def support_weight(self) -> float:
        return round(sum(item.reliability for item in self.evidence if item.relation == "support"), 3)

    @property
    def contradiction_weight(self) -> float:
        return round(sum(item.reliability for item in self.evidence if item.relation == "contradict"), 3)

    @property
    def evidence_mass(self) -> float:
        total = self.support_weight + self.contradiction_weight
        return round(1.0 - math.exp(-total / 2.5), 3)

    @property
    def confidence(self) -> float:
        support = self.support_weight
        contradiction = self.contradiction_weight
        total = support + contradiction
        if total <= 0:
            return 0.0
        direction = support / total
        return round(clamp(direction * self.evidence_mass), 3)

    @property
    def pressure(self) -> float:
        support = self.support_weight
        contradiction = self.contradiction_weight
        total = support + contradiction
        if total <= 0:
            return 0.0
        conflict = 2.0 * min(support, contradiction) / total
        uncertainty = 1.0 - self.evidence_mass
        return round(clamp((0.75 * conflict) + (0.25 * uncertainty)), 3)

    @property
    def status(self) -> str:
        support = self.support_weight
        contradiction = self.contradiction_weight
        total = support + contradiction
        if total == 0:
            return "deferred"
        if support > 0 and contradiction > 0 and self.pressure >= 0.30:
            return "contested"
        if contradiction > support and contradiction >= 0.70:
            return "contradicted"
        if self.confidence >= 0.65:
            return "supported"
        return "provisional"

    def add_unique(self, field_name: str, value: str) -> None:
        value = value.strip()
        if not value:
            return
        target = getattr(self, field_name)
        if value not in target:
            target.append(value)


class OrbitStore:
    SCHEMA_VERSION = 2

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.beliefs: Dict[str, Belief] = {}
        self.load()

    @staticmethod
    def belief_id(subject: str, predicate: str, obj: str, context: str = "") -> str:
        return stable_id(
            "belief",
            normalize_text(subject),
            normalize_text(predicate),
            normalize_text(obj),
            normalize_text(context),
        )

    def load(self) -> None:
        with self._lock:
            if not self.path.exists():
                self.beliefs = {}
                return

            payload = json.loads(self.path.read_text(encoding="utf-8"))
            version = int(payload.get("schema_version", 1))
            if version != self.SCHEMA_VERSION:
                raise ValueError(
                    f"Unsupported Orbit data schema {version}; expected {self.SCHEMA_VERSION}."
                )

            loaded: Dict[str, Belief] = {}
            for raw_item in payload.get("beliefs", []):
                raw = dict(raw_item)
                evidence = [Evidence(**item) for item in raw.pop("evidence", [])]
                belief = Belief(evidence=evidence, **raw)
                belief.validate()
                loaded[belief.id] = belief
            self.beliefs = loaded

    def save(self) -> None:
        with self._lock:
            payload = {
                "schema_version": self.SCHEMA_VERSION,
                "saved_at": utc_now(),
                "beliefs": [asdict(item) for item in self.beliefs.values()],
            }
            temp = self.path.with_suffix(self.path.suffix + ".tmp")
            temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            temp.replace(self.path)

    def seed_if_empty(self) -> None:
        if self.beliefs:
            return
        self.record_evidence(
            subject="Orbit",
            predicate="governs",
            obj="how conclusions are formed and revised",
            context="reasoning under uncertainty",
            claim_type="world_claim",
            relation="support",
            source_type="primary_document",
            source_ref="OPERATIONAL_SPEC.md",
            speaker="ORBIT specification",
            quote="ORBIT is a governor that constrains how conclusions are formed, held, revised, and audited.",
            reliability=0.90,
            note="Seeded from the project specification.",
            revision_trigger="A later specification materially changes Orbit's role.",
            instrument_limit="The specification defines intended behavior, not proven effectiveness.",
        )
        self.record_evidence(
            subject="Contradictions",
            predicate="should remain",
            obj="visible until resolved",
            context="Orbit belief handling",
            claim_type="world_claim",
            relation="support",
            source_type="primary_document",
            source_ref="README.md",
            speaker="ORBIT specification",
            quote="Contradictions remain visible instead of being silently discarded.",
            reliability=0.85,
            note="Seed belief.",
        )

    def record_evidence(
        self,
        *,
        subject: str,
        predicate: str,
        obj: str,
        context: str = "",
        claim_type: str = "world_claim",
        relation: str = "support",
        source_type: str = "unknown",
        source_ref: str = "",
        speaker: str = "",
        quote: str = "",
        reliability: Optional[float] = None,
        note: str = "",
        observed_at: str = "",
        revision_trigger: str = "",
        instrument_limit: str = "",
    ) -> Belief:
        subject = subject.strip()
        predicate = predicate.strip()
        obj = obj.strip()
        context = context.strip()

        belief_id = self.belief_id(subject, predicate, obj, context)
        reliability_value = (
            DEFAULT_RELIABILITY.get(source_type, 0.35)
            if reliability is None
            else float(reliability)
        )

        evidence_id = stable_id(
            "evidence",
            belief_id,
            relation,
            source_type,
            source_ref.strip(),
            speaker.strip(),
            quote.strip(),
            note.strip(),
            observed_at.strip(),
            utc_now(),
        )
        evidence = Evidence(
            id=evidence_id,
            relation=relation,
            source_type=source_type,
            source_ref=source_ref.strip(),
            speaker=speaker.strip(),
            quote=quote.strip(),
            note=note.strip(),
            reliability=reliability_value,
            observed_at=observed_at.strip(),
        )
        evidence.validate()

        with self._lock:
            belief = self.beliefs.get(belief_id)
            if belief is None:
                belief = Belief(
                    id=belief_id,
                    subject=subject,
                    predicate=predicate,
                    obj=obj,
                    context=context,
                    claim_type=claim_type,
                )
                self.beliefs[belief_id] = belief
            elif belief.claim_type != claim_type and belief.claim_type == "world_claim":
                belief.claim_type = claim_type

            belief.evidence.append(evidence)
            belief.add_unique("revision_triggers", revision_trigger)
            belief.add_unique("instrument_limits", instrument_limit)
            belief.updated_at = utc_now()
            belief.validate()
            self.save()
            return belief

    def get(self, belief_id: str) -> Optional[Belief]:
        return self.beliefs.get(belief_id)

    def all(self) -> List[Belief]:
        return sorted(
            self.beliefs.values(),
            key=lambda belief: (belief.pressure, belief.confidence, belief.updated_at),
            reverse=True,
        )

    def search(self, query: str) -> List[Belief]:
        tokens = [token for token in normalize_text(query).split(" ") if token]
        if not tokens:
            return self.all()
        scored: List[Tuple[int, Belief]] = []
        for belief in self.beliefs.values():
            haystack = normalize_text(
                " ".join(
                    [
                        belief.statement,
                        belief.context,
                        belief.claim_type,
                        " ".join(belief.revision_triggers),
                        " ".join(belief.instrument_limits),
                    ]
                )
            )
            score = sum(1 for token in tokens if token in haystack)
            if score:
                scored.append((score, belief))
        scored.sort(key=lambda pair: (pair[0], pair[1].pressure, pair[1].confidence), reverse=True)
        return [belief for _, belief in scored]

    def pressure_queue(self) -> List[Belief]:
        return [belief for belief in self.all() if belief.status in {"contested", "contradicted", "provisional"}]

    def export_snapshot(self) -> dict:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "exported_at": utc_now(),
            "beliefs": [asdict(item) for item in self.all()],
        }


def required_confidence(stakes: str, reversibility: str, time_pressure: str) -> float:
    stakes_base = {"low": 0.30, "medium": 0.60, "high": 0.85}
    reversibility_adjustment = {"high": -0.15, "medium": 0.0, "low": 0.15}
    time_adjustment = {"high": -0.15, "medium": 0.0, "low": 0.10}

    try:
        threshold = (
            stakes_base[stakes.lower()]
            + reversibility_adjustment[reversibility.lower()]
            + time_adjustment[time_pressure.lower()]
        )
    except KeyError as exc:
        raise ValueError("stakes, reversibility, and time pressure must be low, medium, or high") from exc

    threshold = clamp(threshold)
    if stakes.lower() == "high" and reversibility.lower() == "low":
        threshold = max(threshold, 0.85)
    return round(threshold, 2)


def decision_gate(
    confidence: float,
    stakes: str,
    reversibility: str,
    time_pressure: str,
) -> dict:
    confidence = round(clamp(float(confidence)), 3)
    threshold = required_confidence(stakes, reversibility, time_pressure)
    permitted = confidence >= threshold
    return {
        "confidence": confidence,
        "required_confidence": threshold,
        "permitted": permitted,
        "recommendation": (
            "bounded action permitted"
            if permitted
            else "prefer reversible probing or gather more signal"
        ),
    }
