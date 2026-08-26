#!/usr/bin/env python3
import json
import os
import re
import urllib.request
import urllib.parse
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DELAY = 2

def fetch_wikitext(title):
    url = f"https://en.wikipedia.org/w/api.php?action=parse&page={urllib.parse.quote(title)}&prop=wikitext&format=json"
    req = urllib.request.Request(url, headers={'User-Agent': 'TheSecretFamilyBot/1.0 (https://github.com/paulvisciano/the-secret-family)'})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
            return data['parse']['wikitext']['*']
    except Exception:
        return ''

def extract_net_worth(wikitext):
    if not wikitext:
        return None

    patterns = [
        r'net\s*worth\s*(?:stood\s*at|was\s*estimated\s*at|is\s*estimated\s*at|estimated\s*at)?\s*(?:US\$|USD|\$)\s*([\d.,]+)\s*(billion|million|trillion)',
        r'(?:US\$|USD|\$)\s*([\d.,]+)\s*(billion|million|trillion)(?:\s*(?:net worth|fortune))',
        r'net\s*worth\s*(?:of\s*)?(?:US\$|USD|\$)\s*([\d.,]+)\s*(billion|million|trillion)',
        r'net\s*worth\s*=\s*(?:US\$|USD|\$)?\s*([\d.,]+)\s*(billion|million|trillion)',
    ]

    for pat in patterns:
        m = re.search(pat, wikitext, re.IGNORECASE)
        if m:
            amount = m.group(1)
            unit = m.group(2).lower()
            return f"${amount} {unit}"

    m = re.search(r'net\s*worth\s*=\s*\{\{net worth\s*\|\s*([^|}]+)\|([^|}]+)', wikitext, re.IGNORECASE)
    if m:
        return f"${m.group(1).strip()} {m.group(2).strip()}"

    m = re.search(r'net\s*worth\s*=\s*(.+?)(?=\||\}\})', wikitext, re.IGNORECASE | re.DOTALL)
    if m:
        val = m.group(1).strip()
        val = re.sub(r'<[^>]+>', '', val)
        val = re.sub(r'\[\[|\]\]', '', val)
        val = re.sub(r'\{\{[^}]*\}\}', '', val)
        val = val.strip()
        if val and re.search(r'\d', val) and len(val) < 80:
            return val

    return None

def main():
    with open(os.path.join(HERE, 'people_data.json'), 'r', encoding='utf-8') as f:
        data = json.load(f)

    nodes = json.load(open(os.path.join(HERE, 'nodes.json')))
    all_nodes = {n['id']: n for n in nodes.get('graph', []) + nodes.get('contextual', [])}

    updated = 0
    for p in data:
        node = all_nodes.get(p['id'], {})
        title = node.get('wikipedia_title') or p.get('wikipedia_title')
        if not title:
            continue

        wikitext = fetch_wikitext(title)
        nw = extract_net_worth(wikitext)
        if nw:
            p['net_worth'] = nw
            updated += 1
            print(f"  {p['id']}: {nw}")
        else:
            if 'net_worth' in p:
                del p['net_worth']

        time.sleep(DELAY)

    with open(os.path.join(HERE, 'people_data.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n[net_worth] Found net worth for {updated} people")

if __name__ == '__main__':
    main()