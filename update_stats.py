"""
CWS Prospects Auto-Stat Updater
================================
Pulls 2026 MiLB/MLB stats from the MLB Stats API for all 50 ranked prospects
and updates index.html in place.

Run locally:  python update_stats.py
GitHub Actions runs this automatically on a schedule (see .github/workflows/daily.yml)
"""

import json
import re
import requests
import time
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
PLAYER_IDS_FILE = "player_ids.json"
HTML_FILE       = "index.html"
SEASON          = 2026
MLB_API         = "https://statsapi.mlb.com/api/v1"

# ── API helpers ───────────────────────────────────────────────────────────────
def fetch_json(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  ⚠  API error {url}: {e}")
        return None


def get_player_stats(mlb_id, season):
    """
    Return (bat_stats, pit_stats) dicts for a player's current season.
    Tries each MiLB level first, then falls back to MLB.
    """
    url = f"{MLB_API}/people/{mlb_id}/stats"

    # Try MiLB levels: AAA, AA, A+, A, Rookie
    for sport_id in [11, 12, 13, 14, 16]:
        data = fetch_json(url, {
            "stats": "season",
            "season": season,
            "sportId": sport_id,
            "group": "hitting,pitching"
        })
        if data and data.get("stats"):
            bat, pit = _parse_stats(data["stats"])
            if bat or pit:
                return bat, pit

    # Fall back to MLB
    data = fetch_json(url, {
        "stats": "season",
        "season": season,
        "sportId": 1,
        "group": "hitting,pitching"
    })
    if data and data.get("stats"):
        return _parse_stats(data["stats"])

    return {}, {}


def _parse_stats(stats_list):
    bat, pit = {}, {}
    for group in stats_list:
        gtype = group.get("group", {}).get("displayName", "")
        splits = group.get("splits", [])
        if not splits:
            continue
        s = splits[0].get("stat", {})
        if gtype == "hitting":
            bat = s
        elif gtype == "pitching":
            pit = s
    return bat, pit


def fmt(val, field):
    """Format a stat value for injection into JS."""
    if val is None or val == "":
        return "null"
    try:
        f = float(val)
    except (ValueError, TypeError):
        return "null"
    if field in ("avg", "obp", "slg", "ops", "whip", "era"):
        return f"{f:.3f}"
    if field == "ip":
        return f"{f:.1f}"
    return str(int(f))


def build_bat_str(s):
    return (
        f"g:{fmt(s.get('gamesPlayed'),'g')},"
        f"ab:{fmt(s.get('atBats'),'ab')},"
        f"ba:{fmt(s.get('avg'),'ba')},"
        f"obp:{fmt(s.get('obp'),'obp')},"
        f"slg:{fmt(s.get('slg'),'slg')},"
        f"ops:{fmt(s.get('ops'),'ops')},"
        f"hr:{fmt(s.get('homeRuns'),'hr')},"
        f"rbi:{fmt(s.get('rbi'),'rbi')},"
        f"sb:{fmt(s.get('stolenBases'),'sb')}"
    )


def build_pit_str(s):
    return (
        f"era:{fmt(s.get('era'),'era')},"
        f"ip:{fmt(s.get('inningsPitched'),'ip')},"
        f"g:{fmt(s.get('gamesPlayed'),'g')},"
        f"so:{fmt(s.get('strikeOuts'),'so')},"
        f"bb:{fmt(s.get('baseOnBalls'),'bb')},"
        f"whip:{fmt(s.get('whip'),'whip')}"
    )


def update_player_in_html(html, name, bat, pit):
    """Find the player object by name and replace its stat fields."""
    name_pat = re.escape(f'name:"{name}"')
    m = re.search(name_pat, html)
    if not m:
        print(f"  ✗  '{name}' not found in HTML")
        return html

    idx = m.start()
    # Find the enclosing object
    start_brace = html.rfind('{', max(0, idx - 300), idx)
    depth = 0
    obj_end = start_brace
    for i, ch in enumerate(html[start_brace:], start_brace):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                obj_end = i + 1
                break

    obj = html[start_brace:obj_end]

    if bat:
        new_bat = build_bat_str(bat)
        obj = re.sub(
            r"g:[\d.null]+,ab:[\d.null]+,ba:[\d.null]+,obp:[\d.null]+"
            r",slg:[\d.null]+,ops:[\d.null]+,hr:[\d.null]+,rbi:[\d.null]+,sb:[\d.null]+",
            new_bat, obj, count=1
        )

    if pit:
        new_pit = build_pit_str(pit)
        obj = re.sub(
            r"era:[\d.null]+,ip:[\d.null]+,g:[\d.null]+,so:[\d.null]+"
            r",bb:[\d.null]+,whip:[\d.null]+",
            new_pit, obj, count=1
        )

    return html[:start_brace] + obj + html[obj_end:]


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print(f"CWS Prospects Stat Updater  |  Season {SEASON}")
    print("=" * 60)

    ids_path = Path(PLAYER_IDS_FILE)
    if not ids_path.exists():
        print(f"✗ {PLAYER_IDS_FILE} not found.")
        return

    with open(ids_path) as f:
        player_ids = json.load(f)

    html_path = Path(HTML_FILE)
    if not html_path.exists():
        print(f"✗ {HTML_FILE} not found.")
        return

    html = html_path.read_text(encoding="utf-8")

    updated = 0
    skipped = 0

    for name, mlb_id in player_ids.items():
        print(f"\n  {name} (ID {mlb_id})...")
        bat, pit = get_player_stats(mlb_id, SEASON)

        if not bat and not pit:
            print(f"    → No {SEASON} stats yet")
            skipped += 1
            continue

        if bat:
            avg = bat.get('avg', '---')
            print(f"    → Bat: {bat.get('gamesPlayed','?')}G  "
                  f".{str(round(float(avg)*1000)).zfill(3) if avg != '---' else '---'}  "
                  f"{bat.get('homeRuns','?')}HR  {bat.get('stolenBases','?')}SB")
        if pit:
            print(f"    → Pit: {pit.get('gamesPlayed','?')}G  "
                  f"{pit.get('era','?')} ERA  "
                  f"{pit.get('inningsPitched','?')} IP  "
                  f"{pit.get('strikeOuts','?')}K")

        html = update_player_in_html(html, name, bat if bat else None, pit if pit else None)
        updated += 1
        time.sleep(0.25)

    html_path.write_text(html, encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"Done.  Updated: {updated}  |  Skipped: {skipped}")
    print(f"Saved → {HTML_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
