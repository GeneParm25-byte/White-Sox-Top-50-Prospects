import json
import re
import requests
import time
from pathlib import Path

PLAYER_IDS_FILE = "player_ids.json"
HTML_FILE       = "index.html"
SEASON          = 2026
MLB_API         = "https://statsapi.mlb.com/api/v1"

BAT_RE = re.compile(
    r'g:[\d.null]+,ab:[\d.null]+,ba:[\d.null]+,obp:[\d.null]+'
    r',slg:[\d.null]+,ops:[\d.null]+,hr:[\d.null]+,rbi:[\d.null]+,sb:[\d.null]+'
)
PIT_RE = re.compile(
    r'era:[\d.null]+,ip:[\d.null]+,g:[\d.null]+,so:[\d.null]+'
    r',bb:[\d.null]+,whip:[\d.null]+'
)

def fetch_json(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"    warning: API error: {e}")
        return None

def get_player_stats(mlb_id, season):
    url = f"{MLB_API}/people/{mlb_id}/stats"
    for sport_id in [11, 12, 13, 14, 16, 1]:
        data = fetch_json(url, {
            "stats": "season", "season": season,
            "sportId": sport_id, "group": "hitting,pitching"
        })
        if not data or not data.get("stats"):
            continue
        bat, pit = _parse_stats(data["stats"])
        if bat and int(bat.get("atBats", 0) or 0) < 1:
            bat = {}
        try:
            ip_val = float(pit.get("inningsPitched", 0) or 0)
        except (ValueError, TypeError):
            ip_val = 0
        if pit and ip_val < 0.1:
            pit = {}
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
    if field in ("avg", "ba", "obp", "slg", "ops", "whip", "era"):
        return f"{f:.3f}"
    if field == "ip":
        return f"{f:.1f}"
    return str(int(f))

def build_bat_str(s):
    result = (
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
    print(f"    -> Writing: {result}")
    return result

def build_pit_str(s):
    result = (
        f"era:{fmt(s.get('era'),'era')},"
        f"ip:{fmt(s.get('inningsPitched'),'ip')},"
        f"g:{fmt(s.get('gamesPlayed'),'g')},"
        f"so:{fmt(s.get('strikeOuts'),'so')},"
        f"bb:{fmt(s.get('baseOnBalls'),'bb')},"
        f"whip:{fmt(s.get('whip'),'whip')}"
    )
    print(f"    -> Writing: {result}")
    return result

def update_player_in_html(html, name, bat, pit):
    name_str = f'name:"{name}"'
    name_idx = html.find(name_str)
    if name_idx < 0:
        print(f"    MISS: '{name}' not found in HTML")
        return html, False

    next_name_idx = html.find('name:"', name_idx + len(name_str))
    if next_name_idx < 0:
        next_name_idx = len(html)

    section = html[name_idx:next_name_idx]
    changed = False

    if bat:
        new_bat = build_bat_str(bat)
        # Show what we're replacing
        m = BAT_RE.search(section)
        if m:
            print(f"    -> Replacing: {m.group()}")
        else:
            print(f"    -> WARNING: no bat pattern found in section (len={len(section)})")
        new_section, n = BAT_RE.subn(new_bat, section, count=1)
        if n:
            section = new_section
            changed = True

    if pit:
        new_pit = build_pit_str(pit)
        m = PIT_RE.search(section)
        if m:
            print(f"    -> Replacing: {m.group()}")
        else:
            print(f"    -> WARNING: no pit pattern found in section (len={len(section)})")
        new_section, n = PIT_RE.subn(new_pit, section, count=1)
        if n:
            section = new_section
            changed = True

    if not changed:
        return html, False

    return html[:name_idx] + section + html[next_name_idx:], True

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

        html, changed = update_player_in_html(
            html, name,
            bat if bat else None,
            pit if pit else None
        )

        if changed:
            updated += 1
            print(f"    -> SUCCESS")
        else:
            print(f"    -> WARNING: nothing updated")
            no_match += 1

        time.sleep(0.25)

    if html != original:
        Path(HTML_FILE).write_text(html, encoding="utf-8")
        print(f"\nDone. Updated: {updated} | No stats: {skipped} | Pattern miss: {no_match}")
    else:
        print(f"\nNo changes. Updated: {updated} | No stats: {skipped} | Pattern miss: {no_match}")
    print("=" * 60)

if __name__ == "__main__":
    main()
