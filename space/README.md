---
title: Orbit Command Deck
emoji: 🪐
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 6.18.0
python_version: "3.11"
app_file: app.py
short_description: A provenance-aware governor for reasoning under uncertainty.
pinned: true
tags:
  - reasoning
  - knowledge-graph
  - ai-memory
  - mcp
  - gradio
---

# Orbit Command Deck

## Put Your Agent Under Pressure

Orbit is a governor for reasoning under uncertainty. It does not store polished answers as final truths. It stores bounded claims together with their context, supporting and contradicting evidence, source reliability, instrument limits, and revision triggers.

## What this version adds

- Evidence provenance: source, speaker, quote, timestamp, and reliability remain attached to each claim.
- Contradiction pressure: disagreement stays visible rather than being silently averaged away.
- Revisable confidence: confidence grows with evidence mass and falls under contradiction.
- Decision gate: action thresholds scale with stakes, reversibility, and time pressure.
- MCP-ready tools: agents can query, inspect, record evidence, evaluate action thresholds, and export snapshots.

## Core distinction

`Thomas said X` can be a verified transcript fact while `X is true` remains an unverified world claim.

Orbit keeps those statements separate.

## Current scope

This is the governor core. Automatic chat ingestion and claim extraction are intentionally deferred until the evidence schema and revision behavior are stable.

## Local run

```bash
python -m pip install -r requirements.txt
python app.py
```

The MCP endpoint is exposed by Gradio when the app launches with `mcp_server=True`.
