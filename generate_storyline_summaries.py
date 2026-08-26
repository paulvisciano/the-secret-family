#!/usr/bin/env python3
"""Generate storyline_summary for each person from connections + Wikipedia data."""
import json
import os
import re
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))

def load_json(name):
    with open(os.path.join(HERE, name), "r", encoding="utf-8") as f:
        return json.load(f)

def build_adjacency(curated, connections):
    adj = defaultdict(list)
    for e in curated:
        label = e.get('label', '')
        adj[e['source']].append((e['target'], label, 'curated', 'outgoing'))
        adj[e['target']].append((e['source'], label, 'curated', 'incoming'))
    for e in connections:
        w = e.get('weight', 1)
        adj[e['source']].append((e['target'], '', w, 'auto', 'outgoing'))
        adj[e['target']].append((e['source'], '', w, 'auto', 'incoming'))
    return adj

def short_name(name):
    parts = name.split()
    if len(parts) <= 1:
        return name
    return parts[-1]

def first_sentence(text):
    if not text:
        return ''
    m = re.match(r'^(.+?[.!?])\s', text)
    return m.group(1) if m else text.split('.')[0] + '.'

def dedupe_neighbors(neighbors):
    seen = set()
    out = []
    for entry in neighbors:
        n = entry[0]
        if n not in seen:
            seen.add(n)
            out.append(entry)
    return out

def format_connection_list(names, max_count=5):
    if len(names) == 0:
        return ''
    if len(names) == 1:
        return names[0]
    if len(names) <= max_count:
        return ', '.join(names[:-1]) + ' and ' + names[-1]
    visible = names[:max_count]
    rest = len(names) - max_count
    return ', '.join(visible) + f' and {rest} other{"s" if rest > 1 else ""}'

INVERSE_LABELS = {
    'son-in-law': 'son-in-law of',
    'father': 'father of',
    'daughter': 'father of',
    'spouse': 'married to',
    'married': 'married to',
    'sought blessing': 'gave blessing to',
    'sought blessing (per Jiang)': 'gave blessing to',
    'Chabad member': 'connected to Chabad via',
    'donor': 'received donations from',
    'Harvard Chabad': 'connected via Harvard Chabad to',
    'close allies': 'a close ally of',
    'associate': 'an associate of',
    'partner': 'a partner of',
    'elite family (per email)': 'linked to the',
    'Cambridge Analytica': 'linked via Cambridge Analytica to',
    'untouchable by (per Jiang)': 'considers untouchable',
    'mentor': 'mentored by',
    'co-authored Clean Break memo': 'co-authored the Clean Break memo with',
    'advised (Clean Break memo)': 'advised',
    'Iraq War architect': 'an Iraq War architect alongside',
    'successor movement': 'successor to the movement of',
    'converted to Frankism': 'a connection of Frankist convert',
    'reincarnation (per believers)': 'believed to be a reincarnation of',
    'alliance': 'in alliance with',
    'Chabad alliance (per Jiang)': 'allied with Chabad via',
    'brought to America': 'brought to America by',
}

DIRECT_LABELS = {
    'son-in-law': 'father-in-law of',
    'father': 'son of',
    'daughter': 'daughter of',
    'spouse': 'married to',
    'married': 'married to',
    'sought blessing': 'sought the blessing of',
    'sought blessing (per Jiang)': 'sought the blessing of',
    'Chabad member': 'a Chabad member connected to',
    'donor': 'a donor to',
    'Harvard Chabad': 'connected to',
    'close allies': 'a close ally of',
    'associate': 'an associate of',
    'partner': 'a partner of',
    'elite family (per email)': 'linked to the',
    'Cambridge Analytica': 'linked to',
    'untouchable by (per Jiang)': 'considers untouchable',
    'mentor': 'mentor to',
    'co-authored Clean Break memo': 'co-authored the Clean Break memo with',
    'advised (Clean Break memo)': 'advised',
    'Iraq War architect': 'an architect of the Iraq War alongside',
    'successor movement': 'predecessor to the movement of',
    'converted to Frankism': 'converted to Frankism, linking to',
    'reincarnation (per believers)': 'considered a reincarnation by followers of',
    'alliance': 'in alliance with',
    'Chabad alliance (per Jiang)': 'allied with Chabad via',
    'brought to America': 'helped bring to America',
}

def describe_curated_relations(person_id, adj, people_by_id):
    curated_entries = []
    for entry in adj.get(person_id, []):
        if len(entry) >= 4 and entry[2] == 'curated':
            n, lbl, _, direction = entry[0], entry[1], entry[2], entry[3]
            curated_entries.append((n, lbl, direction))
    if not curated_entries:
        return ''
    phrases = []
    for n, lbl, direction in curated_entries:
        if not lbl:
            continue
        name_list = n
        if direction == 'outgoing':
            template = DIRECT_LABELS.get(lbl)
        else:
            template = INVERSE_LABELS.get(lbl)
        if template:
            phrases.append(template.format(name_list) if '{' in template else f"{template} {name_list}")
        else:
            phrases.append(f"connected to {name_list} ({lbl})")
    return '; '.join(phrases)

def generate_summary(person_id, adj, people_by_id):
    p = people_by_id[person_id]
    wiki_desc = p.get('wikipedia_description') or ''
    wiki_summary = p.get('wikipedia_summary') or ''
    tier = p.get('tier', 4)
    category = p.get('category', '')
    sn = short_name(person_id)

    sentences = []

    intro = first_sentence(wiki_summary) if wiki_summary else wiki_desc
    if not intro:
        intro = person_id
    sentences.append(intro)

    all_neighbors = dedupe_neighbors(adj.get(person_id, []))
    curated_desc = describe_curated_relations(person_id, adj, people_by_id)

    auto_neighbors = []
    for entry in all_neighbors:
        if len(entry) >= 4 and entry[2] == 'auto':
            auto_neighbors.append((entry[0], entry[3] if len(entry) > 3 else 1))
        elif len(entry) == 3 and entry[2] == 'auto':
            auto_neighbors.append((entry[0], 1))
    auto_neighbors.sort(key=lambda x: -x[1])
    top_auto = [n for n, w in auto_neighbors[:8]]

    connection_parts = []
    if curated_desc:
        connection_parts.append(curated_desc)
    if top_auto:
        auto_list = format_connection_list(top_auto)
        if curated_desc:
            connection_parts.append(f"frequently co-mentioned with {auto_list}")
        else:
            connection_parts.append(f"closely associated with {auto_list} in the interview")
    if connection_parts:
        joined = '; '.join(connection_parts)
        first_word = joined.split(' ')[0] if joined else ''
        starts_with_verb = first_word.lower() in ('gave', 'sought', 'brought', 'converted', 'considered',
                                                     'mentored', 'advised', 'received', 'believes', 'considers',
                                                     'helped')
        prefix = sn + ' ' if starts_with_verb else sn + ' is '
        sentences.append(prefix + joined + '.' if joined else '')

    tier_labels = {1: 'the top tier of the power hierarchy',
                   2: 'the second tier of influence',
                   3: 'a secondary tier',
                   4: 'the periphery of the network'}
    if category:
        sentences.append(f"Classified under {category}, {sn} sits in {tier_labels.get(tier, 'an unspecified tier')}.")

    transcript_count = len(p.get('transcript_sources', []))
    if transcript_count >= 5:
        sentences.append(f"A frequently discussed figure in the interview with {transcript_count} transcript references.")
    elif transcript_count >= 2:
        sentences.append(f"Mentioned {transcript_count} times in the interview.")
    elif transcript_count == 1:
        sentences.append(f"Mentioned once in the interview.")
    else:
        sentences.append(f"Not directly named in the transcript, but included in the interview's power framework.")

    return ' '.join(sentences)

def main():
    data = load_json('people_data.json')
    curated = load_json('curated_edges.json')
    connections = load_json('connections.json')
    adj = build_adjacency(curated, connections)
    people_by_id = {p['id']: p for p in data}

    updated = 0
    for p in data:
        summary = generate_summary(p['id'], adj, people_by_id)
        if summary != p.get('storyline_summary'):
            p['storyline_summary'] = summary
            updated += 1

    with open(os.path.join(HERE, 'people_data.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"[storyline] Generated summaries for {updated} people")

if __name__ == '__main__':
    main()