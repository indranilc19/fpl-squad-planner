"""
Fetches the FPL bootstrap-static payload and writes a trimmed data/players.json
into the repo. Runs on GitHub's servers via the scheduled Action in
.github/workflows/refresh-data.yml — NOT in the user's browser, so the FPL
API's lack of CORS headers for browser origins never comes into play.

The frontend then reads data/players.json as a same-origin static file after
Vercel's Git integration redeploys on the commit this script produces.
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone

API_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
OUTPUT_PATH = "data/players.json"

# Only the fields the app actually renders — keeps the shipped file small.
PLAYER_FIELDS = [
    "id", "first_name", "second_name", "team", "element_type",
    "now_cost", "total_points", "form",
]
TEAM_FIELDS = ["id", "name", "short_name"]


def fetch_bootstrap():
    req = urllib.request.Request(API_URL, headers={"User-Agent": "fpl-squad-planner/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def trim(data):
    players = [{k: p.get(k) for k in PLAYER_FIELDS} for p in data.get("elements", [])]
    teams = [{k: t.get(k) for k in TEAM_FIELDS} for t in data.get("teams", [])]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "players": players,
        "teams": teams,
    }


def main():
    try:
        raw = fetch_bootstrap()
    except Exception as exc:  # noqa: BLE001 - surface any failure to the Action log
        print(f"Failed to fetch FPL data: {exc}", file=sys.stderr)
        sys.exit(1)

    trimmed = trim(raw)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, separators=(",", ":"))

    print(f"Wrote {len(trimmed['players'])} players, {len(trimmed['teams'])} teams to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
