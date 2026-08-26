#!/usr/bin/env python3
"""Generate storyline_summary for each person based on transcript sources + Wikipedia.

For each person, produces a 2-4 sentence summary that:
1. Identifies who they are (from Wikipedia description/summary)
2. Describes their role in the interview's narrative (from transcript source contexts)

Outputs updated people_data.json with a new 'storyline_summary' field.
Uses only standard library.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

def load_data():
    with open(os.path.join(HERE, "people_data.json"), "r", encoding="utf-8") as f:
        return json.load(f)

def clean_context(text):
    """Clean up a transcript context snippet."""
    # Remove timestamp prefixes
    text = re.sub(r'^\d+:\d+(?::\d+)?\s*-\s*', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_transcript_themes(sources):
    """Extract key themes from transcript source contexts."""
    if not sources:
        return []
    contexts = [clean_context(s.get('context', '')) for s in sources]
    # Return the most substantial contexts (longer ones tend to be more informative)
    contexts.sort(key=len, reverse=True)
    return contexts[:5]

def generate_summary(person):
    """Generate a storyline summary for a person."""
    name = person['id']
    wiki_desc = person.get('wikipedia_description') or ''
    wiki_summary = person.get('wikipedia_summary') or ''
    tier = person.get('tier', 4)
    category = person.get('category', '')
    era = person.get('era', '')
    transcript_sources = person.get('transcript_sources', [])
    timeline = person.get('timeline', [])

    name_parts = name.split()
    if len(name_parts) > 1:
        last = name_parts[-1]
        if last in ('Schneerson', 'Epstein', 'Trump', 'Netanyahu', 'Kushner', 'Maxwell',
                     'Murdoch', 'Zuckerberg', 'Putin', 'Hitler', 'Frank', 'Jackson'):
            short_name = last
        elif last == 'Sandberg':
            short_name = 'Sandberg'
        else:
            short_name = name_parts[-1]
    else:
        short_name = name

    parts = []

    # Part 1: Who they are (from Wikipedia)
    if wiki_desc:
        parts.append(wiki_desc)
    elif wiki_summary:
        # Use first sentence of wiki summary
        first_sent = wiki_summary.split('.')[0] + '.'
        parts.append(first_sent)

    # Part 2: Their role in the interview
    if transcript_sources:
        contexts = extract_transcript_themes(transcript_sources)
        mention_count = len(transcript_sources)

        if mention_count >= 5:
            mention_str = f"a frequently discussed figure ({mention_count} mentions)"
        elif mention_count >= 3:
            mention_str = f"discussed multiple times ({mention_count} mentions)"
        elif mention_count == 2:
            mention_str = "mentioned twice"
        else:
            mention_str = "mentioned once"

        best_context = None
        for ctx in contexts:
            if len(ctx) > 60 and not ctx.startswith('>>'):
                best_context = ctx
                break
        if not best_context and contexts:
            best_context = contexts[0]

        if best_context:
            best_context = best_context.rstrip('.')
            if len(best_context) > 180:
                best_context = best_context[:177] + '...'

            parts.append(f"In the interview, {short_name} is {mention_str}. The discussion touches on: \"{best_context}\"")
        else:
            parts.append(f"In the interview, {short_name} is {mention_str}.")
    else:
        # No transcript sources - describe based on what we know
        if tier == 1:
            parts.append(f"Listed as a top-tier power figure in the interview's hierarchy, though not directly named in the transcript.")
        elif tier == 2:
            parts.append(f"Positioned as a key player in the interview's power network, though not explicitly named in the transcript.")
        elif tier == 3:
            parts.append(f"Referenced as a secondary figure in the interview's framework, though not directly quoted in the transcript.")
        else:
            parts.append(f"Placed in the periphery of the interview's power map, though not explicitly named in the transcript.")

    # Part 3: Tier/context significance
    tier_labels = {1: 'the highest tier of influence', 2: 'the second tier of power',
                   3: 'a secondary tier', 4: 'the peripheral tier'}
    tier_label = tier_labels.get(tier, 'an unspecified tier')

    if category:
        parts.append(f"Classified under {category}, placed in {tier_label} of the interview's power hierarchy.")

    return ' '.join(parts)

def main():
    data = load_data()
    updated = 0
    for p in data:
        summary = generate_summary(p)
        if summary and summary != p.get('storyline_summary'):
            p['storyline_summary'] = summary
            updated += 1

    with open(os.path.join(HERE, "people_data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"[storyline] Generated summaries for {updated} people")

if __name__ == "__main__":
    main()