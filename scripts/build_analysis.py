"""Build a position-balanced Top 30 FPL analysis dataset."""
from __future__ import annotations

import csv
import json
import math
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAYERS_FILE = ROOT / "data" / "players.json"
OUTPUT_FILE = ROOT / "data" / "analysis.json"
VAASAV_DATA = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data/{season}/cleaned_players.csv"
SEASONS = ["2022-23", "2023-24", "2024-25"]
# Current FPL element_type is numeric: 1=GK, 2=DEF, 3=MID, 4=FWD.
POSITION_MAP = {"1": "GK", "2": "DEF", "3": "MID", "4": "FWD", "GK": "GK", "DEF": "DEF", "MID": "MID", "FWD": "FWD", "GKP": "GK"}
TOP30_QUOTA = {"GK": 4, "DEF": 10, "MID": 10, "FWD": 6}
WEIGHTS = {
    "GK": {"history": 0.30, "current": 0.20, "value": 0.15, "fixture": 0.15, "minutes": 0.15, "availability": 0.05, "role": 0.08},
    "DEF": {"history": 0.25, "current": 0.20, "value": 0.15, "fixture": 0.15, "minutes": 0.10, "availability": 0.05, "defence": 0.10},
    "MID": {"history": 0.25, "current": 0.20, "value": 0.15, "fixture": 0.15, "minutes": 0.10, "availability": 0.05, "attack": 0.10},
    "FWD": {"history": 0.25, "current": 0.20, "value": 0.15, "fixture": 0.15, "minutes": 0.10, "availability": 0.05, "attack": 0.10},
}


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "fpl-squad-planner/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8")


def fnum(row: dict, key: str) -> float:
    try:
        value = row.get(key)
        if value in (None, "", "None"):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def pct_rank(values: list[float], value: float) -> float:
    clean = [v for v in values if math.isfinite(v)]
    if not clean:
        return 0.0
    return 100.0 * sum(v <= value for v in clean) / len(clean)


def norm_inverse(values: list[float], value: float) -> float:
    return 100.0 - pct_rank(values, value)


def load_historical() -> dict[str, list[dict]]:
    history: dict[str, list[dict]] = defaultdict(list)
    for season in SEASONS:
        try:
            text = fetch_text(VAASAV_DATA.format(season=season))
        except Exception as exc:
            print(f"Warning: could not fetch {season}: {exc}", file=sys.stderr)
            continue
        for row in csv.DictReader(text.splitlines()):
            position = POSITION_MAP.get((row.get("element_type") or "").strip().upper())
            if not position:
                continue
            name = " ".join([(row.get("first_name") or "").strip(), (row.get("second_name") or "").strip()]).strip().lower()
            if name:
                row["season"] = season
                row["position"] = position
                history[name].append(row)
    return history


def name_key(player: dict) -> str:
    return " ".join([str(player.get("first_name") or "").strip(), str(player.get("second_name") or "").strip()]).strip().lower()


def recent_history(rows: list[dict]) -> dict:
    by_season = {r["season"]: r for r in rows}
    season_weights = {"2024-25": 0.5, "2023-24": 0.3, "2022-23": 0.2}
    total_w = sum(w for s, w in season_weights.items() if s in by_season)
    if not total_w:
        return {"points": 0.0, "ppm": 0.0, "minutes": 0.0, "goals": 0.0, "assists": 0.0, "clean_sheets": 0.0}

    def avg(field: str) -> float:
        return sum(fnum(by_season[s], field) * w for s, w in season_weights.items() if s in by_season) / total_w

    minutes = avg("minutes")
    points = avg("total_points")
    return {"points": points, "ppm": points / max(minutes / 90.0, 1.0), "minutes": minutes, "goals": avg("goals_scored"), "assists": avg("assists"), "clean_sheets": avg("clean_sheets")}


def build() -> None:
    current = json.loads(PLAYERS_FILE.read_text(encoding="utf-8"))
    players = current.get("players", [])
    teams = {int(t["id"]): t for t in current.get("teams", []) if "id" in t}
    fixtures = []
    fixtures_file = ROOT / "data" / "fixtures.json"
    if fixtures_file.exists():
        fixtures = json.loads(fixtures_file.read_text(encoding="utf-8")).get("fixtures", [])
    events = current.get("events", [])
    selected_gw = next((e["id"] for e in events if e.get("is_next")), None) or next((e["id"] for e in events if e.get("is_current")), 1)
    history = load_historical()

    candidates = []
    for p in players:
        pos = POSITION_MAP.get(str(p.get("element_type")).strip().upper())
        if pos:
            candidates.append({"raw": p, "pos": pos, "history": recent_history(history.get(name_key(p), []))})

    by_pos = defaultdict(list)
    for c in candidates:
        by_pos[c["pos"]].append(c)

    for pos, group in by_pos.items():
        fixture_avgs = {}
        for c in group:
            team_id = int(c["raw"].get("team") or 0)
            upcoming = [f for f in fixtures if f.get("event") is not None and f.get("event") >= selected_gw and (f.get("team_h") == team_id or f.get("team_a") == team_id)]
            upcoming.sort(key=lambda f: f.get("event") or 999)
            diffs = []
            for fx in upcoming[:5]:
                home = fx.get("team_h") == team_id
                diffs.append(fnum(fx, "team_h_difficulty" if home else "team_a_difficulty"))
            fixture_avgs[c["raw"]["id"]] = sum(diffs) / len(diffs) if diffs else 3.0

        pools = {
            "history": [c["history"]["points"] for c in group],
            "current": [fnum(c["raw"], "form") for c in group],
            "value": [fnum(c["raw"], "total_points") / max(fnum(c["raw"], "now_cost") / 10.0, 1.0) for c in group],
            "fixture": list(fixture_avgs.values()),
            "minutes": [c["history"]["minutes"] for c in group],
        }

        for c in group:
            p = c["raw"]
            hist = c["history"]
            fixture_avg = fixture_avgs.get(p["id"], 3.0)
            chance = p.get("chance_of_playing_next_round")
            availability = 100.0 if chance in (None, "") else max(0.0, min(100.0, fnum(p, "chance_of_playing_next_round")))
            parts = {
                "history": pct_rank(pools["history"], hist["points"]),
                "current": pct_rank(pools["current"], fnum(p, "form")),
                "value": pct_rank(pools["value"], fnum(p, "total_points") / max(fnum(p, "now_cost") / 10.0, 1.0)),
                "fixture": norm_inverse(pools["fixture"], fixture_avg),
                "minutes": pct_rank(pools["minutes"], hist["minutes"]),
                "availability": availability,
            }
            if pos == "GK":
                role_values = [x["history"]["clean_sheets"] for x in group]
                parts["role"] = pct_rank(role_values, hist["clean_sheets"])
            elif pos == "DEF":
                role_values = [x["history"]["clean_sheets"] + x["history"]["goals"] * 2 + x["history"]["assists"] for x in group]
                parts["defence"] = pct_rank(role_values, hist["clean_sheets"] + hist["goals"] * 2 + hist["assists"])
            else:
                role_values = [x["history"]["goals"] * 2 + x["history"]["assists"] for x in group]
                parts["attack"] = pct_rank(role_values, hist["goals"] * 2 + hist["assists"])

            weights = WEIGHTS[pos]
            score = sum(parts[k] * w for k, w in weights.items()) / sum(weights.values())
            confidence = "High" if hist["minutes"] >= 2000 and len(history.get(name_key(p), [])) >= 2 else "Medium" if hist["minutes"] >= 800 else "Low"
            reasons = []
            if parts["history"] >= 75: reasons.append("Strong multi-season output")
            elif parts["history"] >= 55: reasons.append("Solid historical output")
            if parts["current"] >= 75: reasons.append("Excellent current form")
            elif parts["current"] >= 60: reasons.append("Positive recent form")
            if parts["value"] >= 75: reasons.append("Strong points-per-£m value")
            if parts["fixture"] >= 75: reasons.append("Favourable next-5 fixture run")
            elif parts["fixture"] <= 30: reasons.append("Difficult fixture run")
            if parts["minutes"] >= 75: reasons.append("Reliable minutes profile")
            if availability < 100: reasons.append(f"{int(availability)}% next-GW chance")
            if not reasons: reasons.append("Balanced across form, history and fixtures")

            team_name = teams.get(int(p.get("team") or 0), {}).get("short_name", "—")
            c["analysis"] = {
                "score": round(score, 1), "confidence": confidence, "team": team_name,
                "price": round(fnum(p, "now_cost") / 10.0, 1), "form": round(fnum(p, "form"), 1),
                "points": int(fnum(p, "total_points")), "historical_points": round(hist["points"], 1),
                "historical_minutes": int(hist["minutes"]), "value": round(fnum(p, "total_points") / max(fnum(p, "now_cost") / 10.0, 1.0), 2),
                "fixture_avg": round(fixture_avg, 2), "availability": int(availability), "reasons": reasons[:3],
            }

    final = []
    for pos, quota in TOP30_QUOTA.items():
        role_players = [c for c in candidates if c["pos"] == pos and "analysis" in c]
        role_players.sort(key=lambda c: c["analysis"]["score"], reverse=True)
        for position_rank, c in enumerate(role_players[:quota], 1):
            p, a = c["raw"], c["analysis"]
            final.append({"rank": 0, "position_rank": position_rank, "id": p.get("id"), "first_name": p.get("first_name"), "second_name": p.get("second_name"), "web_name": p.get("web_name", p.get("second_name")), "position": pos, **a})
    final.sort(key=lambda x: x["score"], reverse=True)
    for rank, item in enumerate(final, 1): item["rank"] = rank

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Vaastav Fantasy-Premier-League historical cleaned_players.csv + current FPL snapshot",
        "historical_seasons": SEASONS, "top30_quota": TOP30_QUOTA, "position_ratio": "2:5:5:3", "weights": WEIGHTS,
        "selection_notes": ["Top 30 is position-balanced to 4 GK, 10 DEF, 10 MID, 6 FWD.", "Scores are position-relative decision-support scores, not official FPL projections.", "Historical seasons are weighted 50% 2024-25, 30% 2023-24 and 20% 2022-23 when available.", "Historical xP/ep fields are intentionally excluded because of potential lookahead bias."],
        "players": final,
    }
    OUTPUT_FILE.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"Built {len(final)} Top 30 candidates: " + ", ".join(f"{p}={sum(1 for x in final if x['position']==p)}" for p in TOP30_QUOTA))


if __name__ == "__main__":
    build()
