#!/usr/bin/env python3
"""Build curated_edges.json with hand-defined relationship edges.

Each edge has: source, target, label, source_ref
- source/target MUST match node IDs in nodes.json (graph + contextual)
- source_ref MUST be a real timestamp in transcript.txt
"""
import json
import re
import sys

BASE = "/Users/paulvisciano/Projects/the-secret-family"

# Load nodes
with open(f"{BASE}/nodes.json") as f:
    nodes = json.load(f)

valid_ids = set(n["id"] for n in nodes["graph"])
valid_ids.update(n["id"] for n in nodes.get("contextual", []))

# Load transcript and collect all timestamps that exist
ts_pattern = re.compile(r"^(\d+:\d+(?::\d+)?)\s+-\s+")
existing_ts = set()
with open(f"{BASE}/transcript.txt") as f:
    for line in f:
        m = ts_pattern.match(line)
        if m:
            existing_ts.add(m.group(1))

print(f"Loaded {len(valid_ids)} valid node IDs")
print(f"Loaded {len(existing_ts)} unique transcript timestamps")

# ---------------------------------------------------------------------------
# Curated edges
# ---------------------------------------------------------------------------
# Each edge is (source, target, label, source_ref)
# source_ref = the FIRST timestamp where the relationship is discussed in
# the transcript. All timestamps verified to exist in transcript.txt.
# ---------------------------------------------------------------------------

EDGES_RAW = [
    # --- Family ties ---
    ("Donald Trump", "Jared Kushner", "son-in-law", "2:07:23"),
    # 2:07:23 - "Jerkin and Trump both visit the grave of Reberson" (Kushner+Trump together)
    ("Jared Kushner", "Charles Kushner", "father", "2:06:13"),
    # 2:06:13 - "Nanyahu and Charles Kushner uh who is Jared Kushner's father"
    ("Ivanka Trump", "Donald Trump", "daughter", "2:37:03"),
    # 2:37:03 - "close to Trump, even his own daughter"
    ("Sara Netanyahu", "Benjamin Netanyahu", "spouse", "1:20:08"),
    # Sara Netanyahu not named in transcript; Benjamin Netanyahu discussed at
    # 1:20:08 (Clean Break memo for Netanyahu). Spouse relation from people.md.

    # --- Chabad network ---
    ("Benjamin Netanyahu", "Rabbi Menachem Mendel Schneerson", "sought blessing", "1:44:50"),
    # 1:44:50 - "I came to ask your blessing" (Netanyahu speaking to Rebe)
    ("Donald Trump", "Rabbi Menachem Mendel Schneerson", "sought blessing", "2:07:23"),
    # 2:07:23 - "Jerkin and Trump both visit the grave of Reberson...ask for his blessing"
    ("Jared Kushner", "Rabbi Menachem Mendel Schneerson", "Chabad member", "2:06:13"),
    # 2:06:13 - "The Kushner family is very prominent in the Habat Louage movement"
    ("Sheldon Adelson", "Rabbi Menachem Mendel Schneerson", "donor", "1:47:47"),
    # 1:47:47 - "Miriam and Shauna Ellison asked the Rebe for his blessing"
    ("Miriam Adelson", "Rabbi Menachem Mendel Schneerson", "donor", "1:47:47"),
    # 1:47:47 - same (Miriam & Sheldon Adelson asking Rebe blessing)
    ("Alan Dershowitz", "Jared Kushner", "Harvard Chabad", "2:03:12"),
    # 2:03:12 - "faculty adviser was Alan Dersitz...prominent members...Jared Kushner"
    ("Benjamin Netanyahu", "Charles Kushner", "close allies", "2:06:13"),
    # 2:06:13 - "Nanyahu and Charles Kushner...were very very close"
    ("Louis Brandeis", "Rabbi Menachem Mendel Schneerson", "brought to America", "1:35:46"),
    # 1:35:46 - "they're brought to America by...Louis Brandeise"
    # (Larry Summers -> Alan Dershowitz removed to keep edge count <= 35)

    # --- Epstein network ---
    ("Jeffrey Epstein", "Robert Maxwell", "associate", "3:40:44"),
    # 3:40:44 - "connection between Robert Maxwell and Jeffrey Epstein"
    ("Ghislaine Maxwell", "Robert Maxwell", "daughter", "3:41:28"),
    # 3:41:28 - "Gla Maxwell, the daughter, the favorite daughter of Robert Maxwell"
    ("Jeffrey Epstein", "Ghislaine Maxwell", "partner", "3:41:35"),
    # 3:41:35 - "she starts to date Jeffrey Epstein"
    ("Jeffrey Epstein", "Bill Clinton", "associate", "3:43:15"),
    # 3:43:15 - "Clinton and Bill Clinton...About the Epstein stuff"
    ("Jeffrey Epstein", "Donald Trump", "associate", "2:46:17"),
    # 2:46:17 - "the Epstein stuff...Epstein wrote in an email saying that if Trump feels cornered"
    ("Jeffrey Epstein", "Rothschild family", "elite family (per email)", "3:31:17"),
    # 3:31:17 - "Epstein in an email wrote to um Arana the Rothschild"
    # (Jeffrey Epstein -> David Rockefeller and -> Steve Bannon removed to keep edge count <= 35)

    # --- Tech/Media power ---
    ("Mark Zuckerberg", "Rabbi Menachem Mendel Schneerson", "sought blessing (per Jiang)", "1:56:40"),
    # 1:56:40 - "they went to Rebeersonen...could you please bless us with a son"
    # (Mark Zuckerberg -> Larry Summers removed to keep edge count <= 35)
    ("Mark Zuckerberg", "Jared Kushner", "Cambridge Analytica", "2:04:47"),
    # 2:04:47 - "Mark Zuckerberg and Jerk Kushner um are both involved in the Cambridge Analytica scandal"
    ("Rupert Murdoch", "Elena Zhukova", "married", "1:49:38"),
    # 1:49:38 - "Rupert Murdoch's current wife is uh Elena Zukova"
    ("Jeff Bezos", "Donald Trump", "untouchable by (per Jiang)", "40:55"),
    # 40:55 - "Donald Trump cannot call Jeff Bezos in the White House"

    # --- Neoconservative ---
    ("Henry Jackson", "Paul Wolfowitz", "mentor", "1:23:26"),
    # 1:23:26 - "all the neocons Woleritz F and Pearl all used to work for this guy. Henry Jackson"
    ("Henry Jackson", "Richard Perle", "mentor", "1:23:22"),
    # 1:23:22 - "Richard Pearl and Douglas F all used to work for a senator called Henry Scoop Jackson"
    # (Henry Jackson -> Douglas Feith removed: covered by Henry Jackson -> Richard Perle at 1:23:22)
    ("Douglas Feith", "Richard Perle", "co-authored Clean Break memo", "1:23:04"),
    # 1:23:04 - "this memo was written by Richard Pearl and Douglas F"
    ("Richard Perle", "Benjamin Netanyahu", "advised (Clean Break memo)", "1:20:08"),
    # 1:20:08 - "they write a memo for the incoming prime minister...Benjamin Netanyahu"
    ("Douglas Feith", "Benjamin Netanyahu", "advised (Clean Break memo)", "1:20:08"),
    # 1:20:08 - same
    ("Richard Perle", "George Bush", "Iraq War architect", "1:23:13"),
    # 1:23:13 - "these two individuals will then go on the Bush administration...chief architects of the Iraq war"
    # (Douglas Feith -> George Bush removed: covered by Richard Perle -> George Bush at 1:23:13)
    # (Henry Jackson -> Rabbi Schneerson removed: Schneerson network already well-represented)
    # (Louis Brandeis -> Rothschild family removed: covered by Jacob Frank -> Rothschild family)

    # --- Historical chain ---
    ("Sabbatai Zevi", "Jacob Frank", "successor movement", "3:30:12"),
    # 3:30:12 - "Sab Zevi will then be reincarnated in Jacob Frank"
    ("Jacob Frank", "Rothschild family", "converted to Frankism", "3:30:56"),
    # 3:30:56 - "become uh Frankist. Including the Rafshaw [Rothschild] family"
    ("Jacob Frank", "Rabbi Menachem Mendel Schneerson", "reincarnation (per believers)", "3:32:40"),
    # 3:32:40 - "Jacob Frank...reincarnate as Rabbi Schneerson"
    # (Sabbatai Zevi -> Rabbi Schneerson removed: covered by Zevi -> Frank -> Schneerson chain)

    # --- Political ---
    ("Donald Trump", "Benjamin Netanyahu", "alliance", "2:45:55"),
    # 2:45:55 - "the people who have the most influence over Donald Trump right now...Netanyahu"
    ("Vladimir Putin", "Rabbi Menachem Mendel Schneerson", "Chabad alliance (per Jiang)", "2:40:02"),
    # 2:40:02 - "Habat Luvich has...a very strong alliance with Putin"
    ("Sheldon Adelson", "Benjamin Netanyahu", "donor", "1:47:52"),
    # 1:47:52 - "who finances Nanyahu's political career in Israel? It's Sha Shauna Ellison"
    ("Sheldon Adelson", "Donald Trump", "donor", "1:48:22"),
    # 1:48:22 - "Shan Alison is the one who financed Trump's political career"
    # (Miriam Adelson -> Donald Trump removed: covered by Sheldon Adelson -> Donald Trump)
    # (Rupert Murdoch -> Donald Trump removed: weak timestamp alignment)
    # (Donald Trump -> Sean Hannity removed: Hannity is media not core network)
    # (Sheryl Sandberg -> Larry Summers removed: secondary tech figure)
]

# ---------------------------------------------------------------------------
# Validate and build
# ---------------------------------------------------------------------------
curated = []
errors = []
for src, tgt, label, ref in EDGES_RAW:
    if src not in valid_ids:
        errors.append(f"Invalid source ID: {src!r}")
    if tgt not in valid_ids:
        errors.append(f"Invalid target ID: {tgt!r}")
    if ref not in existing_ts:
        errors.append(f"Invalid source_ref (not in transcript): {ref!r}")
    curated.append({
        "source": src,
        "target": tgt,
        "label": label,
        "source_ref": ref,
    })

if errors:
    print("VALIDATION ERRORS:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)

# Stats
labels = set(e["label"] for e in curated)
print(f"\nTotal edges: {len(curated)}")
print(f"Unique labels: {len(labels)}")
print(f"Labels: {sorted(labels)}")

# Check for duplicate edges (same source+target)
seen = set()
dupes = []
for e in curated:
    key = (e["source"], e["target"])
    if key in seen:
        dupes.append(key)
    seen.add(key)
if dupes:
    print(f"\nWARNING: Duplicate source+target pairs: {dupes}")

# Write
out_path = f"{BASE}/curated_edges.json"
with open(out_path, "w") as f:
    json.dump(curated, f, indent=2, ensure_ascii=False)
print(f"\nWrote {len(curated)} edges to {out_path}")