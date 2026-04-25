import re
import requests
import time
from pathlib import Path

HTML_FILE = "cwsox_prospects_2026_v15.html"

PLAYER_IDS = {
    "Noah Schultz":           702273,
    "Braden Montgomery":      695731,
    "Caleb Bonemer":          815352,
    "Hagen Smith":            696146,
    "Billy Carlson":          815814,
    "Christian Oppor":        803291,
    "Sam Antonacci":          803011,
    "William Bergolla Jr.":   703151,
    "Jaden Fauske":           828262,
    "Samuel Zavala":          694214,
    "Javier Mogollon":        808684,
    "Kyle Lodise":            827517,
    "George Wolkow":          805804,
    "Blake Larson":           820836,
    "Mathias LaCombe":        807187,
    "Jeral Perez":            800419,
    "Landon Hodge":           821933,
    "Alexander Albertus":     800316,
    "Jacob Gonzalez":         694378,
    "Wikelman González":      682790,
    "Shane Murphy":           690294,
    "Mason Adams":            690279,
    "Drew Thorpe":            689672,
    "Drew Romo":              691011,
    "Anthony DePino":         834962,
    "Colby Shelton":          701333,
    "Riley Gowens":           803035,
    "David Sandlin":          689818,
    "Ryan Burrowes":          802018,
    "Nick McLain":            695607,
    "Ky Bush":                681066,
    "Jairo Iriarte":          683568,
    "Lucas Gordon":           690981,
    "Justin Sinibaldi":       811958,
    "Grant Umberger":         802359,
    "Duncan Davitt":          701474,
    "Tyler Schweitzer":       805326,
    "Frankeli Arias":         802087,
    "Gabe Davis":             805031,
    "Juan Carela":            683636,
    "Luis Reyes":             501760,
    "Rikuu Nishida":          807747,
    "Aldrin Batista":         702881,
    "Tanner McDougal":        701780,
    "Eduardo Herrera":        815901,
    "Alejandro Cruz":         829078,
    "Yobal Rodriguez":        830034,
    "Christian Gonzalez":     822619,
    # Signed Jan 2026 — no MLBAM ID assigned yet
    "Sebastian Romero":       None,
    "Fernando Graterol":      None,
}
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
    # Search from MLB (1) down through all MiLB levels
    for sport_id in [1, 11, 12, 13, 14, 16]:
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
            level = {1: "MLB", 11: "AAA", 12: "AA", 13: "A+", 14: "A", 16: "CPX"}.get(sport_id, str(sport_id))
            print(f"    -> Level: {level}")
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
    g   = fmt(s.get('gamesPlayed'), 'g')
    ab  = fmt(s.get('atBats'), 'ab')
    ba  = fmt(s.get('avg'), 'ba')
    obp = fmt(s.get('obp'), 'obp')
    slg = fmt(s.get('slg'), 'slg')
    ops = fmt(s.get('ops'), 'ops')
    hr  = fmt(s.get('homeRuns'), 'hr')
    rbi = fmt(s.get('rbi'), 'rbi')
    sb  = fmt(s.get('stolenBases'), 'sb')
    result = f"g:{g},ab:{ab},ba:{ba},obp:{obp},slg:{slg},ops:{ops},hr:{hr},rbi:{rbi},sb:{sb}"
    print(f"    -> Bat: {g}G  {ba}  {hr}HR  {sb}SB")
    print(f"    -> Writing: {result}")
    return result

def build_pit_str(s):
    era  = fmt(s.get('era'), 'era')
    ip   = fmt(s.get('inningsPitched'), 'ip')
    g    = fmt(s.get('gamesPlayed'), 'g')
    so   = fmt(s.get('strikeOuts'), 'so')
    bb   = fmt(s.get('baseOnBalls'), 'bb')
    whip = fmt(s.get('whip'), 'whip')
    result = f"era:{era},ip:{ip},g:{g},so:{so},bb:{bb},whip:{whip}"
    print(f"    -> Pit: {g}G  {era} ERA  {ip} IP  {so}K")
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

    html = Path(HTML_FILE).read_text(encoding="utf-8")
    original = html
    updated = skipped = no_match = 0

    for name, mlb_id in PLAYER_IDS.items():
        print(f"\n  {name} (ID {mlb_id})")
        if mlb_id is None:
            print(f"    -> No MLBAM ID yet, skipping")
            skipped += 1
            continue
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
        print(f"\nSaved -> {HTML_FILE}")

    print(f"\nDone. Updated: {updated} | No stats: {skipped} | Pattern miss: {no_match}")
    print("=" * 60)

if __name__ == "__main__":
    main()
