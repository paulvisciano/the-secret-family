#!/usr/bin/env python3
"""
build.py — orchestrator that regenerates index.html with all data embedded.

Pipeline:
  1. Ensure connections.json exists (run extract_connections.py if missing).
  2. Ensure people_data.json exists (run fetch_wikipedia.py if missing).
  3. Read nodes.json, connections.json, people_data.json, curated_edges.json.
  4. Normalize + merge auto-extracted edges with curated edges.
  5. Embed all four JSON payloads into index.html as <script type="application/json"> blocks,
     preserving all surrounding HTML/CSS/JS (idempotent targeted replacement).

Usage:
    /opt/homebrew/bin/python3.11 build.py

Idempotent: running again produces the same index.html (byte-for-byte, modulo
the JSON separators which are deterministic via json.dumps with sort_keys=False).
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
PY = "/opt/homebrew/bin/python3.11"

NODES_PATH = BASE_DIR / "nodes.json"
CONNECTIONS_PATH = BASE_DIR / "connections.json"
PEOPLE_DATA_PATH = BASE_DIR / "people_data.json"
CURATED_EDGES_PATH = BASE_DIR / "curated_edges.json"
TRANSCRIPT_PATH = BASE_DIR / "transcript.txt"
INDEX_PATH = BASE_DIR / "index.html"

EXTRACT_SCRIPT = BASE_DIR / "extract_connections.py"
FETCH_SCRIPT = BASE_DIR / "fetch_wikipedia.py"

# Data block IDs in index.html -> (id, source-file loader)
# Order matters only for readability; replacement is by-ID so order-independent.
DATA_BLOCKS = [
    ("people-data", "people"),
    ("connections-data", "edges"),
    ("nodes-data", "nodes_meta"),
    ("curated-edges-data", "curated"),
]

# Regex to locate a <script id="ID" type="application/json">...</script> block
BLOCK_RE_TEMPLATE = r'(<script id="{id}" type="application/json">)(.*?)(</script>)'


# ---------------------------------------------------------------------------
# Step 1 & 2: ensure prerequisite data files exist
# ---------------------------------------------------------------------------
def ensure_file(path: Path, script: Path, label: str) -> None:
    """Run `script` with PY if `path` does not exist."""
    if path.exists():
        print(f"[build] {label}: {path.name} exists — skipping generation.")
        return
    if not script.exists():
        print(f"[build] ERROR: {label} missing and generator {script.name} not found.", file=sys.stderr)
        sys.exit(1)
    print(f"[build] {label}: {path.name} missing — running {script.name} ...")
    result = subprocess.run([PY, str(script)], cwd=str(BASE_DIR))
    if result.returncode != 0:
        print(f"[build] ERROR: {script.name} exited with code {result.returncode}.", file=sys.stderr)
        sys.exit(result.returncode)
    if not path.exists():
        print(f"[build] ERROR: {script.name} ran but did not produce {path.name}.", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Step 3: load data
# ---------------------------------------------------------------------------
def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Step 4: normalize + merge edges
# ---------------------------------------------------------------------------
def build_alias_map(nodes_meta: dict) -> dict:
    """Map every alias (and canonical id) -> canonical graph id."""
    alias_map = {}
    for n in nodes_meta.get("graph", []):
        cid = n["id"]
        alias_map[cid] = cid
        for a in n.get("aliases", []):
            alias_map[a] = cid
    return alias_map


def graph_ids_set(nodes_meta: dict) -> set:
    return {n["id"] for n in nodes_meta.get("graph", [])}


def normalize_auto_edges(connections: list, alias_map: dict, graph_ids: set) -> list:
    """Alias-resolve connections.json, drop contextual/self-loop/unmapped edges."""
    out = []
    for e in connections:
        s = alias_map.get(e["source"])
        t = alias_map.get(e["target"])
        if s is None or t is None:
            continue  # unmapped endpoint (contextual or unknown)
        if s not in graph_ids or t not in graph_ids:
            continue  # contextual node
        if s == t:
            continue  # self-loop
        out.append({
            "source": s,
            "target": t,
            "weight": e.get("weight", 1),
            "transcript_refs": e.get("transcript_refs", []),
        })
    return out


def normalize_curated_edges(curated: list, alias_map: dict, graph_ids: set) -> list:
    """Alias-resolve curated_edges.json; skip edges touching non-graph nodes."""
    out = []
    for e in curated:
        s = alias_map.get(e["source"])
        t = alias_map.get(e["target"])
        if s is None or t is None:
            continue
        if s not in graph_ids or t not in graph_ids:
            continue  # targets contextual node (e.g. "Rothschild family")
        if s == t:
            continue
        out.append({
            "source": s,
            "target": t,
            "label": e.get("label") or e.get("relationship") or "",
            "source_ref": e.get("source_ref") or "",
        })
    return out


def merge_edges(auto_edges: list, curated_norm: list) -> list:
    """
    Merge auto-extracted edges with curated edges.

    - If a curated pair already exists in auto-extracted edges, keep the
      auto-extracted edge (preserving weight + transcript_refs). The curated
      label is applied separately via the curatedLabels map at render time.
    - If a curated pair does NOT exist in auto-extracted edges, add it as a
      new edge with weight=1.
    """
    # Build a lookup of existing pairs (both directions)
    existing = set()
    for e in auto_edges:
        existing.add((e["source"], e["target"]))
        existing.add((e["target"], e["source"]))

    merged = list(auto_edges)  # shallow copy of the list (dicts are not mutated)

    for ce in curated_norm:
        pair = (ce["source"], ce["target"])
        if pair in existing:
            continue  # auto-extracted edge already covers this pair
        # New curated-only edge
        merged.append({
            "source": ce["source"],
            "target": ce["target"],
            "weight": 1,
            "transcript_refs": [],
        })
        existing.add(pair)
        existing.add((ce["target"], ce["source"]))

    return merged


# ---------------------------------------------------------------------------
# Step 5: embed JSON into index.html (idempotent targeted replacement)
# ---------------------------------------------------------------------------
def embed_block(html: str, block_id: str, data, separators=(",", ":")) -> str:
    """
    Replace the content of <script id="block_id" type="application/json">...</script>
    with compact JSON. If the block does not exist, raise an error (blocks must
    already exist in the template — build.py does not create new HTML structure).

    Uses compact separators (",", ":") for connections/curated/nodes and
    readable separators (", ", ": ") for people-data to match the existing
    embedded format. Both are deterministic.
    """
    payload = json.dumps(data, ensure_ascii=False, separators=separators)
    pattern = BLOCK_RE_TEMPLATE.format(id=re.escape(block_id))
    match = re.search(pattern, html, flags=re.DOTALL)
    if not match:
        raise ValueError(
            f"build: <script id=\"{block_id}\" type=\"application/json\"> block not found in index.html. "
            "Ensure the HTML template contains all four data blocks."
        )
    return html[:match.start(2)] + payload + html[match.end(2):]


def embed_all(html: str, people, edges, nodes_meta, curated_norm, transcript_compact=None) -> str:
    html = embed_block(html, "people-data", people, separators=(", ", ": "))
    html = embed_block(html, "connections-data", edges, separators=(",", ":"))
    html = embed_block(html, "nodes-data", nodes_meta, separators=(",", ":"))
    html = embed_block(html, "curated-edges-data", curated_norm, separators=(",", ":"))
    if transcript_compact is not None:
        html = embed_block(html, "transcript-data", transcript_compact, separators=(",", ":"))
    return html


def load_transcript_compact(path):
    """Load transcript.txt and return a compact array of {t: seconds, x: text}."""
    import re
    lines = []
    cur_ts = None
    cur_text = []
    ts_re = re.compile(r"^\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*-\s*(.*)$")
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            m = ts_re.match(line)
            if m:
                if cur_ts is not None:
                    parts = cur_ts.split(":")
                    parts = [int(p) for p in parts]
                    secs = parts[0] * 60 + parts[1] if len(parts) == 2 else parts[0] * 3600 + parts[1] * 60 + parts[2]
                    lines.append({"t": secs, "x": " ".join(cur_text).strip()})
                cur_ts = m.group(1)
                cur_text = [m.group(2)]
            else:
                if cur_ts is not None:
                    cur_text.append(line.strip())
    if cur_ts is not None:
        parts = cur_ts.split(":")
        parts = [int(p) for p in parts]
        secs = parts[0] * 60 + parts[1] if len(parts) == 2 else parts[0] * 3600 + parts[1] * 60 + parts[2]
        lines.append({"t": secs, "x": " ".join(cur_text).strip()})
    return lines


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print("[build] The Secret Family — orchestrator")

    # Step 1: ensure connections.json
    ensure_file(CONNECTIONS_PATH, EXTRACT_SCRIPT, "connections")

    # Step 2: ensure people_data.json
    ensure_file(PEOPLE_DATA_PATH, FETCH_SCRIPT, "people_data")

    # Step 3: load all data
    print("[build] Loading data files ...")
    nodes_meta = load_json(NODES_PATH)
    connections = load_json(CONNECTIONS_PATH)
    people = load_json(PEOPLE_DATA_PATH)
    curated_raw = load_json(CURATED_EDGES_PATH)

    transcript_compact = None
    if TRANSCRIPT_PATH.exists():
        print("[build] Loading transcript ...")
        transcript_compact = load_transcript_compact(TRANSCRIPT_PATH)
        print(f"  transcript lines: {len(transcript_compact)}")

    alias_map = build_alias_map(nodes_meta)
    graph_ids = graph_ids_set(nodes_meta)

    # Step 4: normalize + merge
    print("[build] Normalizing edges ...")
    auto_edges = normalize_auto_edges(connections, alias_map, graph_ids)
    curated_norm = normalize_curated_edges(curated_raw, alias_map, graph_ids)
    merged_edges = merge_edges(auto_edges, curated_norm)

    print(f"  auto-extracted edges (renderable): {len(auto_edges)}")
    print(f"  curated edges (renderable):       {len(curated_norm)}")
    print(f"  merged edges (total in graph):   {len(merged_edges)}")

    # Reorder merged edges: auto-extracted first (stable), then new curated.
    # merge_edges already does this (auto first, then new curated appended).
    # Sort by source then target for deterministic ordering within each group.
    # Actually keep insertion order for stability — the simulation doesn't care.

    # Step 5: embed into index.html
    print("[build] Reading index.html ...")
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    print("[build] Embedding JSON data blocks ...")
    html = embed_all(html, people, merged_edges, nodes_meta, curated_norm, transcript_compact)

    print("[build] Writing index.html ...")
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = len(html) / 1024
    print(f"[build] Done. index.html is {size_kb:.1f} KB.")


if __name__ == "__main__":
    main()