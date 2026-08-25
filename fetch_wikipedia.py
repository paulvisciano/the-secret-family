#!/usr/bin/env python3
"""
fetch_wikipedia.py

Reads nodes.json (60 graph nodes with wikipedia_title), fetches Wikipedia
summaries + thumbnails + infobox-derived timelines for each, and outputs
people_data.json. Raw API responses are cached in wikipedia_cache/.

Rate limit: 1 request / second to Wikipedia.
Usage: /opt/homebrew/bin/python3.11 fetch_wikipedia.py
"""

import json
import os
import re
import time
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
NODES_PATH = BASE_DIR / "nodes.json"
MENTIONS_PATH = BASE_DIR / "mentions.json"
TRANSCRIPT_PATH = BASE_DIR / "transcript.txt"
CACHE_DIR = BASE_DIR / "wikipedia_cache"
OUT_PATH = BASE_DIR / "people_data.json"

REST_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
PARSE_URL = (
    "https://en.wikipedia.org/w/api.php?action=parse&page={title}"
    "&prop=wikitext&format=json"
)

USER_AGENT = "TheSecretFamily/1.0 (educational research; contact: local)"

RATE_LIMIT_SEC = 1.2

# Max transcript sources per person (cap at 10-15 per spec)
MAX_TRANSCRIPT_SOURCES = 10
# Max timeline entries per person
MAX_TIMELINE = 15


def ensure_dirs():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def cache_paths(title):
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", title)[:120]
    return (
        CACHE_DIR / f"{safe}_summary.json",
        CACHE_DIR / f"{safe}_parse.json",
    )


def fetch_with_retry(url, max_retries=4):
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                wait = (2 ** attempt) * 3
                print(f"    HTTP {e.code}, backing off {wait}s (attempt {attempt+1})")
                time.sleep(wait)
                continue
            raise
        except Exception as e:
            if attempt < max_retries - 1:
                wait = (2 ** attempt) * 2
                print(f"    error {e}, retry in {wait}s (attempt {attempt+1})")
                time.sleep(wait)
                continue
            raise


def get_summary(title):
    summary_path, _ = cache_paths(title)
    if summary_path.exists():
        try:
            cached = json.loads(summary_path.read_text(encoding="utf-8"))
            if not (isinstance(cached, dict) and "_error" in cached):
                return cached
        except Exception:
            pass
    url = REST_SUMMARY_URL.format(title=urllib.parse.quote(title, safe=""))
    try:
        raw = fetch_with_retry(url)
        summary_path.write_text(raw, encoding="utf-8")
        time.sleep(RATE_LIMIT_SEC)
        return json.loads(raw)
    except urllib.error.HTTPError as e:
        marker = {"_error": e.code}
        summary_path.write_text(json.dumps(marker), encoding="utf-8")
        time.sleep(RATE_LIMIT_SEC)
        return marker
    except Exception as e:
        time.sleep(RATE_LIMIT_SEC)
        return {"_error": str(e)}


def get_parse(title):
    _, parse_path = cache_paths(title)
    if parse_path.exists():
        try:
            cached = json.loads(parse_path.read_text(encoding="utf-8"))
            if not (isinstance(cached, dict) and "_error" in cached):
                return cached
        except Exception:
            pass
    url = PARSE_URL.format(title=urllib.parse.quote(title, safe=""))
    try:
        raw = fetch_with_retry(url)
        parse_path.write_text(raw, encoding="utf-8")
        time.sleep(RATE_LIMIT_SEC)
        return json.loads(raw)
    except Exception as e:
        time.sleep(RATE_LIMIT_SEC)
        return {"_error": str(e)}


# ---------------------------------------------------------------------------
# Infobox / wikitext parsing
# ---------------------------------------------------------------------------

# {{Infobox person | birth_date = {{birth date and age|df=y|1946|6|14}} }}
BIRTH_DATE_RE = re.compile(
    r"\|\s*birth_date\s*=\s*([^\n|]*?)(?:\||\n|\}\})", re.IGNORECASE
)
DEATH_DATE_RE = re.compile(
    r"\|\s*death_date\s*=\s*([^\n|]*?)(?:\||\n|\}\})", re.IGNORECASE
)
BIRTH_YEAR_RE = re.compile(r"\|\s*birth_year\s*=\s*(\d{3,4})", re.IGNORECASE)
DEATH_YEAR_RE = re.compile(r"\|\s*death_year\s*=\s*(\d{3,4})", re.IGNORECASE)

YEAR_RE = re.compile(r"(1[5-9]\d{2}|20\d{2})")

# Infobox fields useful for timeline events. Each maps to a human-readable
# event template. Only fields that represent temporal milestones are included.
# Metadata fields (party, occupation, nationality, etc.) are excluded since
# they don't represent point-in-time events.
TIMELINE_FIELDS = [
    ("alma_mater", "Education: {val}"),
    ("spouse", "Married: {val}"),
    ("resting_place", "Buried at: {val}"),
    ("death_place", "Died in: {val}"),
    ("birth_place", "Born in: {val}"),
]


def strip_wiki_markup(s):
    if s is None:
        return ""
    s = str(s)
    s = re.sub(r"<!--.*?-->", "", s, flags=re.DOTALL)
    s = re.sub(r"<!--.*", "", s, flags=re.DOTALL)
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.DOTALL)
    s = re.sub(r"<ref[^/]*/>", "", s)
    s = re.sub(r"<ref[^>]*>", "", s)
    for _ in range(5):
        s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"\[\[([^\]|]*?)\|([^\]]*)\]\]", r"\2", s)
    s = re.sub(r"\[\[([^\]]*?)\]\]", r"\1", s)
    s = re.sub(r"\[\[([^\]]*)", r"\1", s)
    s = re.sub(r"\[https?://[^\s]+\s+([^\]]+)\]", r"\1", s)
    s = re.sub(r"\[https?://[^\s]+\]", "", s)
    s = re.sub(r"'''+", "", s)
    s = re.sub(r"[{}]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_year_from_value(val, fallback_year=None):
    """Extract a plausible 4-digit year from a wikitext field value.
    If no year is found in the value, return fallback_year (used to keep
    year-less infobox fields like 'occupation' on the timeline under the
    person's birth year so they aren't silently dropped)."""
    if not val:
        return fallback_year
    # Look at the raw (with templates) - common patterns:
    # {{birth date and age|df=y|1946|6|14}}
    m = re.search(r"\|\s*(1[5-9]\d{2}|20\d{2})\b", val)
    if m:
        return int(m.group(1))
    m = YEAR_RE.search(val)
    if m:
        return int(m.group(1))
    return fallback_year


def parse_infobox_field(wikitext, field_name):
    """Return the raw value of an infobox field, handling nested braces."""
    # Find | field_name = and then capture up to the next top-level | or }}
    pattern = re.compile(
        r"\|\s*" + re.escape(field_name) + r"\s*=\s*",
        re.IGNORECASE,
    )
    m = pattern.search(wikitext)
    if not m:
        return None
    start = m.end()
    depth = 0
    i = start
    while i < len(wikitext):
        c = wikitext[i]
        if c == "{":
            depth += 1
        elif c == "}":
            if depth == 0:
                break
            depth -= 1
        elif c == "|" and depth == 0:
            break
        elif c == "\n" and depth == 0:
            # Field values may span lines but we cap at next newline at depth 0
            # to avoid grabbing the whole infobox. Some infoboxes keep value on
            # next line, so peek: if next non-space char is | or }, stop here.
            j = i + 1
            while j < len(wikitext) and wikitext[j] in " \t":
                j += 1
            if j < len(wikitext) and wikitext[j] in "|}":
                break
        i += 1
    return wikitext[start:i].strip()


def extract_infobox(wikitext):
    """Return the inner text of the first {{Infobox ...}} block, or None."""
    m = re.search(r"\{\{\s*[Ii]nfobox", wikitext)
    if not m:
        return None
    start = m.start()
    # find matching closing braces
    depth = 0
    i = start
    while i < len(wikitext):
        if wikitext[i] == "{":
            depth += 1
        elif wikitext[i] == "}":
            depth -= 1
            if depth == 0:
                return wikitext[start : i + 1]
        i += 1
    return wikitext[start:]


def build_timeline(wikitext, birth_year, death_year):
    """Build a timeline list from the infobox + birth/death years."""
    timeline = []
    seen = set()  # dedupe by (year, event)

    def add(year, event):
        if event is None or not event:
            return
        if year is None:
            year = birth_year
        if year is None:
            return
        key = (year, event[:60])
        if key in seen:
            return
        seen.add(key)
        timeline.append({"year": int(year), "event": event})

    infobox = extract_infobox(wikitext) or ""

    # Birth place
    bp = parse_infobox_field(infobox, "birth_place")
    bp_clean = strip_wiki_markup(bp)
    if birth_year is not None:
        if bp_clean:
            add(birth_year, f"Born in {bp_clean}")
        else:
            add(birth_year, "Born")

    # Field-based events
    for field, tmpl in TIMELINE_FIELDS:
        if field in ("birth_place", "death_place"):
            continue
        raw = parse_infobox_field(infobox, field)
        if not raw:
            continue
        clean = strip_wiki_markup(raw)
        if not clean:
            continue
        year = extract_year_from_value(raw)
        if year is None:
            continue
        add(year, tmpl.format(val=clean[:80]))

    # Death place
    dp = parse_infobox_field(infobox, "death_place")
    dp_clean = strip_wiki_markup(dp)
    if death_year is not None:
        if dp_clean:
            add(death_year, f"Died in {dp_clean}")
        else:
            add(death_year, "Died")

    # Sort by year
    timeline.sort(key=lambda e: e["year"])
    if len(timeline) > MAX_TIMELINE:
        timeline = timeline[:MAX_TIMELINE]
    return timeline


def parse_years(infobox, node_birth, node_death):
    """Parse birth/death years from infobox, falling back to node.json."""
    birth_year = node_birth
    death_year = node_death

    if infobox:
        bd = parse_infobox_field(infobox, "birth_date")
        if bd:
            y = extract_year_from_value(bd)
            if y:
                birth_year = y
        dd = parse_infobox_field(infobox, "death_date")
        if dd:
            y = extract_year_from_value(dd)
            if y:
                death_year = y
        # Some use birth_year/death_year directly
        by = parse_infobox_field(infobox, "birth_year")
        if by:
            y = extract_year_from_value(by)
            if y:
                birth_year = y
        dy = parse_infobox_field(infobox, "death_year")
        if dy:
            y = extract_year_from_value(dy)
            if y:
                death_year = y
    return birth_year, death_year


# ---------------------------------------------------------------------------
# Transcript sources
# ---------------------------------------------------------------------------


def parse_ts_to_seconds(ts):
    """Parse 'MM:SS' or 'H:MM:SS' to seconds."""
    parts = ts.split(":")
    parts = [int(p) for p in parts]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return None


def load_transcript_lines(transcript_path):
    """Return list of (seconds, ts_str, text)."""
    lines = []
    if not transcript_path.exists():
        return lines
    with transcript_path.open(encoding="utf-8") as f:
        cur_ts = None
        cur_text = []
        for line in f:
            line = line.rstrip("\n")
            m = re.match(r"^\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*-\s*(.*)$", line)
            if m:
                if cur_ts is not None:
                    lines.append(
                        (parse_ts_to_seconds(cur_ts), cur_ts, " ".join(cur_text).strip())
                    )
                cur_ts = m.group(1)
                cur_text = [m.group(2)]
            else:
                if cur_ts is not None:
                    cur_text.append(line.strip())
        if cur_ts is not None:
            lines.append(
                (parse_ts_to_seconds(cur_ts), cur_ts, " ".join(cur_text).strip())
            )
    return lines


def find_context_for_ts(transcript_lines, ts_str, window=1):
    """Return concatenated transcript text around the given timestamp."""
    target = parse_ts_to_seconds(ts_str)
    if target is None:
        return ""
    # Find the closest line
    best_idx = None
    best_diff = None
    for idx, (sec, _ts, _text) in enumerate(transcript_lines):
        diff = abs(sec - target)
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_idx = idx
    if best_idx is None:
        return ""
    lo = max(0, best_idx - window)
    hi = min(len(transcript_lines), best_idx + window + 1)
    return " ".join(transcript_lines[i][2] for i in range(lo, hi)).strip()


def build_transcript_sources(person_id, mentions, transcript_lines):
    """Build transcript_sources list for a person from mentions.json."""
    if not mentions or person_id not in mentions:
        return []
    entry = mentions[person_id]
    tss = entry.get("timestamps", [])
    if not tss:
        return []
    # Spread selection across the full list to get a representative sample,
    # capped at MAX_TRANSCRIPT_SOURCES.
    if len(tss) <= MAX_TRANSCRIPT_SOURCES:
        selected = tss
    else:
        # Evenly spaced sample
        step = len(tss) / MAX_TRANSCRIPT_SOURCES
        selected = [tss[int(i * step)] for i in range(MAX_TRANSCRIPT_SOURCES)]
    out = []
    for ts in selected:
        ctx = find_context_for_ts(transcript_lines, ts, window=1)
        out.append({"timestamp": ts, "context": ctx[:300]})
    return out


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def extract_timeline_from_summary(summary_text, birth_year, death_year):
    if not summary_text:
        return []
    events = []
    seen = set()
    def add(year, event):
        event = event.strip()
        key = (year, event[:60])
        if key in seen or year is None or not event:
            return
        seen.add(key)
        events.append({"year": int(year), "event": event})

    sentences = re.split(r'(?<=[.!?])\s+', summary_text)
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 15 or len(sent) > 250:
            continue
        years = YEAR_RE.findall(sent)
        if not years:
            continue
        first_year = int(years[0])

        # Shorten the sentence into a concise event description
        # Strategy: find the year in the sentence, take ~60 chars of context around it
        year_pos = sent.find(str(first_year))
        if year_pos == -1:
            continue

        # Take a window around the year mention
        start = max(0, year_pos - 30)
        end = min(len(sent), year_pos + 40)
        snippet = sent[start:end].strip()

        # Clean up snippet boundaries
        if start > 0:
            # Find first space to avoid cutting words
            sp = snippet.find(' ')
            if sp > 0:
                snippet = snippet[sp+1:]
        if end < len(sent):
            # Find last space
            sp = snippet.rfind(' ')
            if sp > 0:
                snippet = snippet[:sp]

        snippet = snippet.strip()
        if snippet and len(snippet) >= 10:
            # Capitalize first letter
            snippet = snippet[0].upper() + snippet[1:]
            add(first_year, snippet)

    events.sort(key=lambda e: e["year"])
    return events[:MAX_TIMELINE]


def process_node(node, mentions, transcript_lines):
    title = node.get("wikipedia_title")
    person_id = node["id"]

    record = {
        "id": person_id,
        "tier": node.get("tier"),
        "category": node.get("category"),
        "era": node.get("era"),
        "birth_year": node.get("birth_year"),
        "death_year": node.get("death_year"),
        "image": None,
        "wikipedia_url": None,
        "wikipedia_summary": None,
        "wikipedia_description": None,
        "timeline": [],
        "transcript_sources": build_transcript_sources(
            person_id, mentions, transcript_lines
        ),
    }

    if not title:
        return record

    # REST summary
    summary = get_summary(title)
    if isinstance(summary, dict) and "_error" not in summary:
        record["wikipedia_summary"] = summary.get("extract")
        record["wikipedia_description"] = summary.get("description")
        content_urls = summary.get("content_urls") or {}
        desktop = content_urls.get("desktop") or {}
        record["wikipedia_url"] = desktop.get("page")
        thumb = summary.get("thumbnail") or {}
        if thumb:
            record["image"] = thumb.get("source")
        # If no thumbnail, try originalimage
        if not record["image"]:
            orig = summary.get("originalimage") or {}
            if orig:
                record["image"] = orig.get("source")

    # Parse API for wikitext
    parse = get_parse(title)
    wikitext = None
    if isinstance(parse, dict) and "parse" in parse:
        wikitext = parse["parse"].get("wikitext", {}).get("*")

    infobox = extract_infobox(wikitext) if wikitext else None

    # Years
    by, dy = parse_years(infobox, record["birth_year"], record["death_year"])
    record["birth_year"] = by
    record["death_year"] = dy

    # Timeline
    if wikitext:
        record["timeline"] = build_timeline(wikitext, by, dy)
    elif by is not None:
        tl = [{"year": int(by), "event": "Born"}]
        if dy is not None:
            tl.append({"year": int(dy), "event": "Died"})
        record["timeline"] = tl

    summary_events = extract_timeline_from_summary(
        record.get("wikipedia_summary"), by, dy
    )
    if summary_events:
        existing = {(e["year"], e["event"][:60]) for e in record["timeline"]}
        for e in summary_events:
            key = (e["year"], e["event"][:60])
            if key not in existing:
                record["timeline"].append(e)
                existing.add(key)
        record["timeline"].sort(key=lambda e: e["year"])
        if len(record["timeline"]) > MAX_TIMELINE:
            record["timeline"] = record["timeline"][:MAX_TIMELINE]

    return record


def main():
    ensure_dirs()

    with NODES_PATH.open(encoding="utf-8") as f:
        nodes_data = json.load(f)
    graph = nodes_data.get("graph", [])
    print(f"Loaded {len(graph)} graph nodes")

    mentions = {}
    if MENTIONS_PATH.exists():
        with MENTIONS_PATH.open(encoding="utf-8") as f:
            mentions = json.load(f)
    print(f"Loaded {len(mentions)} mentions")

    transcript_lines = load_transcript_lines(TRANSCRIPT_PATH)
    print(f"Loaded {len(transcript_lines)} transcript lines")

    results = []
    for i, node in enumerate(graph, 1):
        title = node.get("wikipedia_title", "(none)")
        print(f"[{i}/{len(graph)}] {node['id']} -> {title}")
        rec = process_node(node, mentions, transcript_lines)
        results.append(rec)
        # Write incrementally so partial runs are usable
        with OUT_PATH.open("w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(results)} entries to {OUT_PATH}")

    # Summary stats
    with_images = sum(1 for r in results if r.get("image"))
    with_summary = sum(1 for r in results if r.get("wikipedia_summary"))
    with_timeline = sum(1 for r in results if r.get("timeline"))
    print(
        f"Stats: {with_images}/{len(results)} images "
        f"({100*with_images/len(results):.0f}%), "
        f"{with_summary}/{len(results)} summaries "
        f"({100*with_summary/len(results):.0f}%), "
        f"{with_timeline}/{len(results)} timelines"
    )


if __name__ == "__main__":
    main()