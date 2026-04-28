# ⚾ BallparkPal Fantasy Optimizer

Daily ESPN H2H fantasy baseball optimizer — auto-rebuilds from BallparkPal projections.

**Live site:** `https://YOUR-USERNAME.github.io/YOUR-REPO-NAME/`

---

## First-Time Setup (5 minutes)

### 1. Create the repo on GitHub
- Go to github.com → New repository
- Name it something like `fantasy-optimizer`
- Set to **Public** (required for free GitHub Pages)
- Don't initialize with README (you'll push these files)

### 2. Upload these files
Using GitHub Desktop or git:
```bash
git init
git remote add origin https://github.com/YOUR-USERNAME/fantasy-optimizer.git
git add .
git commit -m "Initial setup"
git push -u origin main
```

### 3. Enable GitHub Pages
- Go to your repo → Settings → Pages
- Source: **Deploy from branch**
- Branch: `main`, folder: `/ (root)`
- Save — your site will be live at the URL shown

### 4. Update your roster
Edit `roster.json` with your actual players:
```json
{
  "team_name": "My Team",
  "players": [
    { "name": "Ronald Acuña Jr.", "team": "ATL", "pos": "OF", "start": true },
    { "name": "Freddie Freeman",  "team": "LAD", "pos": "1B", "start": true },
    { "name": "Spencer Strider",  "team": "ATL", "pos": "SP", "start": true }
  ]
}
```
- `start: true` = this player is in your starting lineup
- `start: false` = benched / injured list
- Position options: `C`, `1B`, `2B`, `3B`, `SS`, `OF`, `SP`, `RP`, `UTIL`

---

## Daily Workflow

### Every morning:
1. Go to [BallparkPal](https://ballparkpal.com) and download the 4 Excel files:
   - `BallparkPal_Batters.xlsx`
   - `BallparkPal_Pitchers.xlsx`
   - `BallparkPal_Teams.xlsx`
   - `BallparkPal_Games.xlsx`

2. Drop them into the `/data` folder of this repo

3. Either:
   - **Push via GitHub Desktop** → the Action triggers automatically
   - **Wait** → the Action runs at 11am ET anyway if files are already there

4. Open your GitHub Pages URL — it's updated!

### When you add/drop a player:
1. Edit `roster.json`
2. Push the change
3. The Action rebuilds automatically within a minute

---

## Manual Build (run locally)

If you want to test locally:
```bash
pip install pandas openpyxl
python scripts/build.py
open index.html
```

---

## How the Optimizer Works

**Category Priority Sliders** — weight each of the 13 ESPN H2H categories (H, R, HR, TB, SB, OBP, K, QS, W, SV, HD, ERA, WHIP). Higher = optimizer values players who help that category more.

**Matchup Status** — tell the optimizer if you're WINNING, CLOSE, or LOSING each category vs your opponent this week. It automatically:
- Boosts scores for players in categories you're LOSING (1.6x weight)
- Reduces scores for categories you're already WINNING (0.4x weight)
- This focuses recommendations on what you actually need

**Fantasy Score** — composite number combining all weighted categories. Higher = better pickup/start for your specific matchup.

**Start/Sit** — ranks your roster players by today's score and recommends START, CONSIDER, or SIT.

**Waiver Wire** — all players NOT on your roster, sorted by whatever category you need most.

---

## Filters Available

### Batters
| Filter | What it does |
|--------|-------------|
| Top order (1-6) | Only show batters hitting 1st through 6th |
| Home batters | Only batters playing at home today |
| Available only | Hide your roster players (true waiver wire mode) |
| Min PA | Minimum projected plate appearances (e.g., 3.5+) |
| Hand vs | Only batters facing RHP or LHP today |

### Pitchers
| Filter | What it does |
|--------|-------------|
| QS likely (>40%) | Only starters with 40%+ quality start probability |
| Available only | Hide your roster pitchers |
| Min IP | Minimum projected innings (e.g., 5+) |
| Max ERA | Hide pitchers projected over X ERA |
| Min W% | Only pitchers with X% or higher win probability |

---

## File Structure
```
fantasy-optimizer/
├── index.html              ← Built automatically, this is what you view
├── roster.json             ← YOUR PLAYERS — edit this
├── data/
│   ├── BallparkPal_Batters.xlsx    ← Drop daily files here
│   ├── BallparkPal_Pitchers.xlsx
│   ├── BallparkPal_Teams.xlsx
│   └── BallparkPal_Games.xlsx
├── scripts/
│   └── build.py            ← Converts Excel → JSON → HTML
└── .github/
    └── workflows/
        └── daily-build.yml ← Automated daily rebuild
```
