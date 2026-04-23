"""
CWS Prospects Auto-Stat Updater — v14 compatible
=================================================
Pulls 2026 MiLB/MLB stats from the MLB Stats API for all 50 ranked prospects
and updates index.html in place.

Run locally:  python update_stats.py
GitHub Actions runs this on a schedule (see .github/workflows/daily.yml)
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

# Batting stat pattern in index.html:
# g:N,ab:N,ba:N.NNN,obp:N.NNN,slg:N.NNN,ops:N.NNN,hr:N,rbi:N,sb:N
BAT_RE = re.compile(
    r'g:[\d.null]+,ab:[\d.null]+,ba:[\d.null]+,obp:[\d.null]+'
    r',slg:[\d.null]+,ops:[\d.null]+,hr:[\d.null]+,rbi:[\d.null]+,sb:[\d.null]+'
)

# Pitching stat pattern in index.html:
# era:N.NNN,ip:N.N,g:N,so:N,bb:N,whip:N.NNN
PIT_RE = re.compile(
    r'era:[\d.null]+,ip:[\d.null]+,g:[\d.null]+,so:[\d.null]+'
    r',bb:[\d.null]+,whip:[\d.null]+'
)

# ── API helpers ───────────────────────────────────────────────────────────────
def fetch_json(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"    warning  API error: {e}")
        return None


def get_player_stats(mlb_id, season):
    url = f"{MLB_API}/people/{mlb_id}/stats"
    for sport_id in [11, 12, 13, 14, 16, 1]:
        data = fetch_json(url, {
            "stats": "season",
            "season": season,
            "sportId": sport_id,
            "group": "hitting,pitching"
        })
        if not data or not data.get("stats"):
            continue
        bat, pit = _parse_stats(data["stats"])
        if bat or pit:
            return bat, pit
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
    name_str = f'name:"{name}"'
    idx = html.find(name_str)
    if idx < 0:
        print(f"    MISS  '{name}' not found in HTML")
        return html, False

    chunk_end = min(idx + 4000, len(html))
    chunk = html[idx:chunk_end]
    changed = False

    if bat:
        new_bat = build_bat_str(bat)
        new_chunk, n = BAT_RE.subn(new_bat, chunk, count=1)
        if n:
            chunk = new_chunk
            changed = True

    if pit:
        new_pit = build_pit_str(pit)
        new_chunk, n = PIT_RE.subn(new_pit, chunk, count=1)
        if n:
            chunk = new_chunk
            changed = True

    if not changed:
        return html, False

    return html[:idx] + chunk + html[chunk_end:], True


def main():
    print("=" * 60)
    print(f"CWS Prospects Stat Updater  |  Season {SEASON}")
    print("=" * 60)

    with open(PLAYER_IDS_FILE) as f:
        player_ids = json.load(f)

    html = Path(HTML_FILE).read_text(encoding="utf-8")
    original = html
    updated = skipped = no_match = 0

    for name, mlb_id in player_ids.items():
        print(f"\n  {name} (ID {mlb_id})")
        bat, pit = get_player_stats(mlb_id, SEASON)

        if not bat and not pit:
            print(f"    -> No {SEASON} stats yet")
            skipped += 1
            continue

        if bat:
            avg = bat.get('avg', '')
            try:
                avg_fmt = f".{str(round(float(avg)*1000)).zfill(3)}"
            except:
                avg_fmt = "---"
            print(f"    -> Bat: {bat.get('gamesPlayed','?')}G  {avg_fmt}  {bat.get('homeRuns','?')}HR  {bat.get('stolenBases','?')}SB")
        if pit:
            print(f"    -> Pit: {pit.get('gamesPlayed','?')}G  {pit.get('era','?')} ERA  {pit.get('inningsPitched','?')} IP  {pit.get('strikeOuts','?')}K")

        html, changed = update_player_in_html(html, name, bat if bat else None, pit if pit else None)

        if changed:
            updated += 1
        else:
            print(f"    WARNING: stat pattern not found in HTML for {name}")
            no_match += 1

        time.sleep(0.25)

    if html != original:
        Path(HTML_FILE).write_text(html, encoding="utf-8")
        print(f"\nDone. Updated: {updated} | No stats: {skipped} | Pattern miss: {no_match}")
        print(f"Saved -> {HTML_FILE}")
    else:
        print("\nNo changes.")
    print("=" * 60)


if __name__ == "__main__":
    main()
