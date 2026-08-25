# The Secret Family

Interactive D3.js visualization mapping the power hierarchy of ~60 people discussed in Professor Jiang's YouTube interview.

**Live site:** Open `index.html` in any browser — no server, no build step, no dependencies.

## What it shows

A force-directed graph organized into four tiers of influence:

- **Tier 1 (Top Power)** — green rings
- **Tier 2 (Key Players)** — blue rings
- **Tier 3 (Secondary)** — amber rings
- **Tier 4 (Peripheral)** — red rings

Click any person to highlight their connections and open an intelligence dossier with:
- Historical timeline (Wikipedia + transcript mentions)
- Wikipedia summary
- Expandable transcript source cards with YouTube deep links at exact timestamps

## Features

- **Search by name** — Ctrl+F or use the search box (top-right)
- **Pan & zoom** — drag to pan, scroll to zoom, drag avatars to reposition
- **Loading screen** — graph settles before display, centered on Tier 1
- **Responsive** — works on mobile

## Project structure

| File | Purpose |
|---|---|
| `index.html` | The visualization (single self-contained file) |
| `build.py` | Orchestrator — merges data and embeds into `index.html` |
| `extract_connections.py` | Extracts co-mention edges from the transcript |
| `fetch_wikipedia.py` | Fetches Wikipedia data (summaries, images, timelines) |
| `build_curated_edges.py` | Helper for building curated relationship edges |
| `transcript.txt` | Full interview transcript with timestamps |
| `people.md` | All people mentioned, grouped by category |
| `nodes.json` | Node definitions (tiers, eras, Wikipedia titles) |
| `connections.json` | Auto-extracted co-mention edges |
| `curated_edges.json` | Manually curated relationship edges with labels |
| `people_data.json` | Enriched person data (Wikipedia + transcript sources) |
| `mentions.json` | Per-person mention counts and timestamps |

## Data pipeline

```
transcript.txt
    │
    ├─ extract_connections.py → connections.json + mentions.json
    │
    ├─ nodes.json + mentions.json
    │         │
    │         └─ fetch_wikipedia.py → people_data.json
    │
    └─ all + curated_edges.json
              │
              └─ build.py → index.html (single file with everything embedded)
```

## Rebuilding

```bash
python3 build.py
```

This regenerates `index.html` with all JSON data embedded. Run after changing any data file.

To re-fetch Wikipedia data:
```bash
python3 fetch_wikipedia.py
```

To re-extract connections from the transcript:
```bash
python3 extract_connections.py
```

## Source

- **Video:** https://www.youtube.com/watch?v=_TlzUQrnI1I
- **Disclaimer:** This visualization maps claims made in a YouTube interview. Inclusion does not imply endorsement of those claims.

## Tech

- [D3.js v7](https://d3js.org/) — force-directed graph, zoom, drag
- [Wikipedia REST API](https://en.wikipedia.org/api/rest_v1/) — summaries, thumbnails, wikitext
- Vanilla JS, inline CSS, zero dependencies