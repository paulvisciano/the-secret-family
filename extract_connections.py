#!/usr/bin/env python3
"""Extract connections from transcript by co-mention detection.

Parses transcript.txt (lines of form "MM:SS - text" or "H:MM:SS - text"),
matches ~70 people from people.md by canonical name + aliases using
case-insensitive word-boundary regex, and detects co-mentions within a
+/-5 line sliding window. Outputs edges with weight >= 2 to
connections.json and per-person mention counts to mentions.json.

Uses ONLY the Python standard library (re, json, collections, os).
"""

import json
import os
import re
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
TRANSCRIPT = os.path.join(HERE, "transcript.txt")
CONNECTIONS_OUT = os.path.join(HERE, "connections.json")
MENTIONS_OUT = os.path.join(HERE, "mentions.json")

# ---------------------------------------------------------------------------
# Alias -> canonical name mapping
#
# Each canonical name maps to a list of aliases (including the canonical name
# itself). Matching is case-insensitive with word boundaries. Longer aliases
# are matched first so that e.g. "Ivanka Trump" is matched as one span rather
# than two ("Ivanka" + "Trump"), and "Charles Kushner" wins over "Kushner".
# ---------------------------------------------------------------------------
PEOPLE = {
    # --- US Politics / Trump Circle ---
    "Donald Trump": ["Donald J. Trump", "Donald Trump", "Trump"],
    "Jared Kushner": ["Jared Kushner", "Kushner"],
    "Charles Kushner": ["Charles Kushner"],
    "Ivanka Trump": ["Ivanka Trump", "Ivanka"],
    "Natalie Harp": ["Natalie Harp"],
    "Steve Bannon": ["Steve Bannon", "Bannon"],
    "Chris Christie": ["Chris Christie", "Christie"],
    "Laura Loomer": ["Laura Loomer"],
    "Sean Hannity": ["Sean Hannity", "Hannity"],
    "Bernie Sanders": ["Bernie Sanders"],
    "Joe Biden": ["Joe Biden", "Biden"],
    "Kamala Harris": ["Kamala Harris"],
    "Bill Clinton": ["Bill Clinton"],
    "George Bush": ["George Bush", "George W. Bush"],
    "Wesley Clark": ["Wesley Clark"],

    # --- Israel / Netanyahu ---
    "Benjamin Netanyahu": ["Benjamin Netanyahu", "Netanyahu", "Bibi"],
    "Sara Netanyahu": ["Sara Netanyahu"],
    "Ariel Sharon": ["Ariel Sharon"],
    "Yasser Arafat": ["Yasser Arafat", "Arafat"],

    # --- Epstein / Maxwell Network ---
    "Jeffrey Epstein": ["Jeffrey Epstein", "Epstein"],
    "Ghislaine Maxwell": ["Ghislaine Maxwell", "Ghislaine"],
    "Robert Maxwell": ["Robert Maxwell"],

    # --- Tech / Media / Finance ---
    "Mark Zuckerberg": ["Mark Zuckerberg", "Zuckerberg"],
    "Jeff Bezos": ["Jeff Bezos", "Bezos"],
    "Larry Page": ["Larry Page"],
    "Rupert Murdoch": ["Rupert Murdoch", "Murdoch"],
    "Elena Zukova": ["Elena Zukova"],
    "Jimmy Kimmel": ["Jimmy Kimmel", "Kimmel"],
    "Sheryl Sandberg": ["Sheryl Sandberg", "Sandberg"],
    "Jack Ma": ["Jack Ma"],
    "Peter Thiel": ["Peter Thiel", "Thiel"],
    "Malcolm Gladwell": ["Malcolm Gladwell", "Gladwell"],
    "Amy Goodman": ["Amy Goodman"],
    "Ben Shapiro": ["Ben Shapiro", "Shapiro"],

    # --- Neoconservatives / Think Tank Figures ---
    'Henry "Scoop" Jackson': ['Henry "Scoop" Jackson', "Scoop Jackson", "Henry Jackson"],
    "Paul Wolfowitz": ["Paul Wolfowitz", "Wolfowitz"],
    "Richard Perle": ["Richard Perle", "Perle"],
    "Douglas Feith": ["Douglas Feith", "Feith"],
    "Larry Summers": ["Larry Summers", "Summers"],
    "Alan Dershowitz": ["Alan Dershowitz", "Dershowitz"],
    "Louis Brandeis": ["Louis Brandeis", "Brandeis"],

    # --- Financial Dynasties ---
    "Rothschild family": ["Rothschild family", "Rothschild"],
    "David Rockefeller": ["David Rockefeller", "Rockefeller"],
    "Sheldon Adelson": ["Sheldon Adelson", "Adelson", "Adlesen"],
    "Miriam Adelson": ["Miriam Adelson"],

    # --- Chabad-Lubavitch / Religious Figures ---
    "Rabbi Menachem Mendel Schneerson": [
        "Rabbi Menachem Mendel Schneerson",
        "Menachem Mendel Schneerson",
        "Rabbi Schneerson",
        "Schneerson",
        "Rebbe",
        "Menachem Schneerson",
    ],
    "Jacob Frank": ["Jacob Frank"],
    "Sabbatai Zevi": ["Sabbatai Zevi", "Sabbatai", "Zevi"],
    "King David": ["King David"],
    "Abraham": ["Abraham"],
    "Isaac": ["Isaac"],
    "Samuel": ["Samuel"],
    "Adam": ["Adam"],
    "Eve": ["Eve"],
    "Miriam": ["Miriam"],
    "Jesus": ["Jesus"],

    # --- World Leaders ---
    "Vladimir Putin": ["Vladimir Putin", "Putin"],
    "Xi Jinping": ["Xi Jinping"],
    "Mao Zedong": ["Mao Zedong", "Mao"],
    "Deng Xiaoping": ["Deng Xiaoping", "Deng"],
    "Nicolas Maduro": ["Nicolas Maduro", "Maduro"],
    "Saddam Hussein": ["Saddam Hussein", "Saddam"],
    "Adolf Hitler": ["Adolf Hitler", "Hitler"],
    "Volodymyr Zelensky": ["Volodymyr Zelensky", "Zelensky"],
    "Ayatollah Khamenei": ["Ayatollah Khamenei", "Khamenei"],

    # --- China-Related Individuals ---
    "Chun Liwen": ["Chun Liwen"],
    "Professor Jiang": ["Professor Jiang", "Jiang"],

    # --- Other Individuals Mentioned ---
    "Natalie Portman": ["Natalie Portman"],
    "Dan Bilzerian": ["Dan Bilzerian", "Bilzerian"],
    "Randy Fine": ["Randy Fine"],
    "Sam Tripley": ["Sam Tripley"],
    "Andrew Bamonte": ["Andrew Bamonte"],
    "Adam Curtis": ["Adam Curtis"],
    "Adam Kenmont": ["Adam Kenmont"],
    "Ben Landau": ["Ben Landau"],
    "Joe Katsman": ["Joe Katsman"],
}

# First-declaration wins on alias collision: more specific people (Ivanka
# Trump) and family full names (Charles Kushner) are listed before bare
# surnames (Kushner), so the right canonical name wins.
ALIAS_TO_CANONICAL = {}
for _canon, _aliases in PEOPLE.items():
    for _al in _aliases:
        if _al not in ALIAS_TO_CANONICAL:
            ALIAS_TO_CANONICAL[_al] = _canon

# Longest aliases first: greedy span resolution prevents "Trump" inside
# "Ivanka Trump" from matching as a separate (Donald Trump) person.
ALIASES_SORTED = sorted(ALIAS_TO_CANONICAL.keys(), key=len, reverse=True)
ALIAS_REGEXES = [
    (al, re.compile(r"\b" + re.escape(al) + r"\b", re.IGNORECASE))
    for al in ALIASES_SORTED
]

WINDOW = 5
MIN_WEIGHT = 2


def parse_transcript(path):
    """Parse transcript supporting both MM:SS and H:MM:SS timestamps.

    Returns list of (timestamp_str, text). The timestamp_str preserves the
    original form (e.g. "14:34" or "1:34:00"). Non-timestamped continuation
    lines are appended to the previous entry's text.
    """
    full_re = re.compile(r"^(\d{1,3}):(\d{2})(?::(\d{2}))? - (.*)$")
    entries = []
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            m = full_re.match(line)
            if not m:
                if entries:
                    ts, prev_text = entries[-1]
                    entries[-1] = (ts, prev_text + " " + line)
                continue
            g1, g2, g3, text = m.group(1), m.group(2), m.group(3), m.group(4)
            ts = f"{g1}:{g2}:{g3}" if g3 is not None else f"{g1}:{g2}"
            entries.append((ts, text))
    return entries


def match_people(text):
    """Return the set of canonical people mentioned in `text`.

    Uses a span-based non-overlapping matcher: scan the text, at each position
    try the longest alias first, and once a span is consumed skip past it.
    This guarantees e.g. "Ivanka Trump" yields only Ivanka Trump, not also
    Donald Trump (from the "Trump" suffix).
    """
    found = set()
    pos = 0
    n = len(text)
    while pos < n:
        best_end = -1
        best_canon = None
        for alias, rx in ALIAS_REGEXES:
            m = rx.search(text, pos)
            if m is None:
                continue
            start, end = m.start(), m.end()
            if best_end < 0 or start < best_start or (start == best_start and end > best_end):
                best_start, best_end = start, end
                best_canon = ALIAS_TO_CANONICAL[alias]
        if best_end < 0:
            break
        if best_canon is not None:
            found.add(best_canon)
        pos = best_end
    return found


def main():
    entries = parse_transcript(TRANSCRIPT)
    n = len(entries)
    print(f"Parsed {n} transcript entries")

    # Per-line people sets.
    line_people = [match_people(text) for _, text in entries]

    mentions = defaultdict(lambda: {"count": 0, "timestamps": []})
    for i, (ts, _) in enumerate(entries):
        for person in line_people[i]:
            d = mentions[person]
            d["count"] += 1
            d["timestamps"].append(ts)

    # +/-WINDOW sliding window: every distinct pair co-mentioned within the
    # 11-line window gets +1 weight and the center-line timestamp recorded.
    edges = defaultdict(lambda: {"weight": 0, "refs": []})
    for i in range(n):
        lo = max(0, i - WINDOW)
        hi = min(n - 1, i + WINDOW)
        window_people = set()
        for j in range(lo, hi + 1):
            window_people |= line_people[j]
        if len(window_people) < 2:
            continue
        ts = entries[i][0]
        ordered = sorted(window_people)
        for a_idx in range(len(ordered)):
            for b_idx in range(a_idx + 1, len(ordered)):
                e = edges[(ordered[a_idx], ordered[b_idx])]
                e["weight"] += 1
                e["refs"].append(ts)

    # Build filtered output: weight >= MIN_WEIGHT, sorted by weight desc.
    out_edges = []
    for (a, b), data in edges.items():
        if data["weight"] >= MIN_WEIGHT:
            # Deduplicate refs while preserving order.
            seen = set()
            dedup_refs = []
            for r in data["refs"]:
                if r not in seen:
                    seen.add(r)
                    dedup_refs.append(r)
            out_edges.append({
                "source": a,
                "target": b,
                "weight": data["weight"],
                "transcript_refs": dedup_refs,
            })
    out_edges.sort(key=lambda e: (-e["weight"], e["source"], e["target"]))

    with open(CONNECTIONS_OUT, "w", encoding="utf-8") as fh:
        json.dump(out_edges, fh, indent=2, ensure_ascii=False)
    print(f"Wrote {len(out_edges)} edges (weight>={MIN_WEIGHT}) to {CONNECTIONS_OUT}")

    # mentions.json — sort by count desc then name.
    mentions_out = {
        person: {"count": d["count"], "timestamps": d["timestamps"]}
        for person, d in sorted(mentions.items(), key=lambda kv: (-kv[1]["count"], kv[0]))
        if d["count"] > 0
    }
    with open(MENTIONS_OUT, "w", encoding="utf-8") as fh:
        json.dump(mentions_out, fh, indent=2, ensure_ascii=False)
    print(f"Wrote {len(mentions_out)} people mentions to {MENTIONS_OUT}")

    # Quick summary to stdout for verification.
    print("\nTop 15 edges:")
    for e in out_edges[:15]:
        print(f"  {e['weight']:4d}  {e['source']}  --  {e['target']}  ({len(e['transcript_refs'])} refs)")
    print("\nTop 15 mentioned people:")
    for i, (person, d) in enumerate(mentions_out.items()):
        if i >= 15:
            break
        print(f"  {d['count']:4d}  {person}")


if __name__ == "__main__":
    main()