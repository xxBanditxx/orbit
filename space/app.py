from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

import gradio as gr

from orbit_core import (
    CLAIM_TYPES,
    DEFAULT_RELIABILITY,
    RELATIONS,
    SOURCE_TYPES,
    OrbitStore,
    decision_gate,
)


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("ORBIT_DATA_DIR", APP_DIR / "data"))
DATA_FILE = DATA_DIR / "beliefs.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)

STORE = OrbitStore(DATA_FILE)
STORE.seed_if_empty()


def belief_row(belief) -> List[Any]:
    return [
        belief.id,
        belief.statement,
        belief.context,
        belief.claim_type,
        belief.status,
        belief.support_weight,
        belief.contradiction_weight,
        belief.confidence,
        belief.pressure,
        len(belief.evidence),
        belief.updated_at,
    ]


def queue_row(belief) -> List[Any]:
    next_question = (
        belief.revision_triggers[0]
        if belief.revision_triggers
        else f"What evidence would materially change '{belief.statement}'?"
    )
    return [
        belief.id,
        belief.statement,
        belief.status,
        belief.confidence,
        belief.pressure,
        next_question,
    ]


def deck_rows(limit: int = 50) -> List[List[Any]]:
    return [belief_row(item) for item in STORE.all()[:limit]]


def queue_rows(limit: int = 50) -> List[List[Any]]:
    return [queue_row(item) for item in STORE.pressure_queue()[:limit]]


def overview_markdown() -> str:
    beliefs = STORE.all()
    status_counts: Dict[str, int] = {}
    for belief in beliefs:
        status_counts[belief.status] = status_counts.get(belief.status, 0) + 1

    contested = status_counts.get("contested", 0)
    provisional = status_counts.get("provisional", 0)
    supported = status_counts.get("supported", 0)
    contradicted = status_counts.get("contradicted", 0)
    evidence_count = sum(len(item.evidence) for item in beliefs)

    return f"""
### Current state

**{len(beliefs)} beliefs** · **{evidence_count} evidence records** ·
**{supported} supported** · **{contested} contested** ·
**{provisional} provisional** · **{contradicted} contradicted**

Orbit does not store final truths. It stores bounded claims, their evidence, the pressure against them, and what would justify revision.
"""


def serialize_belief(belief) -> Dict[str, Any]:
    if belief is None:
        return {"error": "belief not found"}
    return {
        "id": belief.id,
        "statement": belief.statement,
        "subject": belief.subject,
        "predicate": belief.predicate,
        "object": belief.obj,
        "context": belief.context,
        "claim_type": belief.claim_type,
        "status": belief.status,
        "support_weight": belief.support_weight,
        "contradiction_weight": belief.contradiction_weight,
        "confidence": belief.confidence,
        "pressure": belief.pressure,
        "revision_triggers": belief.revision_triggers,
        "instrument_limits": belief.instrument_limits,
        "evidence": [
            {
                "id": item.id,
                "relation": item.relation,
                "source_type": item.source_type,
                "source_ref": item.source_ref,
                "speaker": item.speaker,
                "quote": item.quote,
                "note": item.note,
                "reliability": item.reliability,
                "observed_at": item.observed_at,
                "submitted_at": item.submitted_at,
            }
            for item in belief.evidence
        ],
        "created_at": belief.created_at,
        "updated_at": belief.updated_at,
    }


def orbit_query(query: str) -> Tuple[str, List[List[Any]], Dict[str, Any]]:
    """Search Orbit's bounded beliefs and return the strongest matching belief with provenance."""
    matches = STORE.search(query)
    if not matches:
        return (
            "### No matching belief\nOrbit has no bounded claim for that query yet.",
            [],
            {"query": query, "matches": 0},
        )

    top = matches[0]
    summary = f"""
### Orbit's current lean

**{top.statement}**

Status: **{top.status}** · Confidence: **{top.confidence:.3f}** ·
Pressure: **{top.pressure:.3f}**

Context: {top.context or "not declared"}

This is a revisable judgment, not a declaration of universal truth.
"""
    return summary, [belief_row(item) for item in matches[:20]], serialize_belief(top)


def orbit_inspect(belief_id: str) -> Dict[str, Any]:
    """Inspect one Orbit belief, including every source, quote, limit, and revision trigger."""
    return serialize_belief(STORE.get(belief_id.strip()))


def orbit_record(
    subject: str,
    predicate: str,
    obj: str,
    context: str,
    claim_type: str,
    relation: str,
    source_type: str,
    source_ref: str,
    speaker: str,
    quote: str,
    reliability: float,
    note: str,
    observed_at: str,
    revision_trigger: str,
    instrument_limit: str,
) -> Tuple[str, str, List[List[Any]], List[List[Any]], Dict[str, Any]]:
    """Record traceable support or contradiction for a bounded claim in Orbit."""
    try:
        belief = STORE.record_evidence(
            subject=subject,
            predicate=predicate,
            obj=obj,
            context=context,
            claim_type=claim_type,
            relation=relation,
            source_type=source_type,
            source_ref=source_ref,
            speaker=speaker,
            quote=quote,
            reliability=reliability,
            note=note,
            observed_at=observed_at,
            revision_trigger=revision_trigger,
            instrument_limit=instrument_limit,
        )
    except (TypeError, ValueError) as exc:
        return (
            f"### Record rejected\n{exc}",
            overview_markdown(),
            deck_rows(),
            queue_rows(),
            {"error": str(exc)},
        )

    return (
        f"### Evidence recorded\n**{relation}** added to `{belief.id}`. "
        f"Status is now **{belief.status}** with confidence **{belief.confidence:.3f}**.",
        overview_markdown(),
        deck_rows(),
        queue_rows(),
        serialize_belief(belief),
    )


def orbit_pressure_queue() -> List[List[Any]]:
    """Return Orbit's unresolved, contested, contradicted, and weakly supported beliefs."""
    return queue_rows()


def orbit_decision_gate(
    confidence: float,
    stakes: str,
    reversibility: str,
    time_pressure: str,
) -> Dict[str, Any]:
    """Apply Orbit's context-dependent action threshold to a proposed bounded action."""
    return decision_gate(confidence, stakes, reversibility, time_pressure)


def orbit_snapshot() -> Dict[str, Any]:
    """Export the current Orbit belief graph as a provenance-preserving JSON snapshot."""
    return STORE.export_snapshot()


def default_reliability(source_type: str) -> float:
    return DEFAULT_RELIABILITY.get(source_type, 0.35)


TABLE_HEADERS = [
    "Belief ID",
    "Statement",
    "Context",
    "Claim type",
    "Status",
    "Support",
    "Contradiction",
    "Confidence",
    "Pressure",
    "Evidence",
    "Updated",
]

QUEUE_HEADERS = [
    "Belief ID",
    "Statement",
    "Status",
    "Confidence",
    "Pressure",
    "Revision question",
]


CSS = """
.orbit-hero {
    border: 1px solid rgba(148, 163, 184, 0.35);
    border-radius: 18px;
    padding: 22px;
    background: radial-gradient(circle at top right, rgba(59,130,246,.18), transparent 35%),
                radial-gradient(circle at bottom left, rgba(16,185,129,.13), transparent 38%);
}
"""


with gr.Blocks(title="Orbit Command Deck", css=CSS) as demo:
    gr.Markdown(
        """
<div class="orbit-hero">

# 🪐 Orbit Command Deck

### Put your agent under pressure.

Orbit separates **claims** from **evidence**, keeps contradiction visible,
binds judgment to context, and records what would justify revision.

</div>
"""
    )

    overview = gr.Markdown(value=overview_markdown())

    with gr.Tab("Command Deck"):
        refresh_button = gr.Button("Refresh deck", variant="primary")
        deck_table = gr.Dataframe(
            headers=TABLE_HEADERS,
            value=deck_rows(),
            interactive=False,
            wrap=True,
            label="Belief graph",
        )
        pressure_table = gr.Dataframe(
            headers=QUEUE_HEADERS,
            value=queue_rows(),
            interactive=False,
            wrap=True,
            label="Pressure queue",
        )

    with gr.Tab("Query Orbit"):
        query_text = gr.Textbox(
            label="Question or topic",
            placeholder="contradictions, Orbit, vehicle security, evidence...",
        )
        query_button = gr.Button("Query Orbit", variant="primary")
        query_summary = gr.Markdown()
        query_table = gr.Dataframe(
            headers=TABLE_HEADERS,
            interactive=False,
            wrap=True,
            label="Matching beliefs",
        )
        query_detail = gr.JSON(label="Strongest matching belief and provenance")

    with gr.Tab("Record Evidence"):
        gr.Markdown(
            """
Record what supports or challenges a claim. A polished sentence is not automatically a fact.
The source, speaker, context, reliability, quote, and instrument limits travel with the claim.
"""
        )
        with gr.Row():
            subject = gr.Textbox(label="Subject", placeholder="The GSX-R750")
            predicate = gr.Textbox(label="Predicate", placeholder="weighs about")
            obj = gr.Textbox(label="Object", placeholder="330 lb")

        context = gr.Textbox(
            label="Context / scope",
            placeholder="Thomas's 2001 motorcycle in current configuration",
        )

        with gr.Row():
            claim_type = gr.Dropdown(
                choices=list(CLAIM_TYPES),
                value="world_claim",
                label="Claim type",
            )
            relation = gr.Radio(
                choices=list(RELATIONS),
                value="support",
                label="Evidence relation",
            )
            source_type = gr.Dropdown(
                choices=list(SOURCE_TYPES),
                value="firsthand_report",
                label="Source type",
            )

        with gr.Row():
            source_ref = gr.Textbox(label="Source reference", placeholder="conversation/message, document, URL")
            speaker = gr.Textbox(label="Speaker / observer", placeholder="Thomas")
            observed_at = gr.Textbox(label="Observed at", placeholder="2026-06-23 or ISO timestamp")

        quote = gr.Textbox(
            label="Exact evidence quote or measurement",
            lines=3,
            placeholder="Preserve the original wording or measurement here.",
        )
        note = gr.Textbox(label="Analyst note", lines=2)
        reliability = gr.Slider(
            minimum=0.0,
            maximum=1.0,
            value=DEFAULT_RELIABILITY["firsthand_report"],
            step=0.05,
            label="Evidence reliability",
        )
        revision_trigger = gr.Textbox(
            label="Revision trigger",
            placeholder="What new signal would materially change this judgment?",
        )
        instrument_limit = gr.Textbox(
            label="Instrument limit",
            placeholder="What can this source, sensor, memory, or model not establish?",
        )
        record_button = gr.Button("Record evidence", variant="primary")
        record_status = gr.Markdown()
        record_detail = gr.JSON(label="Updated belief")

    with gr.Tab("Decision Gate"):
        gr.Markdown(
            """
A belief can be usable without authorizing an action. Orbit scales the required confidence
by stakes, reversibility, and time pressure.
"""
        )
        action_confidence = gr.Slider(0.0, 1.0, value=0.60, step=0.01, label="Current confidence")
        with gr.Row():
            stakes = gr.Radio(["low", "medium", "high"], value="medium", label="Stakes")
            reversibility = gr.Radio(["high", "medium", "low"], value="medium", label="Reversibility")
            time_pressure = gr.Radio(["low", "medium", "high"], value="medium", label="Time pressure")
        gate_button = gr.Button("Apply action threshold", variant="primary")
        gate_result = gr.JSON(label="Decision gate result")

    with gr.Tab("MCP + Schema"):
        gr.Markdown(
            """
### Agent-facing tools

When launched with MCP enabled, Orbit exposes documented tools for:

- `orbit_query`
- `orbit_inspect`
- `orbit_record`
- `orbit_pressure_queue`
- `orbit_decision_gate`
- `orbit_snapshot`

### Core rule

A transcript fact such as **“Thomas said X”** is distinct from the world claim **“X is true.”**
Chat ingestion will arrive after the governor core and will preserve that distinction.
"""
        )
        inspect_id = gr.Textbox(label="Belief ID to inspect")
        inspect_button = gr.Button("Inspect")
        inspect_result = gr.JSON(label="Belief")
        snapshot_button = gr.Button("Export in browser")
        snapshot_result = gr.JSON(label="Orbit snapshot")

    refresh_button.click(
        lambda: (overview_markdown(), deck_rows(), queue_rows()),
        inputs=[],
        outputs=[overview, deck_table, pressure_table],
        api_name=False,
    )

    query_button.click(
        orbit_query,
        inputs=[query_text],
        outputs=[query_summary, query_table, query_detail],
        api_name="orbit_query",
    )

    record_button.click(
        orbit_record,
        inputs=[
            subject,
            predicate,
            obj,
            context,
            claim_type,
            relation,
            source_type,
            source_ref,
            speaker,
            quote,
            reliability,
            note,
            observed_at,
            revision_trigger,
            instrument_limit,
        ],
        outputs=[record_status, overview, deck_table, pressure_table, record_detail],
        api_name="orbit_record",
    )

    gate_button.click(
        orbit_decision_gate,
        inputs=[action_confidence, stakes, reversibility, time_pressure],
        outputs=[gate_result],
        api_name="orbit_decision_gate",
    )

    inspect_button.click(
        orbit_inspect,
        inputs=[inspect_id],
        outputs=[inspect_result],
        api_name="orbit_inspect",
    )

    snapshot_button.click(
        orbit_snapshot,
        inputs=[],
        outputs=[snapshot_result],
        api_name="orbit_snapshot",
    )

    demo.load(
        lambda: (overview_markdown(), deck_rows(), queue_rows()),
        inputs=[],
        outputs=[overview, deck_table, pressure_table],
    )


if __name__ == "__main__":
    demo.launch(mcp_server=True)
