#!/usr/bin/env python3
"""Winter Park lift-status history tracker.
Fetches the resort's official status feed (same JSON the winterparkresort.com
mountain report page renders), appends an hourly snapshot to data/history.jsonl,
and regenerates site/index.html.
"""
import json, os, sys, urllib.request, datetime, html

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'data')
# In GitHub Actions the repo root IS the site (Pages serves index.html from root);
# locally the rendered page lives under site/. WP_REPO_MODE=1 renders to BASE.
SITE = BASE if os.environ.get('WP_REPO_MODE') else os.path.join(BASE, 'site')
HISTORY = os.path.join(DATA, 'history.jsonl')
FEED_URL = 'https://mtnpowder.com/feed/v3.json?bearer_token=_pQB-LhuTtus8AXazk55UBp3Xb1puupqQ4p7grG96UA'
RESORT_NAME = 'Winter Park'   # winter feed, NOT 'Winter Park Summer'
SPOTLIGHT = 'Panoramic Express'
MT = datetime.timezone(datetime.timedelta(hours=-6), 'MT')  # America/Denver (MST; feed carries its own offset)

CHART_SCRIPT = """<script>
const CD = __CHART_DATA__;
function svgOpen(w,h){return '<svg viewBox="0 0 '+w+' '+h+'" style="width:100%;height:auto;display:block">';}
function labels(a,b,w,h){const f=function(s){return s.slice(5,10);};
  return '<text x="0" y="'+(h+12)+'" fill="#8b949e" font-size="10">'+f(a)+'</text>'
    +'<text x="'+w+'" y="'+(h+12)+'" fill="#8b949e" font-size="10" text-anchor="end">'+f(b)+'</text>';}
function lineChart(id, pts, key, color, fixedMax){
  const el=document.getElementById(id); const w=600,h=110;
  if(!pts.length){el.innerHTML='<div class="note">No data yet.</div>';return;}
  const vals=pts.map(function(p){return p[key];}).filter(function(v){return v!=null;});
  if(!vals.length){el.innerHTML='<div class="note">No fresh data yet - this fills in when daily snow reporting resumes with the season.</div>';return;}
  const max=fixedMax||Math.max(1,...vals);
  const step=w/Math.max(1,pts.length-1); let d='',started=false;
  pts.forEach(function(p,i){const v=p[key]; if(v==null){started=false;return;}
    const x=i*step, y=h-6-(v/max)*(h-26);
    d+=(started?' L':' M')+x.toFixed(1)+' '+y.toFixed(1); started=true;});
  el.innerHTML=svgOpen(w,h+16)+'<line x1="0" y1="'+(h-6)+'" x2="'+w+'" y2="'+(h-6)+'" stroke="#2d333b"/>'
    +'<path d="'+d+'" fill="none" stroke="'+color+'" stroke-width="1.5"/>'
    +labels(pts[0].t,pts[pts.length-1].t,w,h)
    +'<text x="'+w+'" y="12" fill="#8b949e" font-size="10" text-anchor="end">max '+max+'</text></svg>';}
function barChart(id, rows, key, color, fixedMax, emptyMsg){
  const el=document.getElementById(id); const w=600,h=110;
  if(!rows.length){el.innerHTML='<div class="note">'+emptyMsg+'</div>';return;}
  const max=fixedMax||Math.max(1,...rows.map(function(r){return r[key]||0;}));
  const bw=w/rows.length; let s='';
  rows.forEach(function(r,i){const v=r[key]||0; const bh=(v/max)*(h-26);
    s+='<rect x="'+(i*bw+1).toFixed(1)+'" y="'+(h-6-bh).toFixed(1)+'" width="'+Math.max(1,bw-2).toFixed(1)+'" height="'+bh.toFixed(1)+'" fill="'+color+'"/>';});
  el.innerHTML=svgOpen(w,h+16)+'<line x1="0" y1="'+(h-6)+'" x2="'+w+'" y2="'+(h-6)+'" stroke="#2d333b"/>'+s
    +labels(rows[0].day,rows[rows.length-1].day,w,h)+'</svg>';}
lineChart('chart-open', CD.pts, 'open', '#3fb950', 26);
barChart('chart-pano', CD.pano, 'hours', '#d7a13b', 24, 'No Pano history yet - recording started Sep 9, 2026.');
barChart('chart-snowbars', CD.snow, 'snow24', '#79b8ff', null,
  'No fresh snow reports yet - this fills in when daily snow reporting resumes with the season.');
lineChart('chart-base', CD.pts, 'base', '#79b8ff', null);
</script>"""


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
        'snow_report_updated': sr.get('LastUpdate'),
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
    s = s.strip()
    if len(s) >= 5 and s[-5] in '+-' and s[-4:].isdigit() and s[-3] != ':':
        s = s[:-2] + ':' + s[-2:]
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
    # --- chart series (embedded as JSON, rendered client-side as inline SVG) ---
    pts = []
    for c in hist:
        lifts = c['lifts']
        oc = sum(1 for l in lifts.values() if classify(l['status']) == 'open')
        pano_open = 1 if classify(lifts.get(SPOTLIGHT, {}).get('status')) == 'open' else 0
        sru_c = parse_ts(c.get('snow_report_updated'))
        cdt = parse_ts(c['checked_at'])
        fresh = bool(sru_c and cdt and 0 <= (cdt - sru_c).total_seconds() < 36 * 3600)
        pts.append({'t': c['checked_at'], 'open': oc, 'pano': pano_open,
                    'snow24': c['snow'].get('last24_in') if fresh else None,
                    'base': c['snow'].get('base_in') if fresh else None})
    pano_bars = [{'day': d, 'hours': pano_days[d]['open'], 'samples': pano_days[d]['n']}
                 for d in sorted(pano_days)[-30:]]
    snow_daily = {}
    for p in pts:
        if p['snow24'] is not None:
            snow_daily[p['t'][:10]] = {'day': p['t'][:10], 'snow24': p['snow24'], 'base': p['base']}
    snow_bars = [snow_daily[d] for d in sorted(snow_daily)[-30:]]
    chart_data = json.dumps({'pts': pts, 'pano': pano_bars, 'snow': snow_bars})
    charts_html = ('<div class="card"><h2 style="margin-top:0">Trends</h2>'
        '<h3>Lifts open over time</h3><div id="chart-open"></div>'
        '<h3>Pano - hours open per day</h3><div id="chart-pano"></div>'
        '<h3>New snow (24h, inches)</h3><div id="chart-snowbars"></div>'
        '<h3>Base depth (inches)</h3><div id="chart-base"></div>'
        '<div class="note">Snow trends only plot readings from a fresh daily snow report; '
        'off-season and stalled reports show as gaps, never as carried-forward numbers.</div></div>')
    sn = cur['snow']
    sru = parse_ts(cur.get('snow_report_updated'))
    nowdt = parse_ts(cur['checked_at'])
    snow_stale = True
    snow_age_txt = 'unknown date'
    if sru:
        snow_age_txt = sru.strftime('%b %-d, %Y')
        if nowdt and (nowdt - sru).total_seconds() < 36 * 3600:
            snow_stale = False
    snow_banner = ('<div class="note" style="margin:0 0 10px;color:#d7a13b">Snow report last updated '
        + snow_age_txt + ' - off-season, these are end-of-last-season numbers. Fresh daily snow reporting resumes with the season.</div>') if snow_stale else (
        '<div class="note" style="margin:0 0 10px">Snow report updated ' + snow_age_txt + '</div>')
    snow_dim = ' style="opacity:.45"' if snow_stale else ''
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
<div class="card"><h2 style="margin-top:0">Snow</h2>{snow_banner}<div class="snow-grid"{snow_dim}>
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
{charts_html}
<h2>Current status, all lifts</h2>{area_html}
<h2>Recent status changes</h2>
<table><tr><th style="text-align:left">When</th><th style="text-align:left">Lift</th><th style="text-align:left">Change</th></tr>{ev_html}</table>
<div class="note">Method: one snapshot per hour from the same feed that powers winterparkresort.com's mountain report. Statuses are the resort's reported values; short openings between checks can be missed. "Open ~Nh" counts hourly samples observed open.</div>
__CHART_SCRIPT__
</body></html>"""
    page = page.replace('__CHART_SCRIPT__', CHART_SCRIPT).replace('__CHART_DATA__', chart_data)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        f.write(page)

def main():
    os.makedirs(DATA, exist_ok=True)
    checked_at = datetime.datetime.now(MT).replace(microsecond=0).isoformat()
    snap = extract(fetch_feed(), checked_at)
    off_season = (snap['resort_status'] == 'Closed' and
                  all(classify(l['status']) == 'season' for l in snap['lifts'].values()))
    # Adaptive cadence in Actions: cron fires hourly; off-season we keep one
    # snapshot per day instead of hourly duplicates.
    if os.environ.get('WP_REPO_MODE') and off_season and not os.environ.get('WP_FORCE'):
        hist_prev = load_history()
        last = parse_ts(hist_prev[-1]['checked_at']) if hist_prev else None
        nowdt = parse_ts(checked_at)
        if last and nowdt and (nowdt - last).total_seconds() < 20 * 3600:
            print(json.dumps({'checked_at': checked_at, 'skipped': 'off-season heartbeat fresh',
                              'resort_status': snap['resort_status'], 'off_season': off_season}))
            return
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
                      'resort_status': snap['resort_status'], 'off_season': off_season,
                      'pano': snap['lifts'].get(SPOTLIGHT), 'changes': changed}))

if __name__ == '__main__':
    main()
