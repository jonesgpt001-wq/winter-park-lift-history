#!/usr/bin/env python3
"""Winter Park lift-status history tracker.
Fetches the resort's official status feed (same JSON the winterparkresort.com
mountain report page renders), appends an hourly snapshot to data/history.jsonl,
and regenerates site/index.html.
"""
import json, os, sys, urllib.request, datetime, html

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'data'); SITE = os.path.join(BASE, 'site')
HISTORY = os.path.join(DATA, 'history.jsonl')
FEED_URL = 'https://mtnpowder.com/feed/v3.json?bearer_token=_pQB-LhuTtus8AXazk55UBp3Xb1puupqQ4p7grG96UA'
RESORT_NAME = 'Winter Park'   # winter feed, NOT 'Winter Park Summer'
SPOTLIGHT = 'Panoramic Express'
MT = datetime.timezone(datetime.timedelta(hours=-6), 'MT')  # America/Denver (MST; feed carries its own offset)

def classify(status):
    s = (status or '').lower()
    if 'season' in s: return 'season'
    if 'hold' in s: return 'hold'
    if 'sched' in s: return 'scheduled'
    if 'anticip' in s or 'expect' in s: return 'scheduled'
    if s.startswith('open'): return 'open'
    if 'close' in s: return 'closed'
    return 'other'

def fetch_feed():
    req = urllib.request.Request(FEED_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

def num(v):
    try: return float(v)
    except (TypeError, ValueError): return None

def extract(feed, checked_at):
    r = next((x for x in feed['Resorts'] if x['Name'] == RESORT_NAME), None)
    if not r: raise SystemExit('Winter Park (winter) not found in feed')
    lifts = {}
    for area in r.get('MountainAreas') or []:
        for lift in area.get('Lifts') or []:
            name = lift.get('Name')
            if name:
                lifts[name] = {'status': lift.get('Status') or 'Unknown',
                               'area': area.get('Name') or ''}
    sr = r.get('SnowReport') or {}
    am = sr.get('AllMountain') or {}
    return {
        'checked_at': checked_at,
        'feed_updated': feed.get('LastUpdate') or r.get('LastUpdate'),
        'resort_status': r.get('OperatingStatus'),
        'lifts': lifts,
        'snow': {
            'last24_in': num(am.get('Last24HoursIn')),
            'last48_in': num(am.get('Last48HoursIn')),
            'last72_in': num(am.get('Last72HoursIn')),
            'last7d_in': num(am.get('Last7DaysIn')),
            'storm_total_in': num(sr.get('StormTotalIn')),
            'season_total_in': num(sr.get('SeasonTotalIn')),
            'base_in': num(sr.get('SnowBaseRangeIn')),
            'open_lifts': sr.get('TotalOpenLifts'),
            'total_lifts': sr.get('TotalLifts'),
            'open_trails': sr.get('TotalOpenTrails'),
            'total_trails': sr.get('TotalTrails'),
            'open_acres': sr.get('OpenTerrainAcres'),
            'total_acres': sr.get('TotalTerrainAcres'),
        },
    }

def load_history():
    out = []
    if os.path.exists(HISTORY):
        with open(HISTORY) as f:
            for line in f:
                line = line.strip()
                if line:
                    try: out.append(json.loads(line))
                    except json.JSONDecodeError: pass
    return out

def parse_ts(s):
    if not s: return None
    try: return datetime.datetime.fromisoformat(s)
    except ValueError: return None

def fmt_ts(iso):
    dt = parse_ts(iso)
    if not dt: return 'never observed'
    return dt.strftime('%a %b %-d, %-I:%M %p')

BADGE = {'open': ('#1a7f37', 'OPEN'), 'closed': ('#b3382c', 'CLOSED'),
         'hold': ('#b8860b', 'HOLD'), 'scheduled': ('#6e5494', 'SCHEDULED'),
         'season': ('#555c66', 'OFF-SEASON'), 'other': ('#555c66', 'UNKNOWN')}

def badge(status):
    cls = classify(status)
    color, _ = BADGE[cls]
    label = status if status else 'Unknown'
    return f'<span class="badge" style="background:{color}">{html.escape(label.upper())}</span>'

def render(hist, out_path):
    cur = hist[-1]
    # transitions per lift (class-level, keep raw text)
    events = []
    prev = None
    for chk in hist:
        if prev:
            for name, info in chk['lifts'].items():
                p = prev['lifts'].get(name)
                if not p: continue
                if classify(info['status']) != classify(p['status']) or info['status'] != p['status']:
                    events.append({'ts': chk['checked_at'], 'lift': name,
                                   'from': p['status'], 'to': info['status']})
        prev = chk
    events.reverse()
    # per-day open fraction for spotlight (approximate: 1 sample = 1 hour)
    pano_days = {}
    for chk in hist:
        li = chk['lifts'].get(SPOTLIGHT)
        if not li: continue
        day = chk['checked_at'][:10]
        d = pano_days.setdefault(day, {'n': 0, 'open': 0, 'snow24': None})
        d['n'] += 1
        if classify(li['status']) == 'open': d['open'] += 1
        s = chk['snow'].get('last24_in')
        if s is not None: d['snow24'] = s
    pano_day_rows = []
    for day in sorted(pano_days)[-14:]:
        d = pano_days[day]
        hrs = d['open']
        label = 'open all day' if hrs == d['n'] else (f'open ~{hrs}h' if hrs else 'never open')
        snow = f"{d['snow24']:.0f}\"" if d['snow24'] else '0"'
        pano_day_rows.append(f'<tr><td>{day}</td><td>{label}</td><td>{snow} new (24h)</td></tr>')
    # spotlight stats
    pano_cur = cur['lifts'].get(SPOTLIGHT, {'status': 'Unknown', 'area': ''})
    last_open = next((c['checked_at'] for c in reversed(hist)
                      if classify(c['lifts'].get(SPOTLIGHT, {}).get('status')) == 'open'), None)
    # areas table
    areas = {}
    for name, info in cur['lifts'].items():
        areas.setdefault(info['area'], []).append((name, info['status']))
    area_html = ''
    for area in sorted(areas):
        rows = ''.join(f'<tr><td>{html.escape(n)}</td><td>{badge(s)}</td></tr>'
                       for n, s in sorted(areas[area]))
        area_html += f'<h3>{html.escape(area)}</h3><table>{rows}</table>'
    ev_html = ''.join(
        f'<tr><td>{fmt_ts(e["ts"])}</td><td>{html.escape(e["lift"])}</td>'
        f'<td>{html.escape(e["from"])} &rarr; <b>{html.escape(e["to"])}</b></td></tr>'
        for e in events[:40]) or '<tr><td colspan="3">No status changes recorded yet.</td></tr>'
    sn = cur['snow']
    def i(v): return f'{v:.0f}&Prime;' if isinstance(v, float) else '&mdash;'
    open_ct = sum(1 for l in cur['lifts'].values() if classify(l['status']) == 'open')
    page = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Winter Park Lift History</title>
<style>
body{{background:#0d1117;color:#d7dde4;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;padding:24px;max-width:960px;margin:0 auto}}
h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:15px;text-transform:uppercase;letter-spacing:.08em;color:#8b949e;margin:32px 0 10px}}
h3{{font-size:13px;color:#8b949e;margin:16px 0 6px}}
.sub{{color:#8b949e;font-size:13px}}
.card{{background:#161b22;border:1px solid #2d333b;border-radius:8px;padding:16px 20px;margin-top:16px}}
.pano-status{{font-size:28px;font-weight:700;margin:6px 0}}
.badge{{color:#fff;font-size:11px;font-weight:700;padding:2px 8px;border-radius:10px;letter-spacing:.04em}}
table{{border-collapse:collapse;width:100%;font-size:14px;margin-bottom:8px}}
td{{padding:5px 8px;border-bottom:1px solid #21262d}}
td:first-child{{width:55%}}
.snow-grid{{display:flex;flex-wrap:wrap;gap:12px}}
.snow-grid div{{background:#0d1117;border:1px solid #2d333b;border-radius:6px;padding:8px 14px;text-align:center}}
.snow-grid b{{display:block;font-size:20px}}
.note{{color:#8b949e;font-size:12px;margin-top:24px;line-height:1.5}}
</style></head><body>
<h1>Winter Park Lift History</h1>
<div class="sub">Observed hourly from the resort's official status feed. Last check: {fmt_ts(cur['checked_at'])} &middot; Resort: {html.escape(str(cur['resort_status']))} &middot; {open_ct}/{len(cur['lifts'])} lifts open</div>
<div class="card"><h2 style="margin-top:0">Panoramic Express (Parsenn Bowl)</h2>
<div class="pano-status">{badge(pano_cur['status'])}</div>
<div class="sub">Last observed open: {fmt_ts(last_open)}</div></div>
<div class="card"><h2 style="margin-top:0">Snow</h2><div class="snow-grid">
<div><b>{i(sn['last24_in'])}</b><span class="sub">24h</span></div>
<div><b>{i(sn['last48_in'])}</b><span class="sub">48h</span></div>
<div><b>{i(sn['last72_in'])}</b><span class="sub">72h</span></div>
<div><b>{i(sn['last7d_in'])}</b><span class="sub">7 days</span></div>
<div><b>{i(sn['storm_total_in'])}</b><span class="sub">storm total</span></div>
<div><b>{i(sn['season_total_in'])}</b><span class="sub">season</span></div>
<div><b>{i(sn['base_in'])}</b><span class="sub">base</span></div></div></div>
<div class="card"><h2 style="margin-top:0">Pano by day (last 14 days)</h2>
<table><tr><th style="text-align:left">Day</th><th style="text-align:left">Pano</th><th style="text-align:left">Snow</th></tr>{''.join(pano_day_rows) or '<tr><td colspan=3>No history yet.</td></tr>'}</table>
<div class="note">Powder read (inference, not observation): if Pano never opened on a day with new snow, that terrain likely still holds untracked snow. This site records what the resort reported, not conditions on the ground.</div></div>
<h2>Current status, all lifts</h2>{area_html}
<h2>Recent status changes</h2>
<table><tr><th style="text-align:left">When</th><th style="text-align:left">Lift</th><th style="text-align:left">Change</th></tr>{ev_html}</table>
<div class="note">Method: one snapshot per hour from the same feed that powers winterparkresort.com's mountain report. Statuses are the resort's reported values; short openings between checks can be missed. "Open ~Nh" counts hourly samples observed open.</div>
</body></html>"""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        f.write(page)

def main():
    os.makedirs(DATA, exist_ok=True)
    checked_at = datetime.datetime.now(MT).replace(microsecond=0).isoformat()
    snap = extract(fetch_feed(), checked_at)
    with open(HISTORY, 'a') as f:
        f.write(json.dumps(snap) + '\n')
    hist = load_history()
    render(hist, os.path.join(SITE, 'index.html'))
    changed = None
    if len(hist) >= 2:
        prev, last = hist[-2]['lifts'], hist[-1]['lifts']
        diffs = {n: (prev.get(n, {}).get('status'), last[n]['status'])
                 for n in last if prev.get(n, {}).get('status') != last[n]['status']}
        changed = diffs or None
    print(json.dumps({'checked_at': checked_at, 'checks_total': len(hist),
                      'pano': snap['lifts'].get(SPOTLIGHT), 'changes': changed}))

if __name__ == '__main__':
    main()
