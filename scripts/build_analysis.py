"""Build a position-balanced Top 30 FPL analysis dataset.

Inputs:
- data/players.json: current FPL snapshot maintained by the existing pipeline.
- Historical cleaned_players.csv files from Vaastav's public FPL dataset.

The engine deliberately avoids the `xP` lookahead field. It combines current
form, historical performance, value, fixture context, minutes reliability and
availability into a transparent position-relative score. The browser consumes
only the compact JSON output in data/analysis.json.
"""
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
POSITION_MAP = {"GK": "GK", "DEF": "DEF", "MID": "MID", "FWD": "FWD", "GKP": "GK"}
# Exact FPL squad slot ratio: 2 GK : 5 DEF : 5 MID : 3 FWD.
# For a Top-30 shortlist this scales to 4 : 10 : 10 : 6.
TOP30_QUOTA = {"GK": 4, "DEF": 10, "MID": 10, "FWD": 6}
WEIGHTS = {
    "GK": {"history": 0.30, "current": 0.20, "value": 0.15, "fixture": 0.15, "minutes": 0.15, "availability": 0.05},
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
    le = sum(v <= value for v in clean)
    return 100.0 * le / len(clean)


def norm_inverse(values: list[float], value: float) -> float:
    # Lower is better; convert to a percentile-like 0-100 score.
    return 100.0 - pct_rank(values, value)


def load_historical() -> dict[str, list[dict]]:
    history: dict[str, list[dict]] = defaultdict(list)
    for season in SEASONS:
        url = VAASAV_DATA.format(season=season)
        try:
            text = fetch_text(url)
        except Exception as exc:
            print(f"Warning: could not fetch {season}: {exc}", file=sys.stderr)
            continue
        reader = csv.DictReader(text.splitlines())
        for row in reader:
            position = POSITION_MAP.get((row.get("element_type") or "").strip().upper())
            if not position:
                continue
            name = " ".join([(row.get("first_name") or "").strip(), (row.get("second_name") or "").strip()]).strip().lower()
            if not name:
                continue
            row["season"] = season
            row["position"] = position
            history[name].append(row)
    return history


def best_name_key(player: dict) -> str:
    return " ".join([str(player.get("first_name") or "").strip(), str(player.get("second_name") or "").strip()]).strip().lower()


def recent_history(rows: list[dict]) -> dict:
    # More recent seasons get higher weight.
    by_season = {r["season"]: r for r in rows}
    season_weights = {"2024-25": 0.5, "2023-24": 0.3, "2022-23": 0.2}
    total_w = sum(w for s, w in season_weights.items() if s in by_season)
    if total_w == 0:
        return {"points": 0.0, "ppm": 0.0, "minutes": 0.0, "goals": 0.0, "assists": 0.0, "clean_sheets": 0.0}

    def avg(field: str) -> float:
        return sum(fnum(by_season[s], field) * w for s, w in season_weights.items() if s in by_season) / total_w

    minutes = avg("minutes")
    points = avg("total_points")
    ppm = points / max(minutes / 90.0, 1.0)
    return {
        "points": points,
        "ppm": ppm,
        "minutes": minutes,
        "goals": avg("goals_scored"),
        "assists": avg("assists"),
        "clean_sheets": avg("clean_sheets"),
    }


def build() -> None:
    current = json.loads(PLAYERS_FILE.read_text(encoding="utf-8"))
    players = current.get("players", [])
    teams = {int(t["id"]): t for t in current.get("teams", []) if "id" in t}
    fixtures_file = ROOT / "data" / "fixtures.json"
    fixtures = []
    if fixtures_file.exists():
        fixtures = json.loads(fixtures_file.read_text(encoding="utf-8")).get("fixtures", [])
    events = current.get("events", [])
    selected_gw = next((e["id"] for e in events if e.get("is_next")), None)
    if selected_gw is None:
        selected_gw = next((e["id"] for e in events if e.get("is_current")), 1)

    history = load_historical()
    candidates = []
    for p in players:
        pos = POSITION_MAP.get(str(p.get("element_type")))
        if not pos:
            continue
        name_key = best_name_key(p)
        h = recent_history(history.get(name_key, []))
        candidates.append({"raw": p, "pos": pos, "history": h})

    # Build position-relative feature pools.
    by_pos = defaultdict(list)
    for c in candidates:
        by_pos[c["pos"]].append(c)

    for pos, group in by_pos.items():
        feature_pools = {
            "history": [c["history"]["points"] for c in group],
            "current": [fnum(c["raw"], "form") for c in group],
            "value": [fnum(c["raw"], "total_points") / max(fnum(c["raw"], "now_cost") / 10.0, 1.0) for c in group],
            "fixture": [],
            "minutes": [c["history"]["minutes"] for c in group],
        }

        fixture_avgs = {}
        for c in group:
            team_id = int(c["raw"].get("team") or 0)
            upcoming = [f for f in fixtures if f.get("event") is not None and f.get("event") >= selected_gw and (f.get("team_h") == team_id or f.get("team_a") == team_id)]
            upcoming.sort(key=lambda f: f.get("event") or 999)
            upcoming = upcoming[:5]
            diffs = []
            for fx in upcoming:
                if fx.get("team_h") == team_id:
                    diffs.append(fnum(fx, "team_h_difficulty"))
                else:
                    diffs.append(fnum(fx, "team_a_difficulty"))
            fixture_avgs[c["raw"]["id"]] = (sum(diffs) / len(diffs)) if diffs else 3.0
        feature_pools["fixture"] = list(fixture_avgs.values())

        for c in group:
            p = c["raw"]
            current_form = fnum(p, "form")
            current_ppg = fnum(p, "total_points") / max(fnum(p, "minutes") / 90.0, 1.0)
            value = fnum(p, "total_points") / max(fnum(p, "now_cost") / 10.0, 1.0)
            hist = c["history"]
            fixture_avg = fixture_avgs.get(p["id"], 3.0)
            chance = p.get("chance_of_playing_next_round")
            availability = 100.0 if chance in (None, "") else max(0.0, min(100.0, fnum(p, "chance_of_playing_next_round")))
            minutes_score = pct_rank(feature_pools["minutes"], hist["minutes"])
            parts = {
                "history": pct_rank(feature_pools["history"], hist["points"]),
                "current": pct_rank(feature_pools["current"], current_form),
                "value": pct_rank(feature_pools["value"], value),
                "fixture": norm_inverse(feature_pools["fixture"], fixture_avg),
                "minutes": minutes_score,
                "availability": availability,
            }
            if pos == "GK":
                parts["role"] = pct_rank([c2["history"]["clean_sheets"] for c2 in group], hist["clean_sheets"])
            elif pos == "DEF":
                role_val = hist["clean_sheets"] + hist["goals"] * 2 + hist["assists"]
                parts["defence"] = pct_rank([c2["history"]["clean_sheets"] + c2["history"]["goals"] * 2 + c2["history"]["assists"] for c2 in group], role_val)
            else:
                role_val = hist["goals"] * 2 + hist["assists"]
                parts["attack"] = pct_rank([c2["history"]["goals"] * 2 + c2["history"]["assists"] for c2 in group], role_val)

            weights = dict(WEIGHTS[pos])
            if pos == "GK":
                weights["history"] *= 0.92
                weights["role"] = 0.08
            weighted = sum(parts[k] * w for k, w in weights.items()) / sum(weights.values())
            confidence = "High" if hist["minutes"] >= 2000 and len(history.get(best_name_key(p), [])) >= 2 else "Medium" if hist["minutes"] >= 800 else "Low"

            next_fx = []
            team_name = teams.get(int(p.get("team") or 0), {}).get("short_name", "—")
            for fx in sorted([f for f in fixtures if f.get("event") is not None and f.get("event") >= selected_gw and (f.get("team_h") == p.get("team") or f.get("team_a") == p.get("team"))], key=lambda x: x.get("event") or 999)[:5]:
                home = fx.get("team_h") == p.get("team")
                opp = fx.get("team_a") if home else fx.get("team_h")
                next_fx.append({"gw": fx.get("event"), "opponent": teams.get(int(opp or 0), {}).get("short_name", "—"), "home": home, "difficulty": int(fx.get("team_h_difficulty") if home else fx.get("team_a_difficulty"))})

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

            candidates[candidates.index(c)]["analysis"] = {
                "score": round(weighted, 1),
                "confidence": confidence,
                "team": team_name,
                "price": round(fnum(p, "now_cost") / 10.0, 1),
                "form": round(current_form, 1),
                "points": int(fnum(p, "total_points")),
                "historical_points": round(hist["points"], 1),
                "historical_minutes": int(hist["minutes"]),
                "value": round(value, 2),
                "fixture_avg": round(fixture_avg, 2),
                "availability": int(availability),
                "next_fixtures": next_fx,
                "reasons": reasons[:3],
            }

    final = []
    for pos, quota in TOP30_QUOTA.items():
        role_players = [c for c in candidates if c["pos"] == pos and "analysis" in c]
        role_players.sort(key=lambda c: c["analysis"]["score"], reverse=True)
        for rank, c in enumerate(role_players[:quota], start=1):
            p = c["raw"]
            a = c["analysis"]
            final.append({
                "rank": 0,
                "position_rank": rank,
                "id": p.get("id"),
                "first_name": p.get("first_name"),
                "second_name": p.get("second_name"),
                "web_name": p.get("web_name", p.get("second_name")),
                "position": pos,
                **a,
            })

    final.sort(key=lambda x: x["score"], reverse=True)
    for idx, item in enumerate(final, start=1):
        item["rank"] = idx

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Vaastav Fantasy-Premier-League historical cleaned_players.csv + current FPL snapshot",
        "historical_seasons": SEASONS,
        "top30_quota": TOP30_QUOTA,
        "position_ratio": "2:5:5:3",
        "weights": WEIGHTS,
        "selection_notes": [
            "Top 30 is position-balanced to the legal FPL squad ratio: 4 GK, 10 DEF, 10 MID, 6 FWD.",
            "Scores are position-relative percentiles, not official FPL projections.",
            "Historical data is weighted 50% 2024-25, 30% 2023-24, 20% 2022-23 when seasons are available.",
            "Vaastav's xP/ep fields are intentionally not used because the repository warns about potential lookahead bias in scraped xP.",
        ],
        "players": final,
    }
    OUTPUT_FILE.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(final)} players to {OUTPUT_FILE}")


if __name__ == "__main__":
    build()
