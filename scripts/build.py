#!/usr/bin/env python3
"""
BallparkPal Fantasy Optimizer - Daily Build Script
Reads Excel files from /data, builds index.html with embedded data.
Run manually or via GitHub Actions.
"""

import pandas as pd
import json
import os
import sys
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
ROSTER_FILE = os.path.join(os.path.dirname(__file__), '..', 'roster.json')
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), '..', 'index.html')

def load_excel(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        print(f"  WARNING: {filename} not found in /data — skipping")
        return None
    return pd.read_excel(path)

def process_batters(df):
    df['Team'] = df['Team'].str.strip()
    df['Opponent'] = df['Opponent'].str.strip()
    df['OBP'] = ((df['Hits'] + df['Walks']) / df['PlateAppearances']).round(3)
    df['SB'] = df['StolenBaseSuccesses']
    df['TB'] = df['Bases']
    cols = ['PlayerId','FullName','Team','Opponent','Side','BattingPosition',
            'PlateAppearances','Hits','Runs','HomeRuns','TB','SB','OBP',
            'Strikeouts','Walks','PointsDK','PointsFD',
            'HitProbability','HomeRunProbability','StolenBaseProbability']
    return df[cols].round(3).to_dict('records')

def process_pitchers(df):
    df['Team'] = df['Team'].str.strip()
    df['Opponent'] = df['Opponent'].str.strip()
    df['ERA_proj'] = (df['RunsAllowed'] / df['Innings'] * 9).round(3)
    df['WHIP_proj'] = ((df['HitsAllowed'] + df['Walks']) / df['Innings']).round(3)
    cols = ['PlayerId','FullName','Team','Opponent','PitcherHand','Side',
            'Innings','WinPct','QualityStart','Strikeouts',
            'ERA_proj','WHIP_proj','RunsAllowed','HitsAllowed','Walks',
            'PointsDK','PointsFD']
    return df[cols].round(3).to_dict('records')

def load_roster():
    if not os.path.exists(ROSTER_FILE):
        print("  WARNING: roster.json not found — using empty roster")
        return {"team_name": "My Team", "players": []}
    with open(ROSTER_FILE) as f:
        return json.load(f)

def build_html(batters_json, pitchers_json, roster, build_date):
    b = json.dumps(batters_json)
    p = json.dumps(pitchers_json)
    r = json.dumps(roster)
    nb = len(batters_json)
    np_ = len(pitchers_json)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BallparkPal Fantasy Optimizer</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap');
  :root {{
    --bg:#0a0e17;--surface:#111827;--surface2:#1a2234;--border:#1e2d47;
    --accent:#00d4ff;--accent2:#ff6b35;--accent3:#39d353;
    --text:#e2e8f0;--text2:#94a3b8;--red:#f87171;--gold:#fbbf24;
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:var(--bg);color:var(--text);font-family:'DM Sans',sans-serif;min-height:100vh}}
  .header{{background:linear-gradient(135deg,#0a0e17,#0d1829,#091420);border-bottom:1px solid var(--border);padding:14px 24px;display:flex;align-items:center;gap:16px;justify-content:space-between}}
  .header h1{{font-family:'Bebas Neue',sans-serif;font-size:1.8rem;letter-spacing:2px;color:var(--accent)}}
  .header .sub{{color:var(--text2);font-size:0.72rem;letter-spacing:1px;text-transform:uppercase;margin-top:2px}}
  .badge{{background:var(--accent2);color:#fff;padding:2px 8px;border-radius:4px;font-size:0.65rem;font-weight:600;text-transform:uppercase;letter-spacing:1px}}
  .badge-date{{background:var(--surface2);color:var(--text2);border:1px solid var(--border);padding:2px 10px;border-radius:4px;font-size:0.65rem;font-family:'DM Mono',monospace}}
  .layout{{display:grid;grid-template-columns:310px 1fr;height:calc(100vh - 62px)}}
  /* SIDEBAR */
  .sidebar{{background:var(--surface);border-right:1px solid var(--border);overflow-y:auto;display:flex;flex-direction:column}}
  .ss{{padding:14px;border-bottom:1px solid var(--border)}}
  .ss h3{{font-family:'Bebas Neue',sans-serif;font-size:0.95rem;letter-spacing:2px;color:var(--accent);margin-bottom:10px}}
  .rs{{display:flex;align-items:center;gap:6px;padding:5px 7px;border-radius:5px;background:var(--surface2);margin-bottom:3px;border:1px solid transparent;transition:all .15s}}
  .rs.active{{border-color:var(--accent);background:rgba(0,212,255,.08)}}
  .rs.benched{{opacity:.5}}
  .rs.il{{border-left:2px solid var(--red)}}
  .sp-badge{{font-family:'DM Mono',monospace;font-size:0.6rem;color:var(--accent2);background:rgba(255,107,53,.15);padding:2px 4px;border-radius:3px;min-width:26px;text-align:center}}
  .cat-grid{{display:grid;grid-template-columns:1fr 1fr;gap:6px}}
  .ci{{display:flex;flex-direction:column;gap:2px}}
  .cl{{font-size:0.68rem;color:var(--text2);font-family:'DM Mono',monospace;display:flex;justify-content:space-between}}
  .cv{{color:var(--accent)}}
  input[type=range]{{width:100%;height:3px;background:var(--border);-webkit-appearance:none;border-radius:2px;cursor:pointer}}
  input[type=range]::-webkit-slider-thumb{{-webkit-appearance:none;width:11px;height:11px;background:var(--accent);border-radius:50%}}
  /* MAIN */
  .main{{overflow-y:auto;display:flex;flex-direction:column}}
  .tabs{{display:flex;border-bottom:1px solid var(--border);background:var(--surface);padding:0 20px;position:sticky;top:0;z-index:10}}
  .tab{{padding:11px 16px;font-size:0.75rem;font-weight:600;text-transform:uppercase;letter-spacing:1px;cursor:pointer;color:var(--text2);border-bottom:2px solid transparent;transition:all .15s}}
  .tab.active{{color:var(--accent);border-bottom-color:var(--accent)}}
  .tab:hover{{color:var(--text)}}
  .tc{{padding:18px;flex:1}}
  .tp{{display:none}}.tp.active{{display:block}}
  /* Controls */
  .ctrls{{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;align-items:center}}
  .sb{{background:var(--surface);border:1px solid var(--border);color:var(--text);padding:7px 11px;border-radius:5px;font-size:0.82rem;font-family:'DM Sans',sans-serif;flex:1;min-width:160px}}
  .sb:focus{{outline:none;border-color:var(--accent)}}
  select{{background:var(--surface);border:1px solid var(--border);color:var(--text);padding:7px 11px;border-radius:5px;font-size:0.78rem;font-family:'DM Sans',sans-serif;cursor:pointer}}
  select:focus{{outline:none;border-color:var(--accent)}}
  .btn{{padding:7px 14px;border-radius:5px;border:none;cursor:pointer;font-size:0.78rem;font-weight:600;letter-spacing:.4px;transition:all .15s}}
  .btn-p{{background:var(--accent);color:#000}}.btn-p:hover{{background:#33ddff}}
  .btn-s{{background:var(--accent3);color:#000}}.btn-s:hover{{opacity:.85}}
  .btn-d{{background:var(--red);color:#000;font-size:0.65rem;padding:3px 7px}}
  .btn-sm{{background:var(--surface2);color:var(--accent);font-size:0.67rem;padding:3px 7px;border:1px solid var(--border)}}
  /* Tables */
  .pt{{width:100%;border-collapse:collapse;font-size:0.78rem}}
  .pt th{{text-align:left;padding:7px 9px;color:var(--text2);font-size:0.67rem;letter-spacing:1px;text-transform:uppercase;border-bottom:1px solid var(--border);white-space:nowrap;cursor:pointer;background:var(--surface);position:sticky;top:0}}
  .pt th:hover{{color:var(--accent)}}
  .pt td{{padding:6px 9px;border-bottom:1px solid rgba(30,45,71,.4);vertical-align:middle}}
  .pt tr:hover td{{background:rgba(0,212,255,.03)}}
  .pt tr.my-start td{{background:rgba(57,211,83,.06)}}
  .pt tr.my-bench td{{background:rgba(255,107,53,.04)}}
  .pt tr.available td{{}}
  .tb{{font-family:'DM Mono',monospace;font-size:0.62rem;background:var(--surface2);color:var(--text2);padding:1px 4px;border-radius:3px}}
  .pb{{font-family:'DM Mono',monospace;font-size:0.62rem;background:rgba(255,107,53,.15);color:var(--accent2);padding:1px 4px;border-radius:3px}}
  .hb{{font-family:'DM Mono',monospace;font-size:0.62rem;background:rgba(0,212,255,.1);color:var(--accent);padding:1px 4px;border-radius:3px}}
  .sv{{font-family:'DM Mono',monospace;font-size:0.76rem}}
  .good{{color:var(--accent3)}}.avg{{color:var(--gold)}}.bad{{color:var(--red)}}
  .sc{{font-family:'Bebas Neue',sans-serif;font-size:1.05rem;color:var(--accent)}}
  /* Status tags */
  .ts{{background:rgba(57,211,83,.15);color:var(--accent3);padding:1px 5px;border-radius:3px;font-size:0.62rem;font-weight:600}}
  .tw{{background:rgba(251,191,36,.15);color:var(--gold);padding:1px 5px;border-radius:3px;font-size:0.62rem;font-weight:600}}
  .tsi{{background:rgba(248,113,113,.15);color:var(--red);padding:1px 5px;border-radius:3px;font-size:0.62rem;font-weight:600}}
  .ta{{background:rgba(0,212,255,.1);color:var(--accent);padding:1px 5px;border-radius:3px;font-size:0.62rem;font-weight:600}}
  /* Summary / rec cards */
  .sg{{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px;margin-bottom:18px}}
  .sc2{{background:var(--surface);border:1px solid var(--border);border-radius:7px;padding:11px;text-align:center}}
  .sc2 .cat{{font-family:'Bebas Neue',sans-serif;font-size:0.95rem;color:var(--accent);letter-spacing:1px}}
  .sc2 .val{{font-family:'DM Mono',monospace;font-size:1.2rem;font-weight:500;margin:3px 0}}
  .sc2 .dsc{{font-size:0.62rem;color:var(--text2)}}
  .rs2{{margin-bottom:20px}}
  .rs2 h3{{font-family:'Bebas Neue',sans-serif;font-size:1.1rem;letter-spacing:2px;color:var(--accent2);margin-bottom:10px}}
  .rc{{background:var(--surface);border:1px solid var(--border);border-radius:7px;padding:12px 14px;margin-bottom:7px;display:flex;align-items:center;gap:10px;border-left:3px solid var(--accent)}}
  .rc.wav{{border-left-color:var(--gold)}}.rc.sit{{border-left-color:var(--red)}}.rc.str{{border-left-color:var(--accent3)}}
  .rm{{flex:1}}.rn{{font-weight:600;font-size:0.85rem}}.rd{{font-size:0.72rem;color:var(--text2);margin-top:3px}}
  .rsc{{font-family:'Bebas Neue',sans-serif;font-size:1.3rem;color:var(--accent)}}
  .es{{text-align:center;padding:40px;color:var(--text2)}}.es .ic{{font-size:2rem;margin-bottom:8px}}
  /* Matchup tracker */
  .mt-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px}}
  .mt-cat{{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:10px;display:flex;align-items:center;justify-content:space-between}}
  .mt-cat.winning{{border-color:var(--accent3);background:rgba(57,211,83,.05)}}
  .mt-cat.losing{{border-color:var(--red);background:rgba(248,113,113,.05)}}
  .mt-cat.close{{border-color:var(--gold);background:rgba(251,191,36,.05)}}
  .mt-label{{font-family:'DM Mono',monospace;font-size:0.75rem;font-weight:600}}
  .mt-status{{font-size:0.65rem;font-weight:600;padding:2px 6px;border-radius:3px}}
  .mt-status.w{{background:rgba(57,211,83,.2);color:var(--accent3)}}
  .mt-status.l{{background:rgba(248,113,113,.2);color:var(--red)}}
  .mt-status.c{{background:rgba(251,191,36,.2);color:var(--gold)}}
  ::-webkit-scrollbar{{width:4px;height:4px}}
  ::-webkit-scrollbar-track{{background:var(--bg)}}
  ::-webkit-scrollbar-thumb{{background:var(--border);border-radius:2px}}
  .filter-row{{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:10px;padding:10px;background:var(--surface);border:1px solid var(--border);border-radius:6px}}
  .filter-row label{{font-size:0.75rem;display:flex;align-items:center;gap:5px;cursor:pointer;color:var(--text2)}}
  .filter-row label:hover{{color:var(--text)}}
  .fl-sep{{width:1px;height:16px;background:var(--border)}}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>⚾ BallparkPal Fantasy Optimizer</h1>
    <div class="sub">ESPN H2H Categories &nbsp;|&nbsp; {nb} Batters &nbsp;|&nbsp; {np_} Pitchers</div>
  </div>
  <div style="display:flex;gap:8px;align-items:center">
    <span class="badge-date">📅 {build_date}</span>
    <span class="badge">Live Projections</span>
  </div>
</div>

<div class="layout">
  <!-- SIDEBAR -->
  <div class="sidebar">
    <div class="ss">
      <h3>My Roster</h3>
      <div style="font-size:.7rem;color:var(--text2);margin-bottom:8px">Loaded from <code style="color:var(--accent);font-size:.65rem">roster.json</code> — edit that file to add/drop players</div>
      <div id="rl"></div>
    </div>

    <div class="ss">
      <h3>Matchup Status</h3>
      <div style="font-size:.7rem;color:var(--text2);margin-bottom:8px">Set each category — optimizer focuses on close/losing ones</div>
      <div id="mt"></div>
    </div>

    <div class="ss">
      <h3>Category Priority</h3>
      <div style="font-size:.7rem;color:var(--text2);margin-bottom:8px">Higher = optimizer values this category more</div>
      <div class="cat-grid" id="cs"></div>
    </div>

    <div class="ss">
      <h3>Today's Games</h3>
      <div id="gl" style="font-size:.73rem"></div>
    </div>
  </div>

  <!-- MAIN -->
  <div class="main">
    <div class="tabs">
      <div class="tab active" onclick="sw('opt',this)">⚡ Optimizer</div>
      <div class="tab" onclick="sw('bat',this)">🏏 Batters</div>
      <div class="tab" onclick="sw('pit',this)">⚾ Pitchers</div>
      <div class="tab" onclick="sw('wv',this)">📋 Waiver Wire</div>
    </div>
    <div class="tc">

      <!-- OPTIMIZER -->
      <div id="tp-opt" class="tp active">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
          <div>
            <h2 style="font-family:'Bebas Neue',sans-serif;font-size:1.3rem;letter-spacing:2px">Daily Recommendations</h2>
            <div style="font-size:.72rem;color:var(--text2)">Start/sit from your roster + best waiver adds for today</div>
          </div>
          <button class="btn btn-s" onclick="runOpt()">⚡ Run Optimizer</button>
        </div>
        <div id="oo"><div class="es"><div class="ic">⚡</div>
          <div>Click <strong>Run Optimizer</strong> to generate today's recommendations</div>
          <div style="margin-top:7px;font-size:.73rem">Set your matchup status (sidebar) for targeted advice</div>
        </div></div>
      </div>

      <!-- BATTERS -->
      <div id="tp-bat" class="tp">
        <div class="filter-row">
          <label><input type="checkbox" id="f-top6" onchange="rB()"> Top order (1-6)</label>
          <label><input type="checkbox" id="f-home" onchange="rB()"> Home batters</label>
          <label><input type="checkbox" id="f-avail" onchange="rB()"> Available only</label>
          <div class="fl-sep"></div>
          <label>Min PA: <input type="number" id="f-minpa" value="3.5" step="0.1" min="0" max="5" style="width:50px;background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:2px 5px;border-radius:3px;font-size:.75rem" onchange="rB()"></label>
          <label>Hand vs:
            <select id="f-hand" onchange="rB()" style="padding:3px 6px;font-size:.72rem">
              <option value="">Any</option>
              <option value="R">vs RHP</option>
              <option value="L">vs LHP</option>
            </select>
          </label>
        </div>
        <div class="ctrls">
          <input type="text" class="sb" placeholder="Search player or team..." id="bs" oninput="rB()">
          <select id="bso" onchange="rB()">
            <option value="score">Fantasy Score</option>
            <option value="Hits">H</option><option value="Runs">R</option>
            <option value="HomeRuns">HR</option><option value="TB">TB</option>
            <option value="SB">SB</option><option value="OBP">OBP</option>
          </select>
          <select id="btf" onchange="rB()"><option value="">All Teams</option></select>
        </div>
        <div style="overflow-x:auto">
          <table class="pt"><thead><tr>
            <th>Score</th><th>Player</th><th>Status</th><th>Team</th><th>Opp</th><th>Pos</th>
            <th onclick="sBs('Hits')">H ↕</th><th onclick="sBs('Runs')">R ↕</th>
            <th onclick="sBs('HomeRuns')">HR ↕</th><th onclick="sBs('TB')">TB ↕</th>
            <th onclick="sBs('SB')">SB ↕</th><th onclick="sBs('OBP')">OBP ↕</th>
            <th>PA</th><th>K</th><th></th>
          </tr></thead><tbody id="btb"></tbody></table>
        </div>
      </div>

      <!-- PITCHERS -->
      <div id="tp-pit" class="tp">
        <div class="filter-row">
          <label><input type="checkbox" id="f-qs" onchange="rP()"> QS likely (&gt;40%)</label>
          <label><input type="checkbox" id="f-avail-p" onchange="rP()"> Available only</label>
          <div class="fl-sep"></div>
          <label>Min IP: <input type="number" id="f-minip" value="4" step="0.5" min="0" max="9" style="width:45px;background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:2px 5px;border-radius:3px;font-size:.75rem" onchange="rP()"></label>
          <label>Max ERA: <input type="number" id="f-maxera" value="6" step="0.5" min="0" max="10" style="width:45px;background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:2px 5px;border-radius:3px;font-size:.75rem" onchange="rP()"></label>
          <label>Min W%: <input type="number" id="f-minw" value="0" step="5" min="0" max="60" style="width:45px;background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:2px 5px;border-radius:3px;font-size:.75rem" onchange="rP()">%</label>
        </div>
        <div class="ctrls">
          <input type="text" class="sb" placeholder="Search pitcher or team..." id="ps" oninput="rP()">
          <select id="pso" onchange="rP()">
            <option value="score">Fantasy Score</option>
            <option value="Strikeouts">K</option><option value="QualityStart">QS%</option>
            <option value="WinPct">Win%</option><option value="ERA_proj">ERA</option>
            <option value="WHIP_proj">WHIP</option>
          </select>
        </div>
        <div style="overflow-x:auto">
          <table class="pt"><thead><tr>
            <th>Score</th><th>Pitcher</th><th>Status</th><th>Team</th><th>Opp</th><th>H</th><th>IP</th>
            <th onclick="sPs('Strikeouts')">K ↕</th><th onclick="sPs('WinPct')">W% ↕</th>
            <th onclick="sPs('QualityStart')">QS% ↕</th><th onclick="sPs('ERA_proj')">ERA ↕</th>
            <th onclick="sPs('WHIP_proj')">WHIP ↕</th><th></th>
          </tr></thead><tbody id="ptb"></tbody></table>
        </div>
      </div>

      <!-- WAIVER WIRE -->
      <div id="tp-wv" class="tp">
        <div style="margin-bottom:14px">
          <h2 style="font-family:'Bebas Neue',sans-serif;font-size:1.3rem;letter-spacing:2px">Waiver Wire Targets</h2>
          <div style="font-size:.72rem;color:var(--text2)">Players NOT on your roster — best adds for today</div>
        </div>
        <div class="ctrls">
          <select id="wc" onchange="rW()">
            <option value="score">Best Overall</option>
            <option value="HR">HR Upside</option><option value="SB">SB Upside</option>
            <option value="Hits">Hit Volume</option><option value="Runs">Run Producers</option>
            <option value="OBP">High OBP</option><option value="TB">Total Bases</option>
            <option value="K_pit">Strikeout Arms</option><option value="QS">QS Candidates</option>
            <option value="ERA">Low ERA</option><option value="WHIP">Low WHIP</option>
          </select>
          <select id="whand" onchange="rW()">
            <option value="">Any Pitcher Hand</option>
            <option value="R">RHP only</option><option value="L">LHP only</option>
          </select>
        </div>
        <div id="wo"></div>
      </div>

    </div>
  </div>
</div>

<script>
// ============================================================
// EMBEDDED DATA (rebuilt daily by scripts/build.py)
// ============================================================
const AB = {b};
const AP = {p};
const ROSTER_DATA = {r};
const BUILD_DATE = "{build_date}";

// ============================================================
// STATE
// ============================================================
let MR = ROSTER_DATA.players.map((p,i) => ({{...p, id:i}}));
let CW = {{H:5,R:5,HR:7,TB:5,SB:6,OBP:4,K:6,QS:7,W:6,ERA:5,WHIP:5}};

// Matchup status per category: 'winning' | 'losing' | 'close'
let MS = {{H:'close',R:'close',HR:'close',TB:'close',SB:'close',OBP:'close',K:'close',QS:'close',W:'close',ERA:'close',WHIP:'close'}};

// ============================================================
// SCORING
// ============================================================
function bScore(b) {{
  const w = CW;
  // Penalize categories where we're already winning (less marginal value)
  const mw = cat => MS[cat]==='winning' ? w[cat]*0.4 : MS[cat]==='losing' ? w[cat]*1.6 : w[cat];
  return (b.Hits*mw('H') + b.Runs*mw('R') + b.HomeRuns*mw('HR')*2 +
          b.TB*mw('TB')*0.5 + b.SB*mw('SB')*1.5 + b.OBP*mw('OBP')*3) / 10;
}}
function pScore(p) {{
  const w = CW;
  const mw = cat => MS[cat]==='winning' ? w[cat]*0.4 : MS[cat]==='losing' ? w[cat]*1.6 : w[cat];
  const eB = Math.max(0,(5-p.ERA_proj))*mw('ERA')*0.3;
  const wB = Math.max(0,(1.5-p.WHIP_proj))*mw('WHIP')*0.5;
  return (p.Strikeouts*mw('K')*0.5 + p.QualityStart*mw('QS')*8 +
          p.WinPct*mw('W')*8 + eB + wB) / 10;
}}
function cs(v,lo,mid,hi){{return v>=hi?'good':v>=mid?'avg':v<=lo?'bad':''}}

// ============================================================
// ROSTER lookup helpers
// ============================================================
function isMyPlayer(name) {{
  return MR.some(r => name.toLowerCase().includes(r.name.toLowerCase()));
}}
function getMyPlayer(name) {{
  return MR.find(r => name.toLowerCase().includes(r.name.toLowerCase()));
}}
function isStarting(name) {{
  const p = getMyPlayer(name);
  return p ? p.start !== false : false;
}}
function rowClass(name) {{
  if (!isMyPlayer(name)) return 'available';
  return isStarting(name) ? 'my-start' : 'my-bench';
}}
function statusTag(name) {{
  if (!isMyPlayer(name)) return `<span class="ta">AVAIL</span>`;
  return isStarting(name) ? `<span class="ts">STARTING</span>` : `<span class="tsi">BENCHED</span>`;
}}
function pitcherHand(pitcher) {{
  // Look up opponent pitcher hand for batter matchup
  const opp = AP.find(p => p.Team === pitcher);
  return opp ? opp.PitcherHand : null;
}}

// ============================================================
// TABS
// ============================================================
function sw(t,el) {{
  document.querySelectorAll('.tp').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
  document.getElementById('tp-'+t).classList.add('active');
  el.classList.add('active');
  if(t==='bat') rB();
  if(t==='pit') rP();
  if(t==='wv')  rW();
}}

// ============================================================
// CATEGORY SLIDERS
// ============================================================
function initCS() {{
  const g = document.getElementById('cs');
  g.innerHTML = Object.keys(CW).map(c => `
    <div class="ci">
      <div class="cl">${{c}} <span class="cv" id="cv-${{c}}">${{CW[c]}}</span></div>
      <input type="range" min="0" max="10" value="${{CW[c]}}"
        oninput="CW['${{c}}']=+this.value;document.getElementById('cv-${{c}}').textContent=this.value">
    </div>`).join('');
}}

// ============================================================
// MATCHUP STATUS
// ============================================================
function initMT() {{
  const el = document.getElementById('mt');
  el.innerHTML = Object.keys(MS).map(c => `
    <div class="mt-cat" id="mtc-${{c}}">
      <span class="mt-label">${{c}}</span>
      <div style="display:flex;gap:4px">
        <button class="btn" style="font-size:.6rem;padding:2px 5px;background:rgba(57,211,83,.2);color:var(--accent3)" onclick="setMS('${{c}}','winning')">W</button>
        <button class="btn" style="font-size:.6rem;padding:2px 5px;background:rgba(251,191,36,.2);color:var(--gold)" onclick="setMS('${{c}}','close')">~</button>
        <button class="btn" style="font-size:.6rem;padding:2px 5px;background:rgba(248,113,113,.2);color:var(--red)" onclick="setMS('${{c}}','losing')">L</button>
      </div>
    </div>`).join('');
}}

function setMS(cat, status) {{
  MS[cat] = status;
  const el = document.getElementById('mtc-'+cat);
  el.className = 'mt-cat ' + (status==='winning'?'winning':status==='losing'?'losing':'close');
}}

// ============================================================
// GAMES SIDEBAR
// ============================================================
function initGames() {{
  const gm = {{}};
  AP.forEach(p => {{
    const k = p.Side==='H' ? p.Opponent+'@'+p.Team : p.Team+'@'+p.Opponent;
    if (!gm[k]) gm[k] = {{
      away: p.Side==='H'?p.Opponent:p.Team,
      home: p.Side==='H'?p.Team:p.Opponent,
      awayP: p.Side==='A'?p.FullName:'',
      homeP: p.Side==='H'?p.FullName:''
    }};
    else {{
      if(p.Side==='A') gm[k].awayP=p.FullName;
      if(p.Side==='H') gm[k].homeP=p.FullName;
    }}
  }});
  document.getElementById('gl').innerHTML = Object.values(gm).map(g =>
    `<div style="padding:4px 0;border-bottom:1px solid var(--border)">
      <div style="display:flex;gap:5px;align-items:center">
        <span style="color:var(--text2)">${{g.away}}</span>
        <span style="color:var(--border)">@</span>
        <span style="font-weight:500">${{g.home}}</span>
      </div>
      <div style="font-size:.62rem;color:var(--text2);margin-top:1px">
        ${{g.awayP||'?'}} vs ${{g.homeP||'?'}}
      </div>
    </div>`).join('');
}}

// ============================================================
// ROSTER SIDEBAR
// ============================================================
function renderRoster() {{
  const el = document.getElementById('rl');
  if (!MR.length) {{
    el.innerHTML='<div style="font-size:.72rem;color:var(--text2);text-align:center;padding:10px">No players in roster.json</div>';
    return;
  }}
  el.innerHTML = MR.map(p => {{
    const match = p.pos.includes('P') || p.pos==='SP'||p.pos==='RP'
      ? AP.find(x=>x.FullName.toLowerCase().includes(p.name.toLowerCase()))
      : AB.find(x=>x.FullName.toLowerCase().includes(p.name.toLowerCase()));
    const sc = match ? (p.pos==='SP'||p.pos==='RP' ? pScore(match) : bScore(match)).toFixed(1) : '—';
    return `<div class="rs ${{p.start===false?'benched':'active'}}">
      <span class="sp-badge">${{p.pos}}</span>
      <div style="flex:1">
        <div style="font-size:.8rem;font-weight:500">${{p.name}}</div>
        <div style="font-size:.62rem;color:var(--text2)">${{p.team}} &nbsp;·&nbsp; Score: <span style="color:var(--accent)">${{sc}}</span></div>
      </div>
      <span style="font-size:.62rem">${{p.start===false?'🪑':'▶'}}</span>
    </div>`;
  }}).join('');
}}

// ============================================================
// TEAM FILTER INIT
// ============================================================
function initTF() {{
  const s = document.getElementById('btf');
  [...new Set(AB.map(b=>b.Team))].sort().forEach(t => {{
    const o = document.createElement('option');
    o.value=t; o.textContent=t; s.appendChild(o);
  }});
}}

// ============================================================
// BATTERS TABLE
// ============================================================
function sBs(f) {{ document.getElementById('bso').value=f; rB(); }}

function rB() {{
  let d = [...AB];
  const sr  = (document.getElementById('bs')?.value||'').toLowerCase();
  const sk  = document.getElementById('bso')?.value||'score';
  const tm  = document.getElementById('btf')?.value||'';
  const t6  = document.getElementById('f-top6')?.checked;
  const hm  = document.getElementById('f-home')?.checked;
  const av  = document.getElementById('f-avail')?.checked;
  const mpa = parseFloat(document.getElementById('f-minpa')?.value||0);
  const hnd = document.getElementById('f-hand')?.value||'';

  if (sr)  d = d.filter(b=>b.FullName.toLowerCase().includes(sr)||b.Team.toLowerCase().includes(sr));
  if (tm)  d = d.filter(b=>b.Team===tm);
  if (t6)  d = d.filter(b=>b.BattingPosition<=6);
  if (hm)  d = d.filter(b=>b.Side==='H');
  if (av)  d = d.filter(b=>!isMyPlayer(b.FullName));
  if (mpa) d = d.filter(b=>b.PlateAppearances>=mpa);
  if (hnd) {{
    // Filter batters facing a specific pitcher hand
    // We need to find what hand the opposing pitcher throws
    const pitHands = {{}};
    AP.forEach(p=>{{ pitHands[p.Team] = p.PitcherHand; }});
    d = d.filter(b => {{
      const oppPitHand = pitHands[b.Opponent];
      return oppPitHand === hnd;
    }});
  }}

  d.sort((a,b) => sk==='score' ? bScore(b)-bScore(a) : b[sk]-a[sk]);

  const mH = Math.max(...d.map(b=>b.Hits), 0.001);
  document.getElementById('btb').innerHTML = d.map(b => {{
    const sc = bScore(b).toFixed(1);
    const rc = rowClass(b.FullName);
    const bw = ((b.Hits/mH)*40).toFixed(0);
    return `<tr class="${{rc}}">
      <td class="sc">${{sc}}</td>
      <td style="font-weight:500;white-space:nowrap">${{b.FullName}}</td>
      <td>${{statusTag(b.FullName)}}</td>
      <td><span class="tb">${{b.Team}}</span></td>
      <td style="color:var(--text2);font-size:.72rem;white-space:nowrap">vs ${{b.Opponent}}</td>
      <td><span class="pb">${{b.BattingPosition}}</span></td>
      <td><div style="display:flex;align-items:center;gap:4px">
        <div style="height:3px;border-radius:2px;background:var(--accent);width:${{bw}}px;min-width:2px"></div>
        <span class="sv ${{cs(b.Hits,.6,.8,1)}}">${{b.Hits.toFixed(3)}}</span>
      </div></td>
      <td class="sv ${{cs(b.Runs,.3,.45,.55)}}">${{b.Runs.toFixed(3)}}</td>
      <td class="sv ${{cs(b.HomeRuns,.08,.13,.18)}}">${{b.HomeRuns.toFixed(3)}}</td>
      <td class="sv ${{cs(b.TB,1,1.4,1.7)}}">${{b.TB.toFixed(3)}}</td>
      <td class="sv ${{cs(b.SB,.01,.05,.12)}}">${{b.SB.toFixed(3)}}</td>
      <td class="sv ${{cs(b.OBP,.28,.33,.38)}}">${{b.OBP.toFixed(3)}}</td>
      <td style="color:var(--text2);font-size:.72rem">${{b.PlateAppearances.toFixed(1)}}</td>
      <td class="sv bad">${{b.Strikeouts.toFixed(1)}}</td>
      <td><button class="btn btn-sm" onclick="quickAdd('${{b.FullName.replace(/'/g,"\\\\'")}}',${{b.Side==='H'?1:0}})">
        ${{isMyPlayer(b.FullName)?'✓':'+ Add'}}
      </button></td>
    </tr>`;
  }}).join('');
}}

// ============================================================
// PITCHERS TABLE
// ============================================================
function sPs(f) {{ document.getElementById('pso').value=f; rP(); }}

function rP() {{
  let d = [...AP];
  const sr   = (document.getElementById('ps')?.value||'').toLowerCase();
  const sk   = document.getElementById('pso')?.value||'score';
  const fqs  = document.getElementById('f-qs')?.checked;
  const fav  = document.getElementById('f-avail-p')?.checked;
  const mip  = parseFloat(document.getElementById('f-minip')?.value||0);
  const mera = parseFloat(document.getElementById('f-maxera')?.value||99);
  const mwp  = parseFloat(document.getElementById('f-minw')?.value||0)/100;

  if (sr)   d = d.filter(p=>p.FullName.toLowerCase().includes(sr)||p.Team.toLowerCase().includes(sr));
  if (fqs)  d = d.filter(p=>p.QualityStart>=0.4);
  if (fav)  d = d.filter(p=>!isMyPlayer(p.FullName));
  if (mip)  d = d.filter(p=>p.Innings>=mip);
  if (mera) d = d.filter(p=>p.ERA_proj<=mera);
  if (mwp)  d = d.filter(p=>p.WinPct>=mwp);

  d.sort((a,b) => {{
    if(sk==='score')    return pScore(b)-pScore(a);
    if(sk==='ERA_proj'||sk==='WHIP_proj') return a[sk]-b[sk];
    return b[sk]-a[sk];
  }});

  document.getElementById('ptb').innerHTML = d.map(p => {{
    const sc = pScore(p).toFixed(1);
    const rc = rowClass(p.FullName);
    return `<tr class="${{rc}}">
      <td class="sc">${{sc}}</td>
      <td style="font-weight:500;white-space:nowrap">${{p.FullName}}</td>
      <td>${{statusTag(p.FullName)}}</td>
      <td><span class="tb">${{p.Team}}</span></td>
      <td style="color:var(--text2);font-size:.72rem;white-space:nowrap">vs ${{p.Opponent}}</td>
      <td><span class="hb">${{p.PitcherHand}}</span></td>
      <td style="font-family:'DM Mono',monospace;font-size:.76rem">${{p.Innings.toFixed(1)}}</td>
      <td class="sv ${{cs(p.Strikeouts,4,6,8)}}">${{p.Strikeouts.toFixed(1)}}</td>
      <td class="sv ${{cs(p.WinPct,.15,.25,.35)}}">${{(p.WinPct*100).toFixed(0)}}%</td>
      <td class="sv ${{cs(p.QualityStart,.2,.35,.5)}}">${{(p.QualityStart*100).toFixed(0)}}%</td>
      <td class="sv ${{cs(5-p.ERA_proj,-2,-.5,.5)}}">${{p.ERA_proj.toFixed(2)}}</td>
      <td class="sv ${{cs(1.5-p.WHIP_proj,-.2,0,.3)}}">${{p.WHIP_proj.toFixed(3)}}</td>
      <td><button class="btn btn-sm" onclick="quickAdd('${{p.FullName.replace(/'/g,"\\\\'")}}',-1)">
        ${{isMyPlayer(p.FullName)?'✓':'+ Add'}}
      </button></td>
    </tr>`;
  }}).join('');
}}

function quickAdd(name, side) {{
  if (!isMyPlayer(name)) {{
    const isPit = AP.some(p=>p.FullName===name);
    MR.push({{name, team:'', pos:isPit?'SP':'OF', start:true, id:Date.now()}});
    renderRoster(); rB(); rP();
  }}
}}

// ============================================================
// WAIVER WIRE
// ============================================================
function rW() {{
  const cat  = document.getElementById('wc')?.value||'score';
  const hand = document.getElementById('whand')?.value||'';
  let bats = AB.filter(b=>!isMyPlayer(b.FullName));
  let pits = AP.filter(p=>!isMyPlayer(p.FullName));
  if (hand) pits = pits.filter(p=>p.PitcherHand===hand);

  let html = '';

  if (['K_pit','QS','ERA','WHIP'].includes(cat)) {{
    pits.sort((a,b) => {{
      if(cat==='K_pit') return b.Strikeouts-a.Strikeouts;
      if(cat==='QS')    return b.QualityStart-a.QualityStart;
      if(cat==='ERA')   return a.ERA_proj-b.ERA_proj;
      if(cat==='WHIP')  return a.WHIP_proj-b.WHIP_proj;
      return pScore(b)-pScore(a);
    }});
    html = '<div class="rs2"><h3>🔥 Top Pitching Adds</h3>';
    html += pits.slice(0,15).map(p => `
      <div class="rc wav">
        <div class="rm">
          <div class="rn">${{p.FullName}} <span class="tb">${{p.Team}}</span> <span class="hb">${{p.PitcherHand}}</span></div>
          <div class="rd">vs ${{p.Opponent}} &nbsp;|&nbsp; ${{p.Innings.toFixed(1)}} IP &nbsp;·&nbsp; ${{p.Strikeouts.toFixed(1)}} K &nbsp;·&nbsp; QS:${{(p.QualityStart*100).toFixed(0)}}% &nbsp;·&nbsp; W:${{(p.WinPct*100).toFixed(0)}}% &nbsp;·&nbsp; ERA:${{p.ERA_proj.toFixed(2)}} &nbsp;·&nbsp; WHIP:${{p.WHIP_proj.toFixed(3)}}</div>
        </div>
        <div class="rsc">${{pScore(p).toFixed(1)}}</div>
      </div>`).join('');
    html += '</div>';
  }} else {{
    const sf = {{score:bScore,HR:b=>b.HomeRuns,SB:b=>b.SB,Hits:b=>b.Hits,Runs:b=>b.Runs,OBP:b=>b.OBP,TB:b=>b.TB}}[cat]||bScore;
    bats.sort((a,b)=>sf(b)-sf(a));
    html = '<div class="rs2"><h3>🔥 Top Batting Adds</h3>';
    html += bats.slice(0,20).map(b => `
      <div class="rc wav">
        <div class="rm">
          <div class="rn">${{b.FullName}} <span class="tb">${{b.Team}}</span> <span class="pb">#${{b.BattingPosition}}</span></div>
          <div class="rd">vs ${{b.Opponent}} &nbsp;|&nbsp; H:${{b.Hits.toFixed(3)}} &nbsp;R:${{b.Runs.toFixed(3)}} &nbsp;HR:${{b.HomeRuns.toFixed(3)}} &nbsp;TB:${{b.TB.toFixed(3)}} &nbsp;SB:${{b.SB.toFixed(3)}} &nbsp;OBP:${{b.OBP.toFixed(3)}}</div>
        </div>
        <div class="rsc">${{bScore(b).toFixed(1)}}</div>
      </div>`).join('');
    html += '</div>';
  }}
  document.getElementById('wo').innerHTML = html;
}}

// ============================================================
// OPTIMIZER
// ============================================================
function runOpt() {{
  const sB = [...AB].map(b=>({{...b,score:bScore(b)}})).sort((a,b)=>b.score-a.score);
  const sP = [...AP].map(p=>({{...p,score:pScore(p)}})).sort((a,b)=>b.score-a.score);

  // My players matched to data
  const myBat = MR.filter(r=>!['SP','RP'].includes(r.pos)).map(r=>{{
    const m=AB.find(b=>b.FullName.toLowerCase().includes(r.name.toLowerCase()));
    return m?{{...m,start:r.start!==false,rosterPos:r.pos}}:null;
  }}).filter(Boolean);
  const myPit = MR.filter(r=>['SP','RP'].includes(r.pos)).map(r=>{{
    const m=AP.find(p=>p.FullName.toLowerCase().includes(r.name.toLowerCase()));
    return m?{{...m,start:r.start!==false,rosterPos:r.pos}}:null;
  }}).filter(Boolean);

  // Start/sit scoring
  const bSS = myBat.map(b=>{{
    const sc=bScore(b);
    const rank=sB.findIndex(x=>x.PlayerId===b.PlayerId)+1;
    const pct=rank/sB.length;
    const action=pct<0.15?'START':pct<0.45?'CONSIDER':'SIT';
    return{{...b,score:sc,rank,action}};
  }});
  const pSS = myPit.map(p=>{{
    const sc=pScore(p);
    const rank=sP.findIndex(x=>x.PlayerId===p.PlayerId)+1;
    const pct=rank/sP.length;
    const action=pct<0.25?'START':pct<0.55?'CONSIDER':'SIT';
    return{{...p,score:sc,rank,action}};
  }});

  // Top waiver targets
  const rn=MR.map(r=>r.name.toLowerCase()).filter(Boolean);
  const wB=sB.filter(b=>!rn.some(n=>b.FullName.toLowerCase().includes(n))).slice(0,5);
  const wP=sP.filter(p=>!rn.some(n=>p.FullName.toLowerCase().includes(n))).slice(0,5);

  // Category leaders today
  const tH  = sB[0];
  const tHR = [...sB].sort((a,b)=>b.HomeRuns-a.HomeRuns)[0];
  const tSB = [...sB].sort((a,b)=>b.SB-a.SB)[0];
  const tO  = [...sB].sort((a,b)=>b.OBP-a.OBP)[0];
  const tK  = sP[0];
  const tQ  = [...sP].sort((a,b)=>b.QualityStart-a.QualityStart)[0];

  let html = '';

  // --- Category leaders ---
  html += `<div class="rs2"><h3>📊 Today's Category Leaders</h3>
    <div class="sg">
      ${{[[tH,'H',tH.Hits.toFixed(3)+' H','Hit Machine'],
          [tHR,'HR',tHR.HomeRuns.toFixed(3)+' HR','HR Threat'],
          [tSB,'SB',tSB.SB.toFixed(3)+' SB','Speedster'],
          [tO,'OBP',tO.OBP.toFixed(3),'Plate Patience'],
          [tK,'K',tK.Strikeouts.toFixed(1)+' K','Swing & Miss'],
          [tQ,'QS',(tQ.QualityStart*100).toFixed(0)+'%','Quality Start']
        ].map(([x,c,v,d])=>`<div class="sc2"><div class="cat">${{c}}</div><div class="val">${{v}}</div>
          <div class="dsc" style="color:var(--text)">${{x.FullName}}</div>
          <div class="dsc">${{x.Team}} vs ${{x.Opponent}}</div>
        </div>`).join('')}}
    </div></div>`;

  // --- Start / Sit ---
  if (bSS.length || pSS.length) {{
    html += `<div class="rs2"><h3>🎯 Start / Sit — Your Roster</h3>`;
    [...bSS,...pSS].sort((a,b)=>b.score-a.score).forEach(x=>{{
      const tc = x.action==='START'?'ts':x.action==='SIT'?'tsi':'tw';
      const rc = x.action==='START'?'str':x.action==='SIT'?'sit':'';
      const ip = 'ERA_proj' in x;
      const dt = ip
        ? `vs ${{x.Opponent}} · ${{x.Innings.toFixed(1)}} IP · ${{x.Strikeouts.toFixed(1)}} K · QS:${{(x.QualityStart*100).toFixed(0)}}% · W:${{(x.WinPct*100).toFixed(0)}}% · ERA:${{x.ERA_proj.toFixed(2)}} · WHIP:${{x.WHIP_proj.toFixed(3)}}`
        : `Bat #${{x.BattingPosition}} vs ${{x.Opponent}} · H:${{x.Hits.toFixed(3)}} R:${{x.Runs.toFixed(3)}} HR:${{x.HomeRuns.toFixed(3)}} TB:${{x.TB.toFixed(3)}} SB:${{x.SB.toFixed(3)}} OBP:${{x.OBP.toFixed(3)}}`;
      html += `<div class="rc ${{rc}}"><div class="rm">
        <div class="rn"><span class="${{tc}}">${{x.action}}</span> &nbsp;${{x.FullName}} <span class="tb">${{x.Team}}</span> <span style="font-size:.65rem;color:var(--text2)">#${{x.rank}} overall</span></div>
        <div class="rd">${{dt}}</div>
      </div><div class="rsc">${{x.score.toFixed(1)}}</div></div>`;
    }});
    html += '</div>';
  }}

  // --- Waiver adds ---
  html += `<div class="rs2"><h3>🔥 Top Waiver Wire Adds Today</h3>`;
  wB.forEach(b=>{{
    html+=`<div class="rc wav"><div class="rm">
      <div class="rn"><span class="tw">BATTER</span> &nbsp;${{b.FullName}} <span class="tb">${{b.Team}}</span> <span class="pb">#${{b.BattingPosition}}</span></div>
      <div class="rd">vs ${{b.Opponent}} · H:${{b.Hits.toFixed(3)}} R:${{b.Runs.toFixed(3)}} HR:${{b.HomeRuns.toFixed(3)}} TB:${{b.TB.toFixed(3)}} SB:${{b.SB.toFixed(3)}} OBP:${{b.OBP.toFixed(3)}}</div>
    </div><div class="rsc">${{b.score.toFixed(1)}}</div></div>`;
  }});
  wP.forEach(p=>{{
    html+=`<div class="rc wav"><div class="rm">
      <div class="rn"><span class="tw">PITCHER</span> &nbsp;${{p.FullName}} <span class="tb">${{p.Team}}</span> <span class="hb">${{p.PitcherHand}}</span></div>
      <div class="rd">vs ${{p.Opponent}} · ${{p.Innings.toFixed(1)}} IP · ${{p.Strikeouts.toFixed(1)}} K · QS:${{(p.QualityStart*100).toFixed(0)}}% · W:${{(p.WinPct*100).toFixed(0)}}% · ERA:${{p.ERA_proj.toFixed(2)}} · WHIP:${{p.WHIP_proj.toFixed(3)}}</div>
    </div><div class="rsc">${{p.score.toFixed(1)}}</div></div>`;
  }});
  html += '</div>';

  document.getElementById('oo').innerHTML = html;
}}

// ============================================================
// INIT
// ============================================================
document.addEventListener('DOMContentLoaded', () => {{
  initCS();
  initMT();
  initGames();
  renderRoster();
  initTF();
  rB();
  rP();
}});
</script>
</body>
</html>'''

    template.write(header)
    template.write(script_start)

def main():
    build_date = datetime.now().strftime("%B %d, %Y")
    print(f"BallparkPal Fantasy Optimizer — Build: {build_date}")

    print("Loading Excel files...")
    df_batters  = load_excel("BallparkPal_Batters.xlsx")
    df_pitchers = load_excel("BallparkPal_Pitchers.xlsx")

    if df_batters is None or df_pitchers is None:
        print("ERROR: Missing required Excel files. Place them in /data and re-run.")
        sys.exit(1)

    print(f"  Batters:  {len(df_batters)} rows")
    print(f"  Pitchers: {len(df_pitchers)} rows")

    print("Processing data...")
    batters_json  = process_batters(df_batters)
    pitchers_json = process_pitchers(df_pitchers)
    roster        = load_roster()

    print(f"Building index.html...")
    html = build_html(batters_json, pitchers_json, roster, build_date)
    with open(OUTPUT_FILE, 'w') as f:
        f.write(html)

    size_kb = len(html) / 1024
    print(f"  Done — {size_kb:.0f} KB written to index.html")
    print(f"  {len(batters_json)} batters, {len(pitchers_json)} pitchers embedded")

if __name__ == "__main__":
    main()
