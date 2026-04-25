import json
import re
import requests
import time
from pathlib import Path

HTML_FILE = "cwsox_prospects_2026_v15.html"
SEASON    = 2026
MLB_API   = "https://statsapi.mlb.com/api/v1"

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
        print(f"    warning: {e}")
        return None

def get_player_stats(mlb_id):
    url = f"{MLB_API}/people/{mlb_id}/stats"
    for sport_id in [1, 11, 12, 13, 14, 16]:
        data = fetch_json(url, {"stats": "season", "season": SEASON,
                                "sportId": sport_id, "group": "hitting,pitching"})
        if not data or not data.get("stats"):
            continue
        bat, pit = {}, {}
        for group in data["stats"]:
            gtype = group.get("group", {}).get("displayName", "")
            splits = group.get("splits", [])
            if not splits:
                continue
            s = splits[0].get("stat", {})
            if gtype == "hitting":
                bat = s
            elif gtype == "pitching":
                pit = s
        if bat and int(bat.get("atBats", 0) or 0) < 1:
            bat = {}
        try:
            ip_val = float(pit.get("inningsPitched", 0) or 0)
        except (ValueError, TypeError):
            ip_val = 0
        if pit and ip_val < 0.1:
            pit = {}
        if bat or pit:
            level = {1:"MLB",11:"AAA",12:"AA",13:"A+",14:"A",16:"CPX"}.get(sport_id, str(sport_id))
            print(f"    -> Level: {level}")
            return bat, pit
    return {}, {}

def fmt(val, field):
    if val is None or val == "":
        return "null"
    try:
        f = float(val)
    except (ValueError, TypeError):
        return "null"
    if field in ("avg","ba","obp","slg","ops","whip","era"):
        return f"{f:.3f}"
    if field == "ip":
        return f"{f:.1f}"
    return str(int(f))

def build_bat_str(s):
    return (f"g:{fmt(s.get('gamesPlayed'),'g')},ab:{fmt(s.get('atBats'),'ab')},"
            f"ba:{fmt(s.get('avg'),'ba')},obp:{fmt(s.get('obp'),'obp')},"
            f"slg:{fmt(s.get('slg'),'slg')},ops:{fmt(s.get('ops'),'ops')},"
            f"hr:{fmt(s.get('homeRuns'),'hr')},rbi:{fmt(s.get('rbi'),'rbi')},"
            f"sb:{fmt(s.get('stolenBases'),'sb')}")

def build_pit_str(s):
    return (f"era:{fmt(s.get('era'),'era')},ip:{fmt(s.get('inningsPitched'),'ip')},"
            f"g:{fmt(s.get('gamesPlayed'),'g')},so:{fmt(s.get('strikeOuts'),'so')},"
            f"bb:{fmt(s.get('baseOnBalls'),'bb')},whip:{fmt(s.get('whip'),'whip')}")

def update_player(html, name, bat, pit):
    name_str = f'name:"{name}"'
    idx = html.find(name_str)
    if idx < 0:
        print(f"    MISS: '{name}' not in HTML")
        return html, False
    nxt = html.find('name:"', idx + len(name_str))
    if nxt < 0:
        nxt = len(html)
    section = html[idx:nxt]
    changed = False
    if bat:
        new_section, n = BAT_RE.subn(build_bat_str(bat), section, count=1)
        if n:
            section = new_section
            changed = True
    if pit:
        new_section, n = PIT_RE.subn(build_pit_str(pit), section, count=1)
        if n:
            section = new_section
            changed = True
    return html[:idx] + section + html[nxt:], changed

def main():
    print("=" * 60)
    print(f"CWS Prospects Stat Updater  |  Season {SEASON}")
    print("=" * 60)

    player_ids = json.loads(Path("player_ids.json").read_text())
    html = Path(HTML_FILE).read_text(encoding="utf-8")
    original = html
    updated = skipped = no_match = 0

    for name, mlb_id in player_ids.items():
        print(f"\n  {name} (ID {mlb_id})")
        if mlb_id is None:
            print(f"    -> No MLBAM ID yet, skipping")
            skipped += 1
            continue
        bat, pit = get_player_stats(mlb_id)
        if not bat and not pit:
            print(f"    -> No {SEASON} stats yet")
            skipped += 1
            continue
        html, changed = update_player(html, name, bat or None, pit or None)
        if changed:
            updated += 1
            print(f"    -> SUCCESS")
        else:
            print(f"    -> WARNING: nothing updated")
            no_match += 1
        time.sleep(0.25)

    if html != original:
        Path(HTML_FILE).write_text(html, encoding="utf-8")
        print(f"\nSaved -> {HTML_FILE}")

    print(f"\nDone. Updated:{updated}  No stats:{skipped}  Pattern miss:{no_match}")
    print("=" * 60)

if __name__ == "__main__":
    main()
