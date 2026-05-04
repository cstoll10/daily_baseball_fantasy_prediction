#!/usr/bin/env python3
"""BallparkPal Fantasy Optimizer - Daily Build Script with Multi-Day Support"""

import pandas as pd
import json, os, sys, glob
from datetime import datetime, date, timedelta

DATA_DIR    = os.path.join(os.path.dirname(__file__), '..', 'data')
ROSTER_FILE = os.path.join(os.path.dirname(__file__), '..', 'roster.json')
TAKEN_FILE  = os.path.join(os.path.dirname(__file__), '..', 'taken.json')
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), '..', 'index.html')

def load_excel(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path): return None
    return pd.read_excel(path)

def load_multi_day(prefix):
    """
    Load BallparkPal data from:
      1. Dated subfolders:  data/2026-05-01/BallparkPal_{prefix}.xlsx
      2. Base file (today): data/BallparkPal_{prefix}.xlsx
    All files are combined and deduplicated by GameDate + PlayerId.
    """
    frames = []
    seen_dates = set()

    # Scan dated subfolders first (e.g. data/2026-05-01/)
    folder_pattern = os.path.join(DATA_DIR, '????-??-??')
    dated_folders = sorted(glob.glob(folder_pattern))
    for folder in dated_folders:
        path = os.path.join(folder, f'BallparkPal_{prefix}.xlsx')
        if os.path.exists(path):
            df = pd.read_excel(path)
            # Tag with folder date if GameDate column is missing
            folder_date = os.path.basename(folder)
            if 'GameDate' not in df.columns:
                df['GameDate'] = folder_date
            frames.append(df)
            seen_dates.add(folder_date)

    # Also load the base file in data/ root (today's download)
    base = os.path.join(DATA_DIR, f'BallparkPal_{prefix}.xlsx')
    if os.path.exists(base):
        df = pd.read_excel(base)
        frames.append(df)

    if not frames:
        print(f"  WARNING: No files found for {prefix}")
        return None

    combined = pd.concat(frames, ignore_index=True)
    # Deduplicate by GameDate + PlayerId
    id_col = 'PlayerId' if 'PlayerId' in combined.columns else combined.columns[0]
    combined = combined.drop_duplicates(subset=['GameDate', id_col])
    n_days = combined['GameDate'].nunique()
    n_folders = len(dated_folders)
    print(f"  {prefix}: {len(frames)} file(s) across {n_days} day(s) [{n_folders} subfolder(s) + root]")
    return combined

def process_batters_day(df, date_str):
    df = df[df['GameDate'] == date_str].copy()
    if df.empty: return []
    df['Team'] = df['Team'].str.strip(); df['Opponent'] = df['Opponent'].str.strip()
    df['OBP'] = ((df['Hits'] + df['Walks']) / df['PlateAppearances']).round(3)
    df['SB'] = df['StolenBaseSuccesses']; df['TB'] = df['Bases']
    cols = ['PlayerId','FullName','Team','Opponent','Side','BattingPosition',
            'PlateAppearances','Hits','Runs','HomeRuns','TB','SB','OBP',
            'Strikeouts','Walks','PointsDK','PointsFD','HitProbability','HomeRunProbability','StolenBaseProbability']
    return df[cols].round(3).to_dict('records')

def process_pitchers_day(df, date_str):
    df = df[df['GameDate'] == date_str].copy()
    if df.empty: return []
    df['Team'] = df['Team'].str.strip(); df['Opponent'] = df['Opponent'].str.strip()
    df['ERA_proj']  = (df['RunsAllowed'] / df['Innings'] * 9).round(3)
    df['WHIP_proj'] = ((df['HitsAllowed'] + df['Walks']) / df['Innings']).round(3)
    cols = ['PlayerId','FullName','Team','Opponent','PitcherHand','Side',
            'Innings','WinPct','QualityStart','Strikeouts',
            'ERA_proj','WHIP_proj','RunsAllowed','HitsAllowed','Walks','PointsDK','PointsFD']
    return df[cols].round(3).to_dict('records')

def process_teams_day(df, date_str):
    df = df[df['GameDate'] == date_str].copy()
    if df.empty: return {}
    df['Team'] = df['Team'].str.strip(); df['Opponent'] = df['Opponent'].str.strip()
    ratings = {}
    for _, row in df.iterrows():
        opp = row['Opponent']
        if opp not in ratings:
            ratings[opp] = {'runs': [], 'hr': [], 'k': []}
        ratings[opp]['runs'].append(row['Runs'])
        ratings[opp]['hr'].append(row['HomeRuns'])
        ratings[opp]['k'].append(row['Strikeouts'])
    return {team: {
        'runs': round(sum(v['runs'])/len(v['runs']), 3),
        'hr':   round(sum(v['hr'])/len(v['hr']), 3),
        'k':    round(sum(v['k'])/len(v['k']), 3)
    } for team, v in ratings.items()}

def process_games_day(df, date_str):
    df = df[df['GameDate'] == date_str].copy()
    if df.empty: return []
    games = []
    for _, row in df.iterrows():
        games.append({
            'away': row['AwayTeam'].strip(), 'home': row['HomeTeam'].strip(),
            'runsAway': round(row['RunsAway'], 2), 'runsHome': round(row['RunsHome'], 2),
            'totalRuns': round(row['RunsAway'] + row['RunsHome'], 2),
            'awayWin': round(row['AwayWinPct'], 3), 'homeWin': round(row['HomeWinPct'], 3),
        })
    return games

def build_weekly_pitcher_data(df_pitchers, roster):
    """For each rostered SP/RP, find all their starts across available dates."""
    if df_pitchers is None: return {}
    df = df_pitchers.copy()
    df['Team'] = df['Team'].str.strip()
    df['ERA_proj']  = (df['RunsAllowed'] / df['Innings'] * 9).round(3)
    df['WHIP_proj'] = ((df['HitsAllowed'] + df['Walks']) / df['Innings']).round(3)

    my_pitchers = [p for p in roster.get('players', []) if p.get('pos') in ['SP','RP']]
    result = {}

    def nm(s): return s.lower().replace(' ','').replace('.','').replace("'",'')

    for rp in my_pitchers:
        matches = df[df['FullName'].apply(lambda x: nm(rp['name']) in nm(x) or nm(x) in nm(rp['name']))]
        if matches.empty: continue
        starts = []
        for _, row in matches.iterrows():
            starts.append({
                'date': str(row['GameDate']),
                'opp': row['Opponent'],
                'hand': row.get('PitcherHand','?'),
                'ip': round(row['Innings'], 1),
                'k': round(row['Strikeouts'], 1),
                'qs': round(row['QualityStart'], 3),
                'win': round(row['WinPct'], 3),
                'era': round(row['ERA_proj'], 2),
                'whip': round(row['WHIP_proj'], 3),
            })
        starts.sort(key=lambda x: x['date'])
        total_ip = round(sum(s['ip'] for s in starts), 1)
        result[rp['name']] = {
            'pos': rp['pos'],
            'team': rp.get('team',''),
            'starts': starts,
            'total_ip': total_ip,
            'total_k': round(sum(s['k'] for s in starts), 1),
            'avg_era': round(sum(s['era'] for s in starts)/len(starts), 2) if starts else 0,
            'avg_whip': round(sum(s['whip'] for s in starts)/len(starts), 3) if starts else 0,
        }
    return result

def build_weekly_batter_data(df_batters):
    """Aggregate batter projections across all available dates."""
    if df_batters is None: return []
    df = df_batters.copy()
    df['Team'] = df['Team'].str.strip()
    df['OBP'] = ((df['Hits'] + df['Walks']) / df['PlateAppearances']).round(3)
    df['SB'] = df['StolenBaseSuccesses']; df['TB'] = df['Bases']

    agg = df.groupby(['PlayerId','FullName','Team']).agg(
        games=('GameDate','nunique'),
        Hits=('Hits','sum'), Runs=('Runs','sum'), HomeRuns=('HomeRuns','sum'),
        TB=('TB','sum'), SB=('SB','sum'), OBP=('OBP','mean'),
        PlateAppearances=('PlateAppearances','sum'),
        HitProbability=('HitProbability','mean'),
        HomeRunProbability=('HomeRunProbability','mean'),
    ).reset_index().round(3)

    return agg.sort_values('Hits', ascending=False).to_dict('records')

def build_streaming_by_day(df_pitchers):
    """For each available date, list the best free-agent streaming SPs."""
    if df_pitchers is None: return {}
    df = df_pitchers.copy()
    df['Team'] = df['Team'].str.strip()
    df['ERA_proj']  = (df['RunsAllowed'] / df['Innings'] * 9).round(3)
    df['WHIP_proj'] = ((df['HitsAllowed'] + df['Walks']) / df['Innings']).round(3)
    result = {}
    for date_str in sorted(df['GameDate'].unique()):
        day = df[df['GameDate'] == date_str]
        starters = day[day['QualityStart'] >= 0.20].sort_values('QualityStart', ascending=False)
        result[str(date_str)] = [{
            'name': row['FullName'], 'team': row['Team'].strip(),
            'opp': row['Opponent'].strip(), 'hand': row.get('PitcherHand','?'),
            'ip': round(row['Innings'],1), 'k': round(row['Strikeouts'],1),
            'qs': round(row['QualityStart'],3), 'win': round(row['WinPct'],3),
            'era': round(row['ERA_proj'],2), 'whip': round(row['WHIP_proj'],3),
        } for _, row in starters.iterrows()]
    return result

def load_roster():
    if not os.path.exists(ROSTER_FILE): return {"team_name":"My Team","players":[]}
    with open(ROSTER_FILE) as f: return json.load(f)

def load_taken():
    if not os.path.exists(TAKEN_FILE): return {"taken":[]}
    with open(TAKEN_FILE) as f: return json.load(f)

def build_html(batters_json, pitchers_json, teams_json, games_json,
               weekly_pitchers, weekly_batters, streaming_by_day,
               roster, taken, build_date, available_dates):

    b   = json.dumps(batters_json)
    p   = json.dumps(pitchers_json)
    tm  = json.dumps(teams_json)
    gm  = json.dumps(games_json)
    wp  = json.dumps(weekly_pitchers)
    wb  = json.dumps(weekly_batters)
    sd  = json.dumps(streaming_by_day)
    r   = json.dumps(roster)
    t   = json.dumps(taken.get('taken', []))
    nb  = len(batters_json); np_ = len(pitchers_json)
    nd  = len(available_dates)
    dates_js = json.dumps(available_dates)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BallparkPal Fantasy Optimizer</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap');
  :root{{--bg:#0a0e17;--surface:#111827;--surface2:#1a2234;--border:#1e2d47;--accent:#00d4ff;--accent2:#ff6b35;--accent3:#39d353;--text:#e2e8f0;--text2:#94a3b8;--red:#f87171;--gold:#fbbf24;}}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:var(--bg);color:var(--text);font-family:'DM Sans',sans-serif;min-height:100vh}}
  .header{{background:linear-gradient(135deg,#0a0e17,#0d1829,#091420);border-bottom:1px solid var(--border);padding:14px 24px;display:flex;align-items:center;gap:16px;justify-content:space-between}}
  .header h1{{font-family:'Bebas Neue',sans-serif;font-size:1.8rem;letter-spacing:2px;color:var(--accent)}}
  .header .sub{{color:var(--text2);font-size:0.72rem;letter-spacing:1px;text-transform:uppercase;margin-top:2px}}
  .badge{{background:var(--accent2);color:#fff;padding:2px 8px;border-radius:4px;font-size:0.65rem;font-weight:600;text-transform:uppercase;letter-spacing:1px}}
  .badge-date{{background:var(--surface2);color:var(--text2);border:1px solid var(--border);padding:2px 10px;border-radius:4px;font-size:0.65rem;font-family:'DM Mono',monospace}}
  .layout{{display:grid;grid-template-columns:310px 1fr;height:calc(100vh - 62px)}}
  .sidebar{{background:var(--surface);border-right:1px solid var(--border);overflow-y:auto;display:flex;flex-direction:column}}
  .ss{{padding:14px;border-bottom:1px solid var(--border)}}
  .ss h3{{font-family:'Bebas Neue',sans-serif;font-size:0.95rem;letter-spacing:2px;color:var(--accent);margin-bottom:10px}}
  .rs{{display:flex;align-items:center;gap:6px;padding:5px 7px;border-radius:5px;background:var(--surface2);margin-bottom:3px;border:1px solid transparent;transition:all .15s}}
  .rs.active{{border-color:var(--accent);background:rgba(0,212,255,.08)}}.rs.benched{{opacity:.55}}
  .sp-badge{{font-family:'DM Mono',monospace;font-size:0.6rem;color:var(--accent2);background:rgba(255,107,53,.15);padding:2px 4px;border-radius:3px;min-width:26px;text-align:center}}
  .il-badge{{font-family:'DM Mono',monospace;font-size:0.6rem;color:var(--red);background:rgba(248,113,113,.15);padding:2px 4px;border-radius:3px}}
  .cat-grid{{display:grid;grid-template-columns:1fr 1fr;gap:6px}}
  .ci{{display:flex;flex-direction:column;gap:2px}}
  .cl{{font-size:0.68rem;color:var(--text2);font-family:'DM Mono',monospace;display:flex;justify-content:space-between}}
  .cv{{color:var(--accent)}}
  input[type=range]{{width:100%;height:3px;background:var(--border);-webkit-appearance:none;border-radius:2px;cursor:pointer}}
  input[type=range]::-webkit-slider-thumb{{-webkit-appearance:none;width:11px;height:11px;background:var(--accent);border-radius:50%}}
  .main{{display:flex;flex-direction:column;overflow:hidden}}
  .tabs{{display:flex;border-bottom:1px solid var(--border);background:var(--surface);padding:0 12px;z-index:10;overflow-x:auto;flex-shrink:0}}
  .tab{{padding:10px 12px;font-size:0.7rem;font-weight:600;text-transform:uppercase;letter-spacing:.8px;cursor:pointer;color:var(--text2);border-bottom:2px solid transparent;transition:all .15s;white-space:nowrap}}
  .tab.active{{color:var(--accent);border-bottom-color:var(--accent)}}.tab:hover{{color:var(--text)}}
  .tc{{padding:18px;flex:1;overflow-y:auto}}.tp{{display:none}}.tp.active{{display:block}}
  .ctrls{{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;align-items:center}}
  .sb{{background:var(--surface);border:1px solid var(--border);color:var(--text);padding:7px 11px;border-radius:5px;font-size:0.82rem;font-family:'DM Sans',sans-serif;flex:1;min-width:160px}}
  .sb:focus{{outline:none;border-color:var(--accent)}}
  select{{background:var(--surface);border:1px solid var(--border);color:var(--text);padding:7px 11px;border-radius:5px;font-size:0.78rem;font-family:'DM Sans',sans-serif;cursor:pointer}}
  select:focus{{outline:none;border-color:var(--accent)}}
  .btn{{padding:7px 14px;border-radius:5px;border:none;cursor:pointer;font-size:0.78rem;font-weight:600;letter-spacing:.4px;transition:all .15s}}
  .btn-p{{background:var(--accent);color:#000}}.btn-p:hover{{background:#33ddff}}
  .btn-s{{background:var(--accent3);color:#000}}.btn-s:hover{{opacity:.85}}
  .btn-sm{{background:var(--surface2);color:var(--accent);font-size:0.67rem;padding:3px 7px;border:1px solid var(--border)}}
  .pt{{width:100%;border-collapse:collapse;font-size:0.78rem}}
  .pt th{{text-align:left;padding:7px 9px;color:var(--text2);font-size:0.67rem;letter-spacing:1px;text-transform:uppercase;border-bottom:1px solid var(--border);white-space:nowrap;cursor:pointer;background:var(--surface);position:sticky;top:0}}
  .pt th:hover{{color:var(--accent)}}
  .pt td{{padding:6px 9px;border-bottom:1px solid rgba(30,45,71,.4);vertical-align:middle}}
  .pt tr:hover td{{background:rgba(0,212,255,.03)}}
  .pt tr.my-start td{{background:rgba(57,211,83,.06)}}.pt tr.my-bench td{{background:rgba(255,107,53,.04)}}.pt tr.taken td{{opacity:.3}}
  .tb{{font-family:'DM Mono',monospace;font-size:0.62rem;background:var(--surface2);color:var(--text2);padding:1px 4px;border-radius:3px}}
  .pb{{font-family:'DM Mono',monospace;font-size:0.62rem;background:rgba(255,107,53,.15);color:var(--accent2);padding:1px 4px;border-radius:3px}}
  .hb{{font-family:'DM Mono',monospace;font-size:0.62rem;background:rgba(0,212,255,.1);color:var(--accent);padding:1px 4px;border-radius:3px}}
  .sv{{font-family:'DM Mono',monospace;font-size:0.76rem}}
  .good{{color:var(--accent3)}}.avg{{color:var(--gold)}}.bad{{color:var(--red)}}
  .sc{{font-family:'Bebas Neue',sans-serif;font-size:1.05rem;color:var(--accent)}}
  .ts{{background:rgba(57,211,83,.15);color:var(--accent3);padding:1px 5px;border-radius:3px;font-size:0.62rem;font-weight:600}}
  .tw{{background:rgba(251,191,36,.15);color:var(--gold);padding:1px 5px;border-radius:3px;font-size:0.62rem;font-weight:600}}
  .tsi{{background:rgba(248,113,113,.15);color:var(--red);padding:1px 5px;border-radius:3px;font-size:0.62rem;font-weight:600}}
  .ta{{background:rgba(0,212,255,.1);color:var(--accent);padding:1px 5px;border-radius:3px;font-size:0.62rem;font-weight:600}}
  .ttk{{background:rgba(148,163,184,.1);color:var(--text2);padding:1px 5px;border-radius:3px;font-size:0.62rem;font-weight:600}}
  .mup-easy{{background:rgba(57,211,83,.15);color:var(--accent3);padding:1px 5px;border-radius:3px;font-size:0.62rem;font-weight:600}}
  .mup-avg{{background:rgba(251,191,36,.15);color:var(--gold);padding:1px 5px;border-radius:3px;font-size:0.62rem;font-weight:600}}
  .mup-tough{{background:rgba(248,113,113,.15);color:var(--red);padding:1px 5px;border-radius:3px;font-size:0.62rem;font-weight:600}}
  .sg{{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px;margin-bottom:18px}}
  .sc2{{background:var(--surface);border:1px solid var(--border);border-radius:7px;padding:11px;text-align:center}}
  .sc2 .cat{{font-family:'Bebas Neue',sans-serif;font-size:0.95rem;color:var(--accent);letter-spacing:1px}}
  .sc2 .val{{font-family:'DM Mono',monospace;font-size:1.2rem;font-weight:500;margin:3px 0}}
  .sc2 .dsc{{font-size:0.62rem;color:var(--text2)}}
  .rs2{{margin-bottom:20px}}
  .rs2 h3{{font-family:'Bebas Neue',sans-serif;font-size:1.1rem;letter-spacing:2px;color:var(--accent2);margin-bottom:10px}}
  .rc{{background:var(--surface);border:1px solid var(--border);border-radius:7px;padding:12px 14px;margin-bottom:7px;display:flex;align-items:center;gap:10px;border-left:3px solid var(--accent)}}
  .rc.wav{{border-left-color:var(--gold)}}.rc.sit{{border-left-color:var(--red)}}.rc.str{{border-left-color:var(--accent3)}}.rc.warn{{border-left-color:var(--gold)}}
  .rm{{flex:1}}.rn{{font-weight:600;font-size:0.85rem}}.rd{{font-size:0.72rem;color:var(--text2);margin-top:3px}}
  .rsc{{font-family:'Bebas Neue',sans-serif;font-size:1.3rem;color:var(--accent)}}
  .es{{text-align:center;padding:40px;color:var(--text2)}}.es .ic{{font-size:2rem;margin-bottom:8px}}
  .mt-cat{{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:8px 10px;display:flex;align-items:center;justify-content:space-between;margin-bottom:4px}}
  .mt-cat.winning{{border-color:var(--accent3);background:rgba(57,211,83,.05)}}
  .mt-cat.losing{{border-color:var(--red);background:rgba(248,113,113,.05)}}
  .filter-row{{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:10px;padding:10px;background:var(--surface);border:1px solid var(--border);border-radius:6px}}
  .filter-row label{{font-size:0.75rem;display:flex;align-items:center;gap:5px;cursor:pointer;color:var(--text2)}}
  .fl-sep{{width:1px;height:16px;background:var(--border)}}
  .h2h-grid{{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:16px}}
  .h2h-cat{{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:10px}}
  .h2h-cat.winning{{border-color:var(--accent3);background:rgba(57,211,83,.05)}}
  .h2h-cat.losing{{border-color:var(--red);background:rgba(248,113,113,.05)}}
  .h2h-cat.close{{border-color:var(--gold);background:rgba(251,191,36,.03)}}
  .h2h-label{{font-family:'DM Mono',monospace;font-size:0.75rem;font-weight:600;margin-bottom:6px}}
  .h2h-inputs{{display:flex;gap:6px;align-items:center}}
  .h2h-input{{background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:4px 7px;border-radius:4px;font-size:0.8rem;font-family:'DM Mono',monospace;width:65px;text-align:center}}
  .h2h-input:focus{{outline:none;border-color:var(--accent)}}
  .h2h-vs{{color:var(--text2);font-size:0.7rem}}
  .h2h-result{{font-size:0.65rem;font-weight:600;margin-top:4px}}
  /* Weekly planner */
  .day-tabs{{display:flex;gap:4px;margin-bottom:14px;flex-wrap:wrap}}
  .day-tab{{padding:5px 12px;border-radius:5px;border:1px solid var(--border);cursor:pointer;font-size:0.72rem;font-family:'DM Mono',monospace;color:var(--text2);background:var(--surface);transition:all .15s}}
  .day-tab.active{{background:var(--accent);color:#000;border-color:var(--accent);font-weight:600}}
  .day-tab:hover{{border-color:var(--accent);color:var(--text)}}
  .pitcher-week-card{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:14px;margin-bottom:10px}}
  .pitcher-week-card.danger{{border-color:var(--red);}}
  .pitcher-week-card.good{{border-color:var(--accent3);}}
  .start-dot{{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--accent3);margin:0 2px;cursor:pointer;position:relative}}
  .start-dot.no-start{{background:var(--border)}}
  .start-dot.tough{{background:var(--red)}}
  .start-dot.easy{{background:var(--accent3)}}
  .start-dot.avg{{background:var(--gold)}}
  .ip-bar{{height:6px;border-radius:3px;background:var(--accent);margin-top:4px}}
  .ip-bar.over{{background:var(--red)}}
  ::-webkit-scrollbar{{width:4px;height:4px}}
  ::-webkit-scrollbar-track{{background:var(--bg)}}
  ::-webkit-scrollbar-thumb{{background:var(--border);border-radius:2px}}
</style>
</head>
<body>
<div class="header">
  <div><h1>⚾ BallparkPal Fantasy Optimizer</h1>
  <div class="sub">ESPN H2H | {nb} Batters | {np_} Pitchers | {nd} Day(s) loaded</div></div>
  <div style="display:flex;gap:8px;align-items:center">
    <span class="badge-date">📅 {build_date}</span>
    <span class="badge">Live Projections</span>
  </div>
</div>
<div class="layout">
  <div class="sidebar">
    <div class="ss">
      <h3>My Roster</h3>
      <div style="font-size:.7rem;color:var(--text2);margin-bottom:8px">Edit <code style="color:var(--accent);font-size:.65rem">roster.json</code> to update</div>
      <div id="rl"></div>
    </div>
    <div class="ss">
      <h3>Matchup Status</h3>
      <div style="font-size:.7rem;color:var(--text2);margin-bottom:8px">W = winning &nbsp;~ = close &nbsp;L = losing</div>
      <div id="mt"></div>
    </div>
    <div class="ss">
      <h3>Category Priority</h3>
      <div style="font-size:.7rem;color:var(--text2);margin-bottom:8px">Higher = optimizer values this more</div>
      <div class="cat-grid" id="cs"></div>
    </div>
    <div class="ss">
      <h3>Today's Games</h3>
      <div id="gl" style="font-size:.73rem"></div>
    </div>
  </div>
  <div class="main">
    <div class="tabs">
      <div class="tab active" onclick="sw('opt',this)">⚡ Optimizer</div>
      <div class="tab" onclick="sw('bat',this)">🏏 Batters</div>
      <div class="tab" onclick="sw('pit',this)">⚾ Pitchers</div>
      <div class="tab" onclick="sw('wv',this)">📋 Waiver Wire</div>
      <div class="tab" onclick="sw('weekly',this)">📅 Weekly Planner</div>
      <div class="tab" onclick="sw('stream',this)">🎯 SP Streamer</div>
      <div class="tab" onclick="sw('h2h',this)">⚔️ H2H Tracker</div>
      <div class="tab" onclick="sw('mgmt',this)">🔧 Roster Mgmt</div>
    </div>
    <div class="tc">

      <div id="tp-opt" class="tp active">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
          <div><h2 style="font-family:'Bebas Neue',sans-serif;font-size:1.3rem;letter-spacing:2px">Daily Recommendations</h2>
          <div style="font-size:.72rem;color:var(--text2)">Start/sit + waiver adds + IL alerts, weighted by matchup status</div></div>
          <button class="btn btn-s" onclick="runOpt()">⚡ Run Optimizer</button>
        </div>
        <div id="oo"><div class="es"><div class="ic">⚡</div>
          <div>Click <strong>Run Optimizer</strong> to generate today's recommendations</div>
          <div style="margin-top:7px;font-size:.73rem">Set matchup status in sidebar for targeted advice</div>
        </div></div>
      </div>

      <div id="tp-bat" class="tp">
        <div class="filter-row">
          <label><input type="checkbox" id="f-top6" onchange="rB()"> Top order (1-6)</label>
          <label><input type="checkbox" id="f-home" onchange="rB()"> Home only</label>
          <label><input type="checkbox" id="f-avail" onchange="rB()"> Available only</label>
          <label><input type="checkbox" id="f-hidetaken" onchange="rB()" checked> Hide taken</label>
          <div class="fl-sep"></div>
          <label>Min PA:<input type="number" id="f-minpa" value="3.5" step="0.1" min="0" max="5" style="width:48px;background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:2px 5px;border-radius:3px;font-size:.75rem;margin-left:4px" onchange="rB()"></label>
          <label>vs:<select id="f-hand" onchange="rB()" style="padding:3px 6px;font-size:.72rem;margin-left:4px"><option value="">Any</option><option value="R">RHP</option><option value="L">LHP</option></select></label>
        </div>
        <div class="ctrls">
          <input type="text" class="sb" placeholder="Search player or team..." id="bs" oninput="rB()">
          <select id="bso" onchange="rB()"><option value="score">Fantasy Score</option><option value="Hits">H</option><option value="Runs">R</option><option value="HomeRuns">HR</option><option value="TB">TB</option><option value="SB">SB</option><option value="OBP">OBP</option></select>
          <select id="btf" onchange="rB()"><option value="">All Teams</option></select>
        </div>
        <div style="overflow-x:auto"><table class="pt"><thead><tr>
          <th>Score</th><th>Player</th><th>Status</th><th>Team</th><th>Opp</th><th>Matchup</th><th>Pos</th>
          <th>H</th><th>R</th><th>HR</th><th>TB</th><th>SB</th><th>OBP</th><th>PA</th>
        </tr></thead><tbody id="btb"></tbody></table></div>
      </div>

      <div id="tp-pit" class="tp">
        <div class="filter-row">
          <label><input type="checkbox" id="f-qs" onchange="rP()"> QS likely (&gt;40%)</label>
          <label><input type="checkbox" id="f-avail-p" onchange="rP()"> Available only</label>
          <label><input type="checkbox" id="f-hidetaken-p" onchange="rP()" checked> Hide taken</label>
          <div class="fl-sep"></div>
          <label>Min IP:<input type="number" id="f-minip" value="4" step="0.5" min="0" max="9" style="width:44px;background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:2px 5px;border-radius:3px;font-size:.75rem;margin-left:4px" onchange="rP()"></label>
          <label>Max ERA:<input type="number" id="f-maxera" value="6" step="0.5" min="0" max="10" style="width:44px;background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:2px 5px;border-radius:3px;font-size:.75rem;margin-left:4px" onchange="rP()"></label>
          <label>Min W%:<input type="number" id="f-minw" value="0" step="5" min="0" max="60" style="width:44px;background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:2px 5px;border-radius:3px;font-size:.75rem;margin-left:4px" onchange="rP()">%</label>
        </div>
        <div class="ctrls">
          <input type="text" class="sb" placeholder="Search pitcher or team..." id="ps" oninput="rP()">
          <select id="pso" onchange="rP()"><option value="score">Fantasy Score</option><option value="Strikeouts">K</option><option value="QualityStart">QS%</option><option value="WinPct">Win%</option><option value="ERA_proj">ERA</option><option value="WHIP_proj">WHIP</option></select>
        </div>
        <div style="overflow-x:auto"><table class="pt"><thead><tr>
          <th>Score</th><th>Pitcher</th><th>Status</th><th>Team</th><th>Opp</th><th>Matchup</th><th>H</th>
          <th>IP</th><th>K</th><th>W%</th><th>QS%</th><th>ERA</th><th>WHIP</th>
        </tr></thead><tbody id="ptb"></tbody></table></div>
      </div>

      <div id="tp-wv" class="tp">
        <div style="margin-bottom:14px"><h2 style="font-family:'Bebas Neue',sans-serif;font-size:1.3rem;letter-spacing:2px">Waiver Wire Targets</h2>
        <div style="font-size:.72rem;color:var(--text2)">Truly free agents — not on your roster or any opponent's</div></div>
        <div class="ctrls">
          <select id="wc" onchange="rW()"><option value="score">Best Overall</option><option value="HR">HR Upside</option><option value="SB">SB Upside</option><option value="Hits">Hit Volume</option><option value="Runs">Run Producers</option><option value="OBP">High OBP</option><option value="TB">Total Bases</option><option value="K_pit">Strikeout Arms</option><option value="QS">QS Candidates</option><option value="ERA">Low ERA</option><option value="WHIP">Low WHIP</option></select>
          <select id="whand" onchange="rW()"><option value="">Any Hand</option><option value="R">RHP only</option><option value="L">LHP only</option></select>
        </div>
        <div id="wo"></div>
      </div>

      <!-- WEEKLY PLANNER -->
      <div id="tp-weekly" class="tp">
        <div style="margin-bottom:14px">
          <h2 style="font-family:'Bebas Neue',sans-serif;font-size:1.3rem;letter-spacing:2px">Weekly Planner</h2>
          <div style="font-size:.72rem;color:var(--text2)">{nd} day(s) of projections loaded</div>
        </div>
        <div class="tabs" style="background:transparent;border:none;padding:0;margin-bottom:16px;position:relative">
          <div class="tab active" onclick="swWeekly('pitchers',this)" style="font-size:.72rem">⚾ Pitcher Starts</div>
          <div class="tab" onclick="swWeekly('batters',this)" style="font-size:.72rem">🏏 Batter Stacks</div>
        </div>
        <div id="weekly-pitchers">
          <div style="font-size:.8rem;color:var(--text2);margin-bottom:12px">
            Track your pitchers' starts this week. ESPN standard week = 12 IP max for most leagues.
            <span style="margin-left:8px;font-size:.7rem"><span style="color:var(--accent3)">●</span> Easy &nbsp;<span style="color:var(--gold)">●</span> Avg &nbsp;<span style="color:var(--red)">●</span> Tough</span>
          </div>
          <div id="wp-cards"></div>
        </div>
        <div id="weekly-batters" style="display:none">
          <div style="font-size:.8rem;color:var(--text2);margin-bottom:12px">Best batters ranked by total projected stats across all {nd} available days</div>
          <div class="ctrls">
            <select id="wb-sort" onchange="renderWeeklyBatters()"><option value="Hits">Sort: Total H</option><option value="HomeRuns">Sort: Total HR</option><option value="Runs">Sort: Total R</option><option value="TB">Sort: Total TB</option><option value="SB">Sort: Total SB</option><option value="OBP">Sort: Avg OBP</option></select>
            <label style="font-size:.78rem;display:flex;align-items:center;gap:5px"><input type="checkbox" id="wb-free" onchange="renderWeeklyBatters()"> Free agents only</label>
            <label style="font-size:.78rem;display:flex;align-items:center;gap:5px"><input type="checkbox" id="wb-mine" onchange="renderWeeklyBatters()"> My roster only</label>
          </div>
          <div style="overflow-x:auto"><table class="pt"><thead><tr>
            <th>Player</th><th>Status</th><th>Team</th><th>Games</th>
            <th>H</th><th>R</th><th>HR</th><th>TB</th><th>SB</th><th>OBP</th>
          </tr></thead><tbody id="wb-table"></tbody></table></div>
        </div>
      </div>

      <!-- SP STREAMER -->
      <div id="tp-stream" class="tp">
        <div style="margin-bottom:14px">
          <h2 style="font-family:'Bebas Neue',sans-serif;font-size:1.3rem;letter-spacing:2px">SP Streaming Targets</h2>
          <div style="font-size:.72rem;color:var(--text2)">Free agent starters by day — ranked by stuff + matchup</div>
        </div>
        <div class="day-tabs" id="stream-day-tabs"></div>
        <div id="stream-out"></div>
      </div>

      <!-- H2H TRACKER -->
      <div id="tp-h2h" class="tp">
        <div style="margin-bottom:14px">
          <h2 style="font-family:'Bebas Neue',sans-serif;font-size:1.3rem;letter-spacing:2px">Head-to-Head Category Tracker</h2>
          <div style="font-size:.72rem;color:var(--text2)">Enter your current stats vs opponent — optimizer auto-adjusts to swing categories</div>
        </div>
        <div style="display:flex;gap:10px;margin-bottom:14px;align-items:center;flex-wrap:wrap">
          <button class="btn btn-s" onclick="calcH2H()">⚡ Analyze Matchup</button>
          <button class="btn btn-sm" onclick="resetH2H()">Reset</button>
        </div>
        <div class="h2h-grid" id="h2h-inputs"></div>
        <div id="h2h-out"></div>
      </div>

      <!-- ROSTER MGMT -->
      <div id="tp-mgmt" class="tp">
        <div style="margin-bottom:14px">
          <h2 style="font-family:'Bebas Neue',sans-serif;font-size:1.3rem;letter-spacing:2px">Roster Management</h2>
          <div style="font-size:.72rem;color:var(--text2)">Add/drop suggestions + IL monitor</div>
        </div>
        <button class="btn btn-s" style="margin-bottom:16px" onclick="runMgmt()">🔧 Analyze My Roster</button>
        <div id="mgmt-out"><div class="es"><div class="ic">🔧</div><div>Click Analyze to get add/drop suggestions</div></div></div>
      </div>

    </div>
  </div>
</div>

<script>
const AB = {b};
const AP = {p};
const TM = {tm};
const GM = {gm};
const WP = {wp};
const WB = {wb};
const SD = {sd};
const ROSTER_DATA = {r};
const TAKEN_LIST  = {t};
const AVAILABLE_DATES = {dates_js};
const BUILD_DATE  = "{build_date}";

let MR = ROSTER_DATA.players.map((p,i)=>({{...p,id:i}}));
let CW = {{H:5,R:5,HR:7,TB:5,SB:6,OBP:4,K:6,QS:7,W:6,ERA:5,WHIP:5}};
let MS = {{H:'close',R:'close',HR:'close',TB:'close',SB:'close',OBP:'close',K:'close',QS:'close',W:'close',ERA:'close',WHIP:'close'}};
const IL_PLAYERS = ['George Springer','Jhoan Duran','Hunter Brown'];
const IL_NOTES   = {{'George Springer':'IL10 | OF | TOR','Jhoan Duran':'IL15 | RP | PHI','Hunter Brown':'IL15 | SP | HOU'}};

function norm(s){{return s.toLowerCase().replace(/[^a-z0-9]/g,'');}}
const TAKEN_NORM=TAKEN_LIST.map(norm);
function isTaken(n){{return TAKEN_NORM.some(t=>norm(n).includes(t)||t.includes(norm(n)));}}
function isMyPlayer(n){{return MR.some(r=>norm(n).includes(norm(r.name))||norm(r.name).includes(norm(n)));}}
function getMyPlayer(n){{return MR.find(r=>norm(n).includes(norm(r.name))||norm(r.name).includes(norm(n)));}}
function isStarting(n){{const p=getMyPlayer(n);return p?p.start!==false:false;}}
function isFreeAgent(n){{return !isMyPlayer(n)&&!isTaken(n);}}
function rowClass(n){{if(isMyPlayer(n))return isStarting(n)?'my-start':'my-bench';if(isTaken(n))return'taken';return'';}}
function statusTag(n){{if(isMyPlayer(n))return isStarting(n)?'<span class="ts">STARTING</span>':'<span class="tsi">BENCHED</span>';if(isTaken(n))return'<span class="ttk">TAKEN</span>';return'<span class="ta">FREE</span>';}}

function getMatchupRating(team,type){{
  const opp=TM[team];if(!opp)return{{label:'?',cls:'mup-avg',val:0}};
  const val=type==='bat'?opp.runs:opp.k;
  const allVals=Object.values(TM).map(t=>type==='bat'?t.runs:t.k);
  const avg=allVals.reduce((a,b)=>a+b,0)/allVals.length;
  const std=Math.sqrt(allVals.map(v=>(v-avg)**2).reduce((a,b)=>a+b,0)/allVals.length)||1;
  const z=(val-avg)/std;
  if(type==='bat'){{if(z>0.5)return{{label:'Easy',cls:'mup-easy',val}};if(z<-0.5)return{{label:'Tough',cls:'mup-tough',val}};return{{label:'Avg',cls:'mup-avg',val}};}}
  else{{if(z>0.5)return{{label:'Hard',cls:'mup-tough',val}};if(z<-0.5)return{{label:'Easy',cls:'mup-easy',val}};return{{label:'Avg',cls:'mup-avg',val}};}}
}}
function matchupTag(team,type){{const m=getMatchupRating(team,type);return`<span class="${{m.cls}}">${{m.label}}</span>`;}}
function mw(cat){{return MS[cat]==='winning'?CW[cat]*0.4:MS[cat]==='losing'?CW[cat]*1.6:CW[cat];}}
function bScore(b){{const mr=getMatchupRating(b.Opponent,'bat');const mb=mr.label==='Easy'?1.15:mr.label==='Tough'?0.87:1;return((b.Hits*mw('H')+b.Runs*mw('R')+b.HomeRuns*mw('HR')*2+b.TB*mw('TB')*.5+b.SB*mw('SB')*1.5+b.OBP*mw('OBP')*3)/10)*mb;}}
function pScore(p){{const mr=getMatchupRating(p.Opponent,'pit');const mb=mr.label==='Easy'?1.15:mr.label==='Hard'?0.87:1;const eB=Math.max(0,(5-p.ERA_proj))*mw('ERA')*.3;const wB=Math.max(0,(1.5-p.WHIP_proj))*mw('WHIP')*.5;return((p.Strikeouts*mw('K')*.5+p.QualityStart*mw('QS')*8+p.WinPct*mw('W')*8+eB+wB)/10)*mb;}}
function cs(v,lo,mid,hi){{return v>=hi?'good':v>=mid?'avg':v<=lo?'bad':'';}}

function sw(t,el){{
  document.querySelectorAll('.tp').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
  document.getElementById('tp-'+t).classList.add('active');el.classList.add('active');
  if(t==='bat')rB();if(t==='pit')rP();if(t==='wv')rW();
  if(t==='weekly')initWeekly();if(t==='stream')initStream();
  if(t==='h2h')initH2H();if(t==='mgmt')runMgmt();
}}
function swWeekly(tab,el){{
  document.getElementById('weekly-pitchers').style.display=tab==='pitchers'?'block':'none';
  document.getElementById('weekly-batters').style.display=tab==='batters'?'block':'none';
  el.parentElement.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
  el.classList.add('active');
  if(tab==='batters')renderWeeklyBatters();
}}

function initCS(){{document.getElementById('cs').innerHTML=Object.keys(CW).map(c=>`<div class="ci"><div class="cl">${{c}}<span class="cv" id="cv-${{c}}">${{CW[c]}}</span></div><input type="range" min="0" max="10" value="${{CW[c]}}" oninput="CW['${{c}}']=+this.value;document.getElementById('cv-${{c}}').textContent=this.value"></div>`).join('');}}
function initMT(){{document.getElementById('mt').innerHTML=Object.keys(MS).map(c=>`<div class="mt-cat close" id="mtc-${{c}}"><span style="font-family:'DM Mono',monospace;font-size:.75rem;font-weight:600">${{c}}</span><div style="display:flex;gap:3px"><button class="btn" style="font-size:.6rem;padding:2px 5px;background:rgba(57,211,83,.2);color:var(--accent3)" onclick="setMS('${{c}}','winning')">W</button><button class="btn" style="font-size:.6rem;padding:2px 5px;background:rgba(148,163,184,.1);color:var(--text2)" onclick="setMS('${{c}}','close')">~</button><button class="btn" style="font-size:.6rem;padding:2px 5px;background:rgba(248,113,113,.2);color:var(--red)" onclick="setMS('${{c}}','losing')">L</button></div></div>`).join('');}}
function setMS(cat,s){{MS[cat]=s;document.getElementById('mtc-'+cat).className='mt-cat '+s;}}

function initGames(){{
  const gm={{}};
  AP.forEach(p=>{{const k=p.Side==='H'?p.Opponent+'@'+p.Team:p.Team+'@'+p.Opponent;if(!gm[k])gm[k]={{away:p.Side==='H'?p.Opponent:p.Team,home:p.Side==='H'?p.Team:p.Opponent,awayP:'',homeP:''}};if(p.Side==='A')gm[k].awayP=p.FullName;if(p.Side==='H')gm[k].homeP=p.FullName;}});
  const gameMap={{}};GM.forEach(g=>{{gameMap[g.away+'@'+g.home]={{total:g.totalRuns}};}});
  document.getElementById('gl').innerHTML=Object.entries(gm).map(([k,g])=>{{const info=gameMap[k]||{{}};return`<div style="padding:4px 0;border-bottom:1px solid var(--border)"><div style="display:flex;gap:5px;align-items:center"><span style="color:var(--text2)">${{g.away}}</span><span style="color:var(--border)">@</span><span style="font-weight:500">${{g.home}}</span>${{info.total?`<span style="margin-left:auto;font-family:'DM Mono',monospace;font-size:.62rem;color:var(--gold)">${{info.total.toFixed(1)}} R</span>`:''}}</div><div style="font-size:.62rem;color:var(--text2)">${{g.awayP||'?'}} vs ${{g.homeP||'?'}}</div></div>`;}}).join('');
}}

function renderRoster(){{
  const el=document.getElementById('rl');
  if(!MR.length){{el.innerHTML='<div style="font-size:.72rem;color:var(--text2);text-align:center;padding:10px">No players in roster.json</div>';return;}}
  el.innerHTML=MR.map(p=>{{const isPit=['SP','RP'].includes(p.pos);const match=isPit?AP.find(x=>norm(x.FullName).includes(norm(p.name))):AB.find(x=>norm(x.FullName).includes(norm(p.name)));const sc=match?(isPit?pScore(match):bScore(match)).toFixed(1):'—';const isIL=IL_PLAYERS.includes(p.name);return`<div class="rs ${{p.start===false?'benched':'active'}}"><span class="sp-badge">${{p.pos}}</span><div style="flex:1"><div style="font-size:.8rem;font-weight:500">${{p.name}} ${{isIL?'<span class="il-badge">IL</span>':''}}</div><div style="font-size:.62rem;color:var(--text2)">${{p.team}} | <span style="color:var(--accent)">${{sc}}</span></div></div><span style="font-size:.65rem">${{p.start===false?'🪑':'▶'}}</span></div>`;}}).join('');
}}

function initTF(){{const s=document.getElementById('btf');[...new Set(AB.map(b=>b.Team))].sort().forEach(t=>{{const o=document.createElement('option');o.value=t;o.textContent=t;s.appendChild(o)}});}}

function rB(){{
  let d=[...AB];
  const sr=(document.getElementById('bs')?.value||'').toLowerCase();
  const sk=document.getElementById('bso')?.value||'score';
  const tm=document.getElementById('btf')?.value||'';
  const pitHands={{}};AP.forEach(p=>{{pitHands[p.Team]=p.PitcherHand;}});
  if(sr)d=d.filter(b=>b.FullName.toLowerCase().includes(sr)||b.Team.toLowerCase().includes(sr));
  if(tm)d=d.filter(b=>b.Team===tm);
  if(document.getElementById('f-top6')?.checked)d=d.filter(b=>b.BattingPosition<=6);
  if(document.getElementById('f-home')?.checked)d=d.filter(b=>b.Side==='H');
  if(document.getElementById('f-avail')?.checked)d=d.filter(b=>isFreeAgent(b.FullName));
  if(document.getElementById('f-hidetaken')?.checked)d=d.filter(b=>!isTaken(b.FullName)||isMyPlayer(b.FullName));
  const mpa=parseFloat(document.getElementById('f-minpa')?.value||0);
  const hnd=document.getElementById('f-hand')?.value||'';
  if(mpa)d=d.filter(b=>b.PlateAppearances>=mpa);
  if(hnd)d=d.filter(b=>pitHands[b.Opponent]===hnd);
  d.sort((a,b)=>sk==='score'?bScore(b)-bScore(a):b[sk]-a[sk]);
  const mH=Math.max(...d.map(b=>b.Hits),.001);
  document.getElementById('btb').innerHTML=d.map(b=>{{const sc=bScore(b).toFixed(1);const rc=rowClass(b.FullName);const bw=((b.Hits/mH)*40).toFixed(0);return`<tr class="${{rc}}"><td class="sc">${{sc}}</td><td style="font-weight:500;white-space:nowrap">${{b.FullName}}</td><td>${{statusTag(b.FullName)}}</td><td><span class="tb">${{b.Team}}</span></td><td style="color:var(--text2);font-size:.72rem">vs ${{b.Opponent}}</td><td>${{matchupTag(b.Opponent,'bat')}}</td><td><span class="pb">${{b.BattingPosition}}</span></td><td><div style="display:flex;align-items:center;gap:4px"><div style="height:3px;border-radius:2px;background:var(--accent);width:${{bw}}px;min-width:2px"></div><span class="sv ${{cs(b.Hits,.6,.8,1)}}">${{b.Hits.toFixed(3)}}</span></div></td><td class="sv ${{cs(b.Runs,.3,.45,.55)}}">${{b.Runs.toFixed(3)}}</td><td class="sv ${{cs(b.HomeRuns,.08,.13,.18)}}">${{b.HomeRuns.toFixed(3)}}</td><td class="sv ${{cs(b.TB,1,1.4,1.7)}}">${{b.TB.toFixed(3)}}</td><td class="sv ${{cs(b.SB,.01,.05,.12)}}">${{b.SB.toFixed(3)}}</td><td class="sv ${{cs(b.OBP,.28,.33,.38)}}">${{b.OBP.toFixed(3)}}</td><td style="color:var(--text2);font-size:.72rem">${{b.PlateAppearances.toFixed(1)}}</td></tr>`;}}).join('');
}}

function rP(){{
  let d=[...AP];
  const sr=(document.getElementById('ps')?.value||'').toLowerCase();
  const sk=document.getElementById('pso')?.value||'score';
  if(sr)d=d.filter(p=>p.FullName.toLowerCase().includes(sr)||p.Team.toLowerCase().includes(sr));
  if(document.getElementById('f-qs')?.checked)d=d.filter(p=>p.QualityStart>=.4);
  if(document.getElementById('f-avail-p')?.checked)d=d.filter(p=>isFreeAgent(p.FullName));
  if(document.getElementById('f-hidetaken-p')?.checked)d=d.filter(p=>!isTaken(p.FullName)||isMyPlayer(p.FullName));
  const mip=parseFloat(document.getElementById('f-minip')?.value||0);
  const mera=parseFloat(document.getElementById('f-maxera')?.value||99);
  const mwp=parseFloat(document.getElementById('f-minw')?.value||0)/100;
  if(mip)d=d.filter(p=>p.Innings>=mip);if(mera<99)d=d.filter(p=>p.ERA_proj<=mera);if(mwp)d=d.filter(p=>p.WinPct>=mwp);
  d.sort((a,b)=>{{if(sk==='score')return pScore(b)-pScore(a);if(sk==='ERA_proj'||sk==='WHIP_proj')return a[sk]-b[sk];return b[sk]-a[sk];}});
  document.getElementById('ptb').innerHTML=d.map(p=>{{const sc=pScore(p).toFixed(1);const rc=rowClass(p.FullName);return`<tr class="${{rc}}"><td class="sc">${{sc}}</td><td style="font-weight:500;white-space:nowrap">${{p.FullName}}</td><td>${{statusTag(p.FullName)}}</td><td><span class="tb">${{p.Team}}</span></td><td style="color:var(--text2);font-size:.72rem">vs ${{p.Opponent}}</td><td>${{matchupTag(p.Opponent,'pit')}}</td><td><span class="hb">${{p.PitcherHand}}</span></td><td style="font-family:'DM Mono',monospace;font-size:.76rem">${{p.Innings.toFixed(1)}}</td><td class="sv ${{cs(p.Strikeouts,4,6,8)}}">${{p.Strikeouts.toFixed(1)}}</td><td class="sv ${{cs(p.WinPct,.15,.25,.35)}}">${{(p.WinPct*100).toFixed(0)}}%</td><td class="sv ${{cs(p.QualityStart,.2,.35,.5)}}">${{(p.QualityStart*100).toFixed(0)}}%</td><td class="sv ${{cs(5-p.ERA_proj,-2,-.5,.5)}}">${{p.ERA_proj.toFixed(2)}}</td><td class="sv ${{cs(1.5-p.WHIP_proj,-.2,0,.3)}}">${{p.WHIP_proj.toFixed(3)}}</td></tr>`;}}).join('');
}}

function rW(){{
  const cat=document.getElementById('wc')?.value||'score';
  const hand=document.getElementById('whand')?.value||'';
  let bats=AB.filter(b=>isFreeAgent(b.FullName));
  let pits=AP.filter(p=>isFreeAgent(p.FullName));
  if(hand)pits=pits.filter(p=>p.PitcherHand===hand);
  let html='';
  if(['K_pit','QS','ERA','WHIP'].includes(cat)){{
    pits.sort((a,b)=>cat==='K_pit'?b.Strikeouts-a.Strikeouts:cat==='QS'?b.QualityStart-a.QualityStart:cat==='ERA'?a.ERA_proj-b.ERA_proj:a.WHIP_proj-b.WHIP_proj);
    html='<div class="rs2"><h3>🔥 Top Pitching Adds</h3>'+pits.slice(0,15).map(p=>{{const mr=getMatchupRating(p.Opponent,'pit');return`<div class="rc wav"><div class="rm"><div class="rn">${{p.FullName}} <span class="tb">${{p.Team}}</span> <span class="hb">${{p.PitcherHand}}</span> <span class="${{mr.cls}}">${{mr.label}}</span></div><div class="rd">vs ${{p.Opponent}} | ${{p.Innings.toFixed(1)}} IP | ${{p.Strikeouts.toFixed(1)}} K | QS:${{(p.QualityStart*100).toFixed(0)}}% | W:${{(p.WinPct*100).toFixed(0)}}% | ERA:${{p.ERA_proj.toFixed(2)}} | WHIP:${{p.WHIP_proj.toFixed(3)}}</div></div><div class="rsc">${{pScore(p).toFixed(1)}}</div></div>`;}}).join('')+'</div>';
  }}else{{
    const sf={{score:bScore,HR:b=>b.HomeRuns,SB:b=>b.SB,Hits:b=>b.Hits,Runs:b=>b.Runs,OBP:b=>b.OBP,TB:b=>b.TB}}[cat]||bScore;
    bats.sort((a,b)=>sf(b)-sf(a));
    html='<div class="rs2"><h3>🔥 Top Batting Adds</h3>'+bats.slice(0,20).map(b=>{{const mr=getMatchupRating(b.Opponent,'bat');return`<div class="rc wav"><div class="rm"><div class="rn">${{b.FullName}} <span class="tb">${{b.Team}}</span> <span class="pb">#${{b.BattingPosition}}</span> <span class="${{mr.cls}}">${{mr.label}}</span></div><div class="rd">vs ${{b.Opponent}} | H:${{b.Hits.toFixed(3)}} R:${{b.Runs.toFixed(3)}} HR:${{b.HomeRuns.toFixed(3)}} TB:${{b.TB.toFixed(3)}} SB:${{b.SB.toFixed(3)}} OBP:${{b.OBP.toFixed(3)}}</div></div><div class="rsc">${{bScore(b).toFixed(1)}}</div></div>`;}}).join('')+'</div>';
  }}
  document.getElementById('wo').innerHTML=html;
}}

// ── WEEKLY PLANNER ──
const ESPN_IP_LIMIT = 12;
function initWeekly(){{
  // Pitcher starts cards
  const el=document.getElementById('wp-cards');
  if(!Object.keys(WP).length){{el.innerHTML='<div class="es"><div>Upload multiple days of BallparkPal data to see weekly pitcher schedules</div></div>';return;}}
  const allDates=AVAILABLE_DATES;
  el.innerHTML=Object.entries(WP).sort((a,b)=>b[1].total_ip-a[1].total_ip).map(([name,data])=>{{
    const ipPct=Math.min(data.total_ip/ESPN_IP_LIMIT*100,100);
    const over=data.total_ip>ESPN_IP_LIMIT;
    const cardCls=over?'danger':data.total_ip>=ESPN_IP_LIMIT*0.75?'good':'';
    const dots=allDates.map(d=>{{
      const s=data.starts.find(x=>x.date===d);
      if(!s)return`<span class="start-dot no-start" title="${{d}}: No start"></span>`;
      const mr=TM[s.opp];
      const allK=mr?Object.values(TM).map(t=>t.k):[];
      const avgK=allK.length?allK.reduce((a,b)=>a+b,0)/allK.length:5;
      const dotCls=mr&&mr.k>avgK*1.15?'tough':mr&&mr.k<avgK*0.85?'easy':'avg';
      return`<span class="start-dot ${{dotCls}}" title="${{d}}: vs ${{s.opp}} | ${{s.ip}} IP | ${{s.k}} K | QS:${{(s.qs*100).toFixed(0)}}% | ERA:${{s.era}}"></span>`;
    }}).join('');
    return`<div class="pitcher-week-card ${{cardCls}}">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div>
          <span style="font-weight:600">${{name}}</span>
          <span class="tb" style="margin-left:6px">${{data.team}}</span>
          <span class="sp-badge" style="margin-left:4px">${{data.pos}}</span>
        </div>
        <div style="text-align:right">
          <span style="font-family:'DM Mono',monospace;font-size:.9rem;${{over?'color:var(--red)':'color:var(--accent)'}}">${{data.total_ip}} IP</span>
          <span style="font-size:.65rem;color:var(--text2);margin-left:4px">/ ${{ESPN_IP_LIMIT}}</span>
        </div>
      </div>
      <div style="margin:8px 0;display:flex;align-items:center;gap:8px">
        <div style="display:flex;align-items:center;gap:2px">${{dots}}</div>
        <span style="font-size:.65rem;color:var(--text2)">${{data.starts.length}} start(s)</span>
      </div>
      <div class="ip-bar ${{over?'over':''}}" style="width:${{ipPct}}%"></div>
      <div style="display:flex;gap:14px;margin-top:8px;font-size:.7rem;color:var(--text2)">
        <span>K: <span style="color:var(--text)">${{data.total_k}}</span></span>
        <span>ERA: <span style="color:var(--text)">${{data.avg_era}}</span></span>
        <span>WHIP: <span style="color:var(--text)">${{data.avg_whip}}</span></span>
        ${{data.starts.map(s=>`<span style="color:var(--text2)">${{s.date.slice(5)}} vs ${{s.opp}} (${{s.ip}}ip)</span>`).join('')}}
      </div>
    </div>`;
  }}).join('');
}}

function renderWeeklyBatters(){{
  const sk=document.getElementById('wb-sort')?.value||'Hits';
  const freeOnly=document.getElementById('wb-free')?.checked;
  const mineOnly=document.getElementById('wb-mine')?.checked;
  let d=[...WB];
  if(freeOnly)d=d.filter(b=>isFreeAgent(b.FullName));
  if(mineOnly)d=d.filter(b=>isMyPlayer(b.FullName));
  d.sort((a,b)=>b[sk]-a[sk]);
  document.getElementById('wb-table').innerHTML=d.slice(0,50).map(b=>{{
    const rc=rowClass(b.FullName);
    return`<tr class="${{rc}}"><td style="font-weight:500;white-space:nowrap">${{b.FullName}}</td><td>${{statusTag(b.FullName)}}</td><td><span class="tb">${{b.Team}}</span></td>
      <td style="color:var(--text2);font-size:.75rem">${{b.games}}g</td>
      <td class="sv ${{cs(b.Hits,1.5,2.5,3.5)}}">${{b.Hits.toFixed(2)}}</td>
      <td class="sv ${{cs(b.Runs,0.8,1.3,1.8)}}">${{b.Runs.toFixed(2)}}</td>
      <td class="sv ${{cs(b.HomeRuns,0.2,0.4,0.7)}}">${{b.HomeRuns.toFixed(2)}}</td>
      <td class="sv ${{cs(b.TB,3,5,7)}}">${{b.TB.toFixed(2)}}</td>
      <td class="sv ${{cs(b.SB,0,0.1,0.3)}}">${{b.SB.toFixed(2)}}</td>
      <td class="sv ${{cs(b.OBP,.28,.33,.38)}}">${{b.OBP.toFixed(3)}}</td></tr>`;
  }}).join('');
}}

// ── SP STREAMER BY DAY ──
let currentStreamDay='';
function initStream(){{
  const dates=Object.keys(SD).sort();
  if(!dates.length){{document.getElementById('stream-out').innerHTML='<div class="es"><div>Upload multiple days of BallparkPal data to see streaming targets by day</div></div>';return;}}
  const tabsEl=document.getElementById('stream-day-tabs');
  tabsEl.innerHTML=dates.map((d,i)=>{{
    const label=new Date(d+'T12:00:00').toLocaleDateString('en-US',{{weekday:'short',month:'short',day:'numeric'}});
    return`<div class="day-tab ${{i===0?'active':''}}" onclick="selectStreamDay('${{d}}',this)">${{label}}</div>`;
  }}).join('');
  selectStreamDay(dates[0], tabsEl.querySelector('.day-tab'));
}}
function selectStreamDay(d,el){{
  currentStreamDay=d;
  document.querySelectorAll('.day-tab').forEach(x=>x.classList.remove('active'));
  el.classList.add('active');
  const pitchers=(SD[d]||[]).filter(p=>isFreeAgent(p.name));
  if(!pitchers.length){{document.getElementById('stream-out').innerHTML='<div class="es"><div>No free agent starters with QS &gt; 20% on this date</div></div>';return;}}
  // Score them
  const scored=pitchers.map(p=>{{
    const mr=TM[p.opp]||{{k:5,runs:4,hr:1}};
    const allK=Object.values(TM).map(t=>t.k);const avgK=allK.reduce((a,b)=>a+b,0)/allK.length||5;
    const mBonus=mr.k<avgK*0.85?1.15:mr.k>avgK*1.15?0.87:1;
    const sc=((p.k*mw('K')*.5+p.qs*mw('QS')*8+p.win*mw('W')*8+Math.max(0,(5-p.era))*mw('ERA')*.3+Math.max(0,(1.5-p.whip))*mw('WHIP')*.5)/10)*mBonus;
    const mLabel=mr.k<avgK*0.85?'Easy':mr.k>avgK*1.15?'Hard':'Avg';
    const mCls=mr.k<avgK*0.85?'mup-easy':mr.k>avgK*1.15?'mup-tough':'mup-avg';
    return{{...p,sc,mLabel,mCls}};
  }}).sort((a,b)=>b.sc-a.sc);

  const label=new Date(d+'T12:00:00').toLocaleDateString('en-US',{{weekday:'long',month:'long',day:'numeric'}});
  let html=`<div class="rs2"><h3>🎯 Streaming Targets — ${{label}}</h3>`;
  html+=scored.slice(0,12).map((p,i)=>{{
    const grade=i<3?'🟢 Elite stream':i<6?'🟡 Good stream':i<9?'🟠 Dart throw':'🔴 Risky';
    return`<div class="rc ${{i<3?'str':i<6?'':'sit'}}">
      <div style="font-family:'Bebas Neue',sans-serif;font-size:1.5rem;color:var(--text2);min-width:28px">${{i+1}}</div>
      <div class="rm">
        <div class="rn">${{p.name}} <span class="tb">${{p.team}}</span> <span class="hb">${{p.hand}}</span> <span class="${{p.mCls}}">${{p.mLabel}} matchup</span></div>
        <div class="rd">vs ${{p.opp}} | ${{p.ip}} IP | ${{p.k}} K | QS:${{(p.qs*100).toFixed(0)}}% | W:${{(p.win*100).toFixed(0)}}% | ERA:${{p.era}} | WHIP:${{p.whip}}</div>
        <div style="font-size:.65rem;margin-top:3px">${{grade}}</div>
      </div>
      <div class="rsc">${{p.sc.toFixed(1)}}</div>
    </div>`;
  }}).join('');
  html+='</div>';
  document.getElementById('stream-out').innerHTML=html;
}}

// ── H2H TRACKER ──
const H2H_CATS=['H','R','HR','TB','SB','OBP','K','QS','W','ERA','WHIP'];
function initH2H(){{
  const el=document.getElementById('h2h-inputs');if(el.innerHTML)return;
  el.innerHTML=H2H_CATS.map(c=>{{const lb=c==='ERA'||c==='WHIP';return`<div class="h2h-cat close" id="h2hc-${{c}}"><div class="h2h-label">${{c}} ${{lb?'↓':''}}</div><div class="h2h-inputs"><input class="h2h-input" id="h2h-my-${{c}}" placeholder="Mine" type="number" step="0.001" oninput="calcH2H()"><span class="h2h-vs">vs</span><input class="h2h-input" id="h2h-opp-${{c}}" placeholder="Opp" type="number" step="0.001" oninput="calcH2H()"></div><div class="h2h-result" id="h2hr-${{c}}"></div></div>`;}}).join('');
}}
function calcH2H(){{
  let wins=0,losses=0,close=0;const results={{}};
  H2H_CATS.forEach(c=>{{
    const myV=parseFloat(document.getElementById('h2h-my-'+c)?.value);
    const opV=parseFloat(document.getElementById('h2h-opp-'+c)?.value);
    const el=document.getElementById('h2hc-'+c);const res=document.getElementById('h2hr-'+c);
    if(isNaN(myV)||isNaN(opV)){{el.className='h2h-cat close';res.innerHTML='';results[c]='unknown';return;}}
    const lb=c==='ERA'||c==='WHIP';const diff=lb?opV-myV:myV-opV;
    if(diff>0){{el.className='h2h-cat winning';res.innerHTML=`<span style="color:var(--accent3)">✓ +${{Math.abs(diff).toFixed(3)}}</span>`;wins++;results[c]='winning';}}
    else if(diff<0){{el.className='h2h-cat losing';res.innerHTML=`<span style="color:var(--red)">✗ ${{diff.toFixed(3)}}</span>`;losses++;results[c]='losing';}}
    else{{el.className='h2h-cat close';res.innerHTML=`<span style="color:var(--gold)">— Tied</span>`;close++;results[c]='close';}}
  }});
  H2H_CATS.forEach(c=>{{if(results[c]&&results[c]!=='unknown'){{MS[c]=results[c];const mt=document.getElementById('mtc-'+c);if(mt)mt.className='mt-cat '+results[c];}}}});
  const total=wins+losses+close;
  if(!total){{document.getElementById('h2h-out').innerHTML='';return;}}
  const losing=H2H_CATS.filter(c=>results[c]==='losing');
  const closeC=H2H_CATS.filter(c=>results[c]==='close');
  let out=`<div class="rs2" style="margin-top:16px"><h3>📊 Matchup Summary</h3>
    <div style="display:flex;gap:10px;margin-bottom:12px">
      <div class="sc2" style="flex:1"><div class="cat" style="color:var(--accent3)">W</div><div class="val">${{wins}}</div></div>
      <div class="sc2" style="flex:1"><div class="cat" style="color:var(--red)">L</div><div class="val">${{losses}}</div></div>
      <div class="sc2" style="flex:1"><div class="cat" style="color:var(--gold)">~</div><div class="val">${{close}}</div></div>
    </div>`;
  if(losing.length)out+=`<div style="font-size:.8rem;margin-bottom:6px"><span style="color:var(--red);font-weight:600">Chase:</span> ${{losing.join(', ')}}</div>`;
  if(closeC.length)out+=`<div style="font-size:.8rem;margin-bottom:6px"><span style="color:var(--gold);font-weight:600">Swing:</span> ${{closeC.join(', ')}}</div>`;
  out+=`<div style="font-size:.72rem;color:var(--text2)">Weights updated — run Optimizer for targeted picks</div></div>`;
  document.getElementById('h2h-out').innerHTML=out;
}}
function resetH2H(){{H2H_CATS.forEach(c=>{{const mi=document.getElementById('h2h-my-'+c);const oi=document.getElementById('h2h-opp-'+c);if(mi)mi.value='';if(oi)oi.value='';const el=document.getElementById('h2hc-'+c);if(el)el.className='h2h-cat close';const r=document.getElementById('h2hr-'+c);if(r)r.innerHTML='';}}); document.getElementById('h2h-out').innerHTML='';}}

// ── ROSTER MGMT ──
function runMgmt(){{
  let html='';
  const ilPlayers=MR.filter(r=>IL_PLAYERS.includes(r.name));
  if(ilPlayers.length){{html+=`<div class="rs2"><h3>🏥 IL Monitor</h3>`;ilPlayers.forEach(p=>{{html+=`<div class="rc sit"><div class="rm"><div class="rn"><span class="il-badge">IL</span> &nbsp;${{p.name}}</div><div class="rd">${{IL_NOTES[p.name]||'On injured list'}} | Update roster.json when activated</div></div></div>`;}});html+='</div>';}}
  const sB=[...AB].map(b=>({{...b,score:bScore(b)}})).sort((a,b)=>b.score-a.score);
  const sP=[...AP].map(p=>({{...p,score:pScore(p)}})).sort((a,b)=>b.score-a.score);
  const myBat=MR.filter(r=>!['SP','RP'].includes(r.pos)&&r.start!==false).map(r=>{{const m=AB.find(b=>norm(b.FullName).includes(norm(r.name)));return m?{{...m,score:bScore(m),rPos:r.pos}}:null;}}).filter(Boolean).sort((a,b)=>a.score-b.score);
  const myPit=MR.filter(r=>['SP','RP'].includes(r.pos)&&r.start!==false).map(r=>{{const m=AP.find(p=>norm(p.FullName).includes(norm(r.name)));return m?{{...m,score:pScore(m),rPos:r.pos}}:null;}}).filter(Boolean).sort((a,b)=>a.score-b.score);
  const freeBat=sB.filter(b=>isFreeAgent(b.FullName));
  const freePit=sP.filter(p=>isFreeAgent(p.FullName));
  html+=`<div class="rs2"><h3>🔄 Add / Drop Suggestions</h3>`;
  let suggestions=0;
  myBat.slice(0,3).forEach(mine=>{{const better=freeBat.find(f=>f.score>mine.score*1.2);if(better){{suggestions++;html+=`<div class="rc wav"><div class="rm"><div class="rn">DROP <span style="color:var(--red)">${{mine.FullName}}</span> → ADD <span style="color:var(--accent3)">${{better.FullName}}</span> <span class="tb">${{better.Team}}</span></div><div class="rd">Yours: ${{mine.score.toFixed(1)}} | H:${{mine.Hits.toFixed(3)}} HR:${{mine.HomeRuns.toFixed(3)}} OBP:${{mine.OBP.toFixed(3)}}</div><div class="rd" style="color:var(--accent3)">Add: ${{better.score.toFixed(1)}} | H:${{better.Hits.toFixed(3)}} HR:${{better.HomeRuns.toFixed(3)}} OBP:${{better.OBP.toFixed(3)}} | #${{better.BattingPosition}} vs ${{better.Opponent}}</div></div><div style="text-align:right"><div style="font-family:'Bebas Neue',sans-serif;font-size:1.1rem;color:var(--accent3)">+${{(better.score-mine.score).toFixed(1)}}</div><div style="font-size:.62rem;color:var(--text2)">upgrade</div></div></div>`;}}}});
  myPit.filter(p=>p.rPos==='SP').slice(0,2).forEach(mine=>{{const better=freePit.find(f=>f.score>mine.score*1.2&&f.QualityStart>=.3);if(better){{suggestions++;html+=`<div class="rc wav"><div class="rm"><div class="rn">DROP <span style="color:var(--red)">${{mine.FullName}}</span> → ADD <span style="color:var(--accent3)">${{better.FullName}}</span> <span class="tb">${{better.Team}}</span></div><div class="rd">Yours: ${{mine.score.toFixed(1)}} | ${{mine.Strikeouts.toFixed(1)}} K | QS:${{(mine.QualityStart*100).toFixed(0)}}% | ERA:${{mine.ERA_proj.toFixed(2)}}</div><div class="rd" style="color:var(--accent3)">Add: ${{better.score.toFixed(1)}} | ${{better.Strikeouts.toFixed(1)}} K | QS:${{(better.QualityStart*100).toFixed(0)}}% | ERA:${{better.ERA_proj.toFixed(2)}} | vs ${{better.Opponent}}</div></div><div style="text-align:right"><div style="font-family:'Bebas Neue',sans-serif;font-size:1.1rem;color:var(--accent3)">+${{(better.score-mine.score).toFixed(1)}}</div><div style="font-size:.62rem;color:var(--text2)">upgrade</div></div></div>`;}}}});
  if(!suggestions)html+=`<div style="font-size:.8rem;color:var(--text2);padding:10px">✓ No obvious upgrades today — your roster looks solid</div>`;
  html+='</div>';
  document.getElementById('mgmt-out').innerHTML=html;
}}

// ── OPTIMIZER ──
function runOpt(){{
  const sB=[...AB].map(b=>({{...b,score:bScore(b)}})).sort((a,b)=>b.score-a.score);
  const sP=[...AP].map(p=>({{...p,score:pScore(p)}})).sort((a,b)=>b.score-a.score);
  const myBat=MR.filter(r=>!['SP','RP'].includes(r.pos)).map(r=>{{const m=AB.find(b=>norm(b.FullName).includes(norm(r.name)));return m?{{...m,start:r.start!==false}}:null;}}).filter(Boolean);
  const myPit=MR.filter(r=>['SP','RP'].includes(r.pos)).map(r=>{{const m=AP.find(p=>norm(p.FullName).includes(norm(r.name)));return m?{{...m,start:r.start!==false}}:null;}}).filter(Boolean);
  const bSS=myBat.map(b=>{{const sc=bScore(b);const rank=sB.findIndex(x=>x.PlayerId===b.PlayerId)+1;const pct=rank/sB.length;return{{...b,score:sc,rank,action:pct<.15?'START':pct<.45?'CONSIDER':'SIT'}};}});
  const pSS=myPit.map(p=>{{const sc=pScore(p);const rank=sP.findIndex(x=>x.PlayerId===p.PlayerId)+1;const pct=rank>0?rank/sP.length:1;const action=rank===0?'NO START':pct<.25?'START':pct<.55?'CONSIDER':'SIT';return{{...p,score:sc,rank,action}};}});
  const wB=sB.filter(b=>isFreeAgent(b.FullName)).slice(0,5);
  const wP=sP.filter(p=>isFreeAgent(p.FullName)).slice(0,5);
  const tH=sB[0],tHR=[...sB].sort((a,b)=>b.HomeRuns-a.HomeRuns)[0],tSB=[...sB].sort((a,b)=>b.SB-a.SB)[0],tO=[...sB].sort((a,b)=>b.OBP-a.OBP)[0],tK=sP[0],tQ=[...sP].sort((a,b)=>b.QualityStart-a.QualityStart)[0];
  const ilActive=MR.filter(r=>IL_PLAYERS.includes(r.name));
  let html='';
  if(ilActive.length){{html+=`<div class="rs2"><h3>🏥 IL Alerts</h3>`;ilActive.forEach(p=>{{html+=`<div class="rc warn"><div class="rm"><div class="rn"><span class="il-badge">IL</span> &nbsp;${{p.name}}</div><div class="rd">${{IL_NOTES[p.name]||'On injured list'}}</div></div></div>`;}});html+='</div>';}}
  html+=`<div class="rs2"><h3>📊 Today's Category Leaders</h3><div class="sg">${{[[tH,'H',tH.Hits.toFixed(3)+' H','Hit Machine'],[tHR,'HR',tHR.HomeRuns.toFixed(3)+' HR','HR Threat'],[tSB,'SB',tSB.SB.toFixed(3)+' SB','Speedster'],[tO,'OBP',tO.OBP.toFixed(3),'Patience'],[tK,'K',tK.Strikeouts.toFixed(1)+' K','Swing & Miss'],[tQ,'QS',(tQ.QualityStart*100).toFixed(0)+'%','QS']].map(([x,c,v,d])=>`<div class="sc2"><div class="cat">${{c}}</div><div class="val">${{v}}</div><div class="dsc" style="color:var(--text)">${{x.FullName}}</div><div class="dsc">${{x.Team}} vs ${{x.Opponent}}</div></div>`).join('')}}</div></div>`;
  if(bSS.length||pSS.length){{
    html+=`<div class="rs2"><h3>🎯 Start / Sit — Your Roster</h3>`;
    [...bSS,...pSS].sort((a,b)=>b.score-a.score).forEach(x=>{{
      if(x.action==='NO START'){{
        html+=`<div class="rc"><div class="rm"><div class="rn"><span class="ttk">NO START</span> &nbsp;${{x.FullName}} <span class="tb">${{x.Team}}</span></div><div class="rd">Not scheduled to start today per BallparkPal</div></div></div>`;
        return;
      }}
      const tc=x.action==='START'?'ts':x.action==='SIT'?'tsi':'tw';
      const rc=x.action==='START'?'str':x.action==='SIT'?'sit':'';
      const ip='ERA_proj'in x;const mr=getMatchupRating(x.Opponent,ip?'pit':'bat');
      const dt=ip?`vs ${{x.Opponent}} (${{mr.label}} matchup) | ${{x.Innings.toFixed(1)}} IP | ${{x.Strikeouts.toFixed(1)}} K | QS:${{(x.QualityStart*100).toFixed(0)}}% | W:${{(x.WinPct*100).toFixed(0)}}% | ERA:${{x.ERA_proj.toFixed(2)}} | WHIP:${{x.WHIP_proj.toFixed(3)}}`:
              `Bat #${{x.BattingPosition}} vs ${{x.Opponent}} (${{mr.label}} matchup) | H:${{x.Hits.toFixed(3)}} R:${{x.Runs.toFixed(3)}} HR:${{x.HomeRuns.toFixed(3)}} TB:${{x.TB.toFixed(3)}} SB:${{x.SB.toFixed(3)}} OBP:${{x.OBP.toFixed(3)}}`;
      html+=`<div class="rc ${{rc}}"><div class="rm"><div class="rn"><span class="${{tc}}">${{x.action}}</span> &nbsp;${{x.FullName}} <span class="tb">${{x.Team}}</span> <span class="${{mr.cls}}">vs ${{x.Opponent}} (${{mr.label}})</span> <span style="font-size:.65rem;color:var(--text2)">#${{x.rank}} overall</span></div><div class="rd">${{dt}}</div></div><div class="rsc">${{x.score.toFixed(1)}}</div></div>`;
    }});
    html+='</div>';
  }}
  html+=`<div class="rs2"><h3>🔥 Top Waiver Wire Adds Today</h3>`;
  wB.forEach(b=>{{const mr=getMatchupRating(b.Opponent,'bat');html+=`<div class="rc wav"><div class="rm"><div class="rn"><span class="tw">BATTER</span> &nbsp;${{b.FullName}} <span class="tb">${{b.Team}}</span> <span class="pb">#${{b.BattingPosition}}</span> <span class="${{mr.cls}}">${{mr.label}}</span></div><div class="rd">vs ${{b.Opponent}} | H:${{b.Hits.toFixed(3)}} R:${{b.Runs.toFixed(3)}} HR:${{b.HomeRuns.toFixed(3)}} TB:${{b.TB.toFixed(3)}} SB:${{b.SB.toFixed(3)}} OBP:${{b.OBP.toFixed(3)}}</div></div><div class="rsc">${{b.score.toFixed(1)}}</div></div>`;}});
  wP.forEach(p=>{{const mr=getMatchupRating(p.Opponent,'pit');html+=`<div class="rc wav"><div class="rm"><div class="rn"><span class="tw">PITCHER</span> &nbsp;${{p.FullName}} <span class="tb">${{p.Team}}</span> <span class="hb">${{p.PitcherHand}}</span> <span class="${{mr.cls}}">${{mr.label}}</span></div><div class="rd">vs ${{p.Opponent}} | ${{p.Innings.toFixed(1)}} IP | ${{p.Strikeouts.toFixed(1)}} K | QS:${{(p.QualityStart*100).toFixed(0)}}% | W:${{(p.WinPct*100).toFixed(0)}}% | ERA:${{p.ERA_proj.toFixed(2)}} | WHIP:${{p.WHIP_proj.toFixed(3)}}</div></div><div class="rsc">${{p.score.toFixed(1)}}</div></div>`;}});
  html+='</div>';
  document.getElementById('oo').innerHTML=html;
}}

document.addEventListener('DOMContentLoaded',()=>{{initCS();initMT();initGames();renderRoster();initTF();rB();rP();}});
</script>
</body>
</html>'''

def main():
    build_date = datetime.now().strftime("%B %d, %Y")
    print(f"BallparkPal Fantasy Optimizer — Build: {build_date}")
    print("Loading data files...")

    df_batters  = load_multi_day("Batters")
    df_pitchers = load_multi_day("Pitchers")
    df_teams    = load_multi_day("Teams")
    df_games    = load_excel("BallparkPal_Games.xlsx")
    if df_games is None: df_games = load_multi_day("Games")

    if df_batters is None or df_pitchers is None:
        print("ERROR: Missing required Excel files"); sys.exit(1)

    # Get all available dates
    all_dates = sorted(df_batters['GameDate'].unique().tolist())

    # Use TODAY env var (set by GitHub Action) or fall back to system date
    today_actual = os.environ.get('TODAY', str(date.today()))
    print(f"  Today's date: {today_actual}")

    # Only show dates >= today (ignore old/stale data automatically)
    available_dates = [d for d in all_dates if d >= today_actual]
    if not available_dates:
        # Fallback if no future data — use most recent available
        available_dates = all_dates
        print(f"  WARNING: No data for today or future, using all available dates")

    today_str = available_dates[0]
    print(f"  Dates loaded: {available_dates}")

    # Today's data
    batters_json  = process_batters_day(df_batters, today_str)
    pitchers_json = process_pitchers_day(df_pitchers, today_str)
    teams_json    = process_teams_day(df_teams, today_str) if df_teams is not None else {}
    games_json    = []
    if df_games is not None:
        try: games_json = process_games_day(df_games, today_str)
        except: games_json = []

    # Multi-day data
    roster  = load_roster()
    taken   = load_taken()
    weekly_pitchers  = build_weekly_pitcher_data(df_pitchers, roster)
    weekly_batters   = build_weekly_batter_data(df_batters)
    streaming_by_day = build_streaming_by_day(df_pitchers)

    print(f"  Today: {len(batters_json)} batters, {len(pitchers_json)} pitchers")
    print(f"  Weekly: {len(weekly_pitchers)} pitchers tracked, {len(streaming_by_day)} stream days")
    print(f"  Roster: {len(roster['players'])} players  Taken: {len(taken.get('taken',[]))}")

    html = build_html(batters_json, pitchers_json, teams_json, games_json,
                      weekly_pitchers, weekly_batters, streaming_by_day,
                      roster, taken, build_date, available_dates)

    with open(OUTPUT_FILE, 'w') as f: f.write(html)
    print(f"  Done — {len(html)//1024} KB written to index.html")

if __name__ == "__main__":
    main()
