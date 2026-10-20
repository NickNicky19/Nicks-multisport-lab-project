"""Manual post-event NBA source normalization and statistical grading.

The CLI owns capture/import clocks, never requests a future outcome, and only
operates on genuine issued forecasts bound to one retained pregame input record.
This is forecast grading, not provider ticket settlement. No scheduler is added.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from time import monotonic
import urllib.request

from .integrity import IntegrityError, digest, read_receipt, stamp, utc, write_receipt
from .ledger import Ledger, LedgerRef
from .nba_data import NBAPlayerGame, COUNT_FIELDS, _strict_json, audit_rows, parse_minutes

NORMALIZER_VERSION = "espn-nba-selected-outcomes-v1"
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_SOURCE_SECONDS = 30
LABELS = {"MIN", "FG", "3PT", "FT", "OREB", "DREB", "REB", "AST", "TO", "STL", "BLK", "PTS"}


def _now():
    return datetime.now(timezone.utc)


def _id(value, name):
    if type(value) is not str or not re.fullmatch(r"[1-9][0-9]*", value):
        raise IntegrityError(f"{name} requires an explicit numeric source ID")
    return value


def _count(value, label):
    if type(value) is not str or not re.fullmatch(r"[0-9]+", value):
        raise IntegrityError(f"{label} requires a complete integer count")
    return int(value)


def _pair(value, label):
    if type(value) is not str or not re.fullmatch(r"[0-9]+-[0-9]+", value):
        raise IntegrityError(f"{label} requires explicit made-attempted counts")
    return tuple(int(x) for x in value.split("-"))


def _event_identity(body, event):
    if (event.get("id_namespace"), event.get("league"), event.get("status")) != ("espn", "NBA", "PRE_GAME"):
        raise IntegrityError("expected event must preserve the original pregame NBA identity")
    if event.get("event_version") != digest({k: v for k, v in event.items() if k != "event_version"}):
        raise IntegrityError("original pregame event version is inconsistent")
    header = body.get("header", {})
    if type(header) is not dict:
        raise IntegrityError("summary header must be an object")
    if _id(header.get("id"), "header event") != event["event_id"]:
        raise IntegrityError("summary event differs from issued event")
    competitions = header.get("competitions")
    if type(competitions) is not list or len(competitions) != 1:
        raise IntegrityError("summary requires one complete event competition")
    competition = competitions[0]
    if type(competition) is not dict:
        raise IntegrityError("summary competition must be an object")
    if _id(competition.get("id"), "competition") != event["event_id"]:
        raise IntegrityError("summary competition differs from issued event")
    if stamp(utc(competition["date"])) != event["event_starts_at"]:
        raise IntegrityError("summary start differs from issued event; reschedule needs separate handling")
    if header.get("date") is not None and stamp(utc(header["date"])) != event["event_starts_at"]:
        raise IntegrityError("summary header and competition starts conflict")
    season = header.get("season", {})
    if type(season) is not dict:
        raise IntegrityError("summary season must be explicit")
    if (season.get("year"), str(season.get("type"))) != (event["season_ending_year"], event["season_type"]):
        raise IntegrityError("summary season differs from issued event")
    competitors = competition.get("competitors")
    if type(competitors) is not list or len(competitors) != 2:
        raise IntegrityError("summary must identify both issued teams")
    teams = {}
    for side in competitors:
        if type(side) is not dict or type(side.get("team")) is not dict:
            raise IntegrityError("summary competitors require explicit team objects")
        team = _id(side.get("team", {}).get("id"), "team")
        if side.get("id") != team or side.get("homeAway") not in {"home", "away"}:
            raise IntegrityError("summary team/competitor identity conflict")
        if side["homeAway"] in teams:
            raise IntegrityError("duplicate summary team side")
        teams[side["homeAway"]] = team
    if teams != {"home": event["home_team_id"], "away": event["away_team_id"]}:
        raise IntegrityError("summary teams differ from issued event")
    status = competition.get("status", header.get("status", {}))
    if type(status) is not dict or type(status.get("type")) is not dict:
        raise IntegrityError("summary requires an explicit event status")
    if header.get("status") is not None and header["status"] != status:
        raise IntegrityError("summary event statuses conflict")
    return competition, status


def normalize_summary(raw: bytes, event: dict, candidates: list[dict], *, observed_at: datetime) -> dict:
    """Bind retained bytes to selected final rows; a missing row remains pending.

    This pure parser's observed_at is the capture receipt clock, not an upstream
    update time. The production CLI obtains it from its own actual HTTP capture.
    Unrecognized source shape fails closed; no final-source validation is claimed
    from the synthetic regression fixtures alone.
    """
    if type(raw) is not bytes or not raw or len(raw) > MAX_SOURCE_BYTES:
        raise IntegrityError("summary bytes are empty or exceed the bounded source budget")
    imported = _now()
    observed = utc(observed_at)
    if observed > imported or observed < utc(event["event_starts_at"]):
        raise IntegrityError("outcome observation must follow event start and precede import")
    body = _strict_json(raw.decode("utf-8"))
    if type(body) is not dict:
        raise IntegrityError("summary must be a JSON object")
    competition, status = _event_identity(body, event)
    selected = {}
    if type(candidates) is not list or not 1 <= len(candidates) <= 1000:
        raise IntegrityError("bounded explicit selected-player cohort is required")
    teams = {event["home_team_id"], event["away_team_id"]}
    for candidate in candidates:
        if type(candidate) is not dict:
            raise IntegrityError("selected player must have an explicit identity object")
        pid = _id(candidate.get("player_id"), "selected athlete")
        if pid in selected or {candidate.get("team_id"), candidate.get("opponent_id")} != teams:
            raise IntegrityError("selected player identity is duplicated or conflicts with event teams")
        selected[pid] = candidate
    result = {"normalizer_version": NORMALIZER_VERSION, "event_id": event["event_id"],
              "pregame_event_version": event["event_version"], "source_raw_sha256": hashlib.sha256(raw).hexdigest(),
              "source_observed_at": stamp(observed), "source_updated_at": None,
              "normalized_at": stamp(imported), "rows": {}, "pending": [], "status": "PENDING"}
    state = status.get("type", {})
    if (state.get("name"), state.get("state"), state.get("completed")) != ("STATUS_FINAL", "post", True):
        result["pending"] = [{"player_id": p, "reason": "EVENT_NOT_VERIFIED_FINAL"} for p in selected]
        return result
    period = status.get("period")
    if type(period) is not int or period < 4:
        raise IntegrityError("final event requires an explicit complete NBA period count")
    for side in competition["competitors"]:
        scores = side.get("linescores")
        if scores is not None and (type(scores) is not list or len(scores) != period):
            raise IntegrityError("final period count conflicts with team period scores")
    result["outcome_event_version"] = digest({"event_id": event["event_id"], "pregame_event_version": event["event_version"],
                                             "status": "FINAL", "final_periods": period})
    boxscore = body.get("boxscore", {})
    if type(boxscore) is not dict:
        raise IntegrityError("summary boxscore must be an object")
    player_groups = boxscore.get("players", [])
    if type(player_groups) is not list or len(player_groups) > 2:
        raise IntegrityError("unrecognized full-game player boxscore shape")
    seen_teams, seen_players = set(), set()
    for team_group in player_groups:
        if type(team_group) is not dict or type(team_group.get("team")) is not dict:
            raise IntegrityError("player boxscore requires explicit team objects")
        team = _id(team_group.get("team", {}).get("id"), "boxscore team")
        if team not in teams or team in seen_teams:
            raise IntegrityError("boxscore team is duplicated or differs from issued teams")
        seen_teams.add(team)
        groups = team_group.get("statistics")
        if type(groups) is not list or len(groups) != 1:
            raise IntegrityError("one explicit full-game player-statistics group is required")
        group = groups[0]
        if type(group) is not dict:
            raise IntegrityError("player statistics group must be an object")
        if any(k in group for k in ("period", "periodNumber", "quarter", "half")):
            raise IntegrityError("period-specific statistics cannot grade a full-game forecast")
        if re.search(r"quarter|half|period", str(group.get("displayName", "")), re.IGNORECASE):
            raise IntegrityError("period-specific statistics cannot grade a full-game forecast")
        if group.get("name") not in (None, "athletes", "Athletes"):
            raise IntegrityError("unrecognized player-statistics group")
        labels = group.get("labels")
        if (type(labels) is not list or not all(type(x) is str for x in labels)
                or len(set(labels)) != len(labels) or not LABELS <= set(labels)):
            raise IntegrityError("full-game statistics require unique explicit primitive labels")
        athletes = group.get("athletes")
        if type(athletes) is not list or len(athletes) > 100:
            raise IntegrityError("bounded explicit athlete rows are required")
        for athlete in athletes:
            if type(athlete) is not dict or type(athlete.get("athlete")) is not dict:
                raise IntegrityError("boxscore athlete requires an explicit identity object")
            pid = _id(athlete.get("athlete", {}).get("id"), "boxscore athlete")
            if pid in seen_players:
                raise IntegrityError("duplicate athlete in final summary")
            seen_players.add(pid)
            if pid not in selected:
                continue
            candidate = selected[pid]
            if candidate["team_id"] != team:
                raise IntegrityError("selected athlete is assigned to a different final team")
            supplied_team = athlete["athlete"].get("team")
            if supplied_team is not None and supplied_team.get("id") != team:
                raise IntegrityError("athlete-level final team conflicts with boxscore team")
            values = athlete.get("stats")
            if type(values) is not list:
                raise IntegrityError("selected athlete stats must be an explicit list")
            dnp = athlete.get("didNotPlay")
            if type(dnp) is not bool:
                result["pending"].append({"player_id": pid, "reason": "PARTICIPATION_NOT_EXPLICIT"})
                continue
            if dnp:
                placeholders = {None, "", "--", "DNP", "DND", "0", "0.0", "0:00", "0-0", "+0"}
                if any(type(v) not in (str, type(None)) or v not in placeholders for v in values):
                    raise IntegrityError("explicit DNP contradicts supplied production")
                row = NBAPlayerGame(id_namespace="espn", event_id=event["event_id"], player_id=pid,
                    team_id=team, opponent_id=candidate["opponent_id"], season_ending_year=event["season_ending_year"],
                    season_type=event["season_type"], event_start=utc(event["event_starts_at"]),
                    participation="DNP", minutes=None, minutes_precision="unknown",
                    **dict.fromkeys(COUNT_FIELDS), final_status="FINAL", final_periods=period)
            else:
                if len(values) != len(labels):
                    raise IntegrityError("selected appearance is missing statistic values")
                line = dict(zip(labels, values))
                fgm, fga = _pair(line["FG"], "FG")
                fg3m, fg3a = _pair(line["3PT"], "3PT")
                ftm, fta = _pair(line["FT"], "FT")
                minute_text = line["MIN"]
                if type(minute_text) is str and re.fullmatch(r"[0-9]+", minute_text):
                    minutes, precision = float(minute_text), "rounded_whole_minutes"
                else:
                    minutes, precision = parse_minutes(minute_text, encoding="clock"), "seconds"
                    if minutes is None:
                        raise IntegrityError("appearance has no verified minutes")
                row = NBAPlayerGame(id_namespace="espn", event_id=event["event_id"], player_id=pid,
                    team_id=team, opponent_id=candidate["opponent_id"], season_ending_year=event["season_ending_year"],
                    season_type=event["season_type"], event_start=utc(event["event_starts_at"]),
                    participation="APPEARED", minutes=minutes, minutes_precision=precision,
                    points=_count(line["PTS"], "PTS"), fgm=fgm, fga=fga, fg2m=fgm-fg3m,
                    fg3m=fg3m, fg3a=fg3a, ftm=ftm, fta=fta, oreb=_count(line["OREB"], "OREB"),
                    dreb=_count(line["DREB"], "DREB"), rebounds=_count(line["REB"], "REB"),
                    assists=_count(line["AST"], "AST"), turnovers=_count(line["TO"], "TO"),
                    blocks=_count(line["BLK"], "BLK"), steals=_count(line["STL"], "STL"),
                    final_status="FINAL", final_periods=period)
                if audit_rows([row])["identity_failures"]:
                    raise IntegrityError("selected appearance contradicts scoring/rebound/attempt identities")
            result["rows"][pid] = row
    existing = set(result["rows"]) | {x["player_id"] for x in result["pending"]}
    result["pending"].extend({"player_id": p, "reason": "SELECTED_ATHLETE_MISSING_FROM_FINAL_BOXSCORE"}
                             for p in selected if p not in existing)
    result["status"] = "FINAL_COMPLETE_SELECTED_COHORT" if not result["pending"] else "FINAL_PARTIAL_SELECTED_COHORT"
    return result


def _semantic_outcome(row):
    if row.participation == "DNP":
        return "DNP", None
    fields = {"FGM": "fgm", "FG2M": "fg2m", "FG3M": "fg3m", "FTM": "ftm", "PTS": "points",
              "REB": "rebounds", "AST": "assists", "TOV": "turnovers", "BLK": "blocks", "STL": "steals"}
    return "FINAL_APPEARANCE", {k: getattr(row, v) for k, v in fields.items()}


def _ref(payload):
    return LedgerRef(payload["kind"], payload["record_id"], digest(payload))


def persist_grades(store: Ledger, forecasts: dict[str, list[LedgerRef]], normalized: dict,
                   *, correction_reason: str | None = None) -> dict:
    """Persist statistical outcomes/grades with restart-safe original source clocks.

    Fresh captures with unchanged statistical outcomes reuse the original records.
    A changed line needs an explicit reason and correction links. This helper also
    works for reconstructed statistical tests; CLI selection requires actual R1.
    """
    if correction_reason is not None and (type(correction_reason) is not str or not correction_reason.strip()):
        raise IntegrityError("outcome corrections require an explicit reason")
    index = store.scan()
    superseded = store._correction_map(index)
    plans = []
    for player, row in normalized["rows"].items():
        if player not in forecasts:
            continue
        if (not isinstance(row, NBAPlayerGame) or row.final_status != "FINAL"
                or row.participation not in {"APPEARED", "DNP"}
                or row.event_id != normalized["event_id"] or row.player_id != player
                or not normalized["status"].startswith("FINAL_")):
            raise IntegrityError("statistical persistence requires a normalized selected final outcome")
        semantic = _semantic_outcome(row)
        matching, differing = [], []
        for payload in index["outcomes"].values():
            ref = _ref(payload)
            body = payload["data"].get("outcome")
            if body is None or ref in superseded:
                continue
            identity = (body["event_id"], body["player_id"], body["event_starts_at"], body["team_id"], body["opponent_id"])
            if identity != (row.event_id, row.player_id, stamp(row.event_start), row.team_id, row.opponent_id):
                continue
            (matching if (body["status"], body["primitives"]) == semantic else differing).append(ref)
        if len(matching) > 1 or len(differing) > 1:
            raise IntegrityError("ambiguous existing outcome revisions require explicit manual reconciliation")
        if differing and correction_reason is None:
            raise IntegrityError("changed source outcome requires an explicit correction reason")
        for forecast_ref in forecasts[player]:
            bundle = store.read(forecast_ref)["data"]["bundle"]
            if (bundle["event_id"], bundle["player_id"], bundle["event_starts_at"], bundle["team_id"], bundle["opponent_id"]) != (
                    row.event_id, row.player_id, stamp(row.event_start), row.team_id, row.opponent_id):
                raise IntegrityError("selected outcome differs from issued forecast identity")
        plans.append((player, row, matching, differing))
    results = []
    for player, row, matching, differing in plans:
        outcome_ref = matching[0] if matching else store.record_outcome(
            row, source_evidence_sha256=normalized["source_raw_sha256"],
            source_observed_at=utc(normalized["source_observed_at"]))
        if differing:
            store.correct(differing[0], outcome_ref, reason=correction_reason)
        grade_refs = []
        for forecast_ref in forecasts[player]:
            grade_ref = store.grade_forecast(forecast_ref, outcome_ref)
            # Recover an interrupted outcome correction/regrade without replacing
            # original grade clocks or double-counting an obsolete outcome.
            current = store.scan()
            mapping = store._correction_map(current)
            for payload in current["grades"].values():
                old_ref = _ref(payload)
                if old_ref == grade_ref or old_ref in mapping:
                    continue
                deps = [LedgerRef.from_record(x) for x in payload["references"]]
                old_forecast = next((x for x in deps if x.kind == "forecasts"), None)
                old_outcome = next((x for x in deps if x.kind == "outcomes"), None)
                if (old_forecast == forecast_ref and old_outcome is not None and old_outcome != outcome_ref
                        and store.latest(old_outcome) == outcome_ref):
                    store.correct(old_ref, grade_ref, reason=correction_reason or "Statistical regrade following explicit outcome correction")
            grade_body = store.read(grade_ref)["data"]["grade"]
            grade_refs.append({"reference": grade_ref.to_record(), "forecast_reference": forecast_ref.to_record(),
                               "graded_at": grade_body["graded_at"], "status": grade_body["status"]})
        original = store.read(outcome_ref)["data"]["outcome"]
        results.append({"player_id": player, "outcome_reference": outcome_ref.to_record(),
                        "source_observed_at": original["observed_at"],
                        "source_evidence_sha256": original["source_evidence_sha256"],
                        "reused_original_outcome": bool(matching), "grades": grade_refs})
    report = {"schema_version": "nba-prospective-grading-report-v1", "recorded_at": stamp(_now()),
              "normalizer_version": NORMALIZER_VERSION, "event_id": normalized["event_id"],
              "pregame_event_version": normalized["pregame_event_version"],
              "fresh_capture": {k: normalized[k] for k in ("source_raw_sha256", "source_observed_at", "source_updated_at", "normalized_at")},
              "selected_normalized_rows": [row.to_record() for row in normalized["rows"].values()],
              "pending": normalized["pending"], "results": results,
              "financial_settlement": "NOT_EVALUATED", "qualification": "UNAVAILABLE",
              "persistence_status": "LOCAL_RECEIPT_ONLY_REQUIRES_COMMIT_PUSH_READBACK"}
    verify_report(store, report)
    return report


def verify_report(store: Ledger, report: dict) -> None:
    """Check per-record original clocks against actual referenced ledger records."""
    if (report.get("schema_version") != "nba-prospective-grading-report-v1"
            or report.get("normalizer_version") != NORMALIZER_VERSION
            or report.get("financial_settlement") != "NOT_EVALUATED"
            or report.get("qualification") != "UNAVAILABLE"):
        raise IntegrityError("invalid statistical grading report identity or status")
    capture = report["fresh_capture"]
    if not (utc(capture["source_observed_at"]) <= utc(capture["normalized_at"]) <= utc(report["recorded_at"])):
        raise IntegrityError("grading report source/import clocks conflict")
    if "input_record_id" in report:
        view, _ = issued_context(store, report["input_record_id"], report["event_id"])
        if report["pregame_event_version"] != view["event"]["event_version"]:
            raise IntegrityError("grading report differs from original pregame event version")
    rows = {}
    for record in report["selected_normalized_rows"]:
        row = NBAPlayerGame(**{k: v for k, v in record.items() if k != "game_duration_minutes"})
        if row.player_id in rows or row.event_id != report["event_id"]:
            raise IntegrityError("grading report has conflicting selected outcome identities")
        rows[row.player_id] = row
    for result in report["results"]:
        outcome_ref = LedgerRef.from_record(result["outcome_reference"])
        outcome = store.read(outcome_ref)["data"]["outcome"]
        if outcome["event_id"] != report["event_id"]:
            raise IntegrityError("grading report differs from original outcome event")
        row = rows.get(result["player_id"])
        if row is None or _semantic_outcome(row) != (outcome["status"], outcome["primitives"]):
            raise IntegrityError("grading report normalized row differs from referenced outcome")
        if (row.id_namespace, row.event_id, row.player_id, stamp(row.event_start), row.team_id, row.opponent_id) != (
                outcome["id_namespace"], outcome["event_id"], outcome["player_id"], outcome["event_starts_at"],
                outcome["team_id"], outcome["opponent_id"]):
            raise IntegrityError("grading report normalized row differs from exact outcome identity")
        if (result["player_id"], result["source_observed_at"], result["source_evidence_sha256"]) != (
                outcome["player_id"], outcome["observed_at"], outcome["source_evidence_sha256"]):
            raise IntegrityError("grading report differs from original outcome source clocks or identity")
        if type(result["reused_original_outcome"]) is not bool or utc(outcome["observed_at"]) > utc(capture["source_observed_at"]):
            raise IntegrityError("grading report reuse state or fresh/original clocks conflict")
        if not result["reused_original_outcome"] and (
                outcome["observed_at"] != capture["source_observed_at"]
                or outcome["source_evidence_sha256"] != capture["source_raw_sha256"]):
            raise IntegrityError("new outcome must bind the actual fresh source capture")
        for item in result["grades"]:
            grade_ref = LedgerRef.from_record(item["reference"])
            forecast_ref = LedgerRef.from_record(item["forecast_reference"])
            payload = store.read(grade_ref)
            grade = payload["data"]["grade"]
            if (grade["graded_at"], grade["status"]) != (item["graded_at"], item["status"]):
                raise IntegrityError("grading report differs from original grade clock or status")
            if payload["references"] != [forecast_ref.to_record(), outcome_ref.to_record()]:
                raise IntegrityError("grading report differs from exact grade dependencies")


def issued_context(store: Ledger, input_record_id: str, event_id: str):
    """Select only active actual R1 forecasts bound to the exact original pack."""
    if not re.fullmatch(r"[a-f0-9]{64}", input_record_id):
        raise IntegrityError("an exact retained input record ID is required")
    _id(event_id, "requested event")
    index = store.scan()
    payload = index["research_inputs"].get(input_record_id)
    if payload is None:
        raise IntegrityError("retained pregame input record is missing")
    from .pregame_sources import binding_view
    pack = payload["data"]["source_pack"]
    view = binding_view(pack)
    # The small issuance binding omits season/namespace/status. Outcome source
    # normalization needs the complete validated original event, not that subset.
    view = {**view, "event": dict(pack["event"])}
    if view["event"]["event_id"] != event_id:
        raise IntegrityError("requested event differs from retained input record")
    active_ids = {x["forecast_id"] for x in store.iter_active_forecasts()}
    forecasts = {}
    for payload in index["forecasts"].values():
        bundle = payload["data"].get("bundle", {})
        if (bundle.get("forecast_id") in active_ids and bundle.get("evidence_lane") == "REAL_TIME_CAPTURED"
                and bundle.get("model_version") == "nba_joint_empirical_pregame_r1_v1"
                and bundle.get("prospective", {}).get("source_pack_record_id") == input_record_id):
            if bundle["prospective"]["event_version"] != view["event"]["event_version"]:
                raise IntegrityError("issued event version differs from retained input identity")
            forecasts.setdefault(bundle["player_id"], []).append(_ref(payload))
    return view, forecasts


def _raw_directory(path: Path) -> Path:
    """Raw providers' responses stay in ignored local storage, never site/Git."""
    path = Path(path).absolute()
    cursor = Path(path.anchor)
    for part in path.parts[1:]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise IntegrityError("raw outcome path or parent cannot be a symlink")
    resolved = path.resolve()
    local = Path(__file__).resolve().parents[1] / ".local-data"
    if not (resolved.is_relative_to(Path("/tmp")) or resolved.is_relative_to(local)):
        raise IntegrityError("raw outcome path must remain under /tmp or this repository's .local-data")
    if resolved.exists() and not resolved.is_dir():
        raise IntegrityError("raw outcome directory must be a directory")
    return resolved


def capture_summary(event: dict, raw_directory: Path) -> tuple[bytes, dict]:
    """One post-start GET with actual clocks; no caller clock or outcome override."""
    if _now() < utc(event["event_starts_at"]):
        raise IntegrityError("outcome source capture is forbidden before event start")
    raw_directory = _raw_directory(raw_directory)
    event_id = _id(event["event_id"], "event")
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={event_id}"
    started = _now()
    tick = monotonic()
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "NicksMultisportLab-bounded-research/1"}), timeout=20) as response:
        raw = response.read(MAX_SOURCE_BYTES + 1)
        if len(raw) > MAX_SOURCE_BYTES:
            raise IntegrityError("outcome source exceeds 8 MiB capture budget")
        observed = _now()
        elapsed = monotonic() - tick
        if not (0 <= elapsed <= MAX_SOURCE_SECONDS and 0 <= (observed-started).total_seconds() <= MAX_SOURCE_SECONDS):
            raise IntegrityError("outcome source capture exceeded its actual 30-second latency budget")
        metadata = {"source_url": url, "http_status": response.status, "content_type": response.headers.get("Content-Type"),
                    "http_date": response.headers.get("Date"), "http_last_modified": response.headers.get("Last-Modified"),
                    "source_updated_at": None,
                    "retrieval_started_at": stamp(started), "observed_at": stamp(observed),
                    "elapsed_seconds": round(elapsed, 6),
                    "raw_sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    if metadata["http_status"] != 200 or "json" not in (metadata["content_type"] or "").lower():
        raise IntegrityError("outcome response is not successful JSON")
    raw_directory = _raw_directory(raw_directory)
    raw_directory.mkdir(parents=True, exist_ok=True)
    _raw_directory(raw_directory)
    raw_path = raw_directory / f"{metadata['raw_sha256']}.raw"
    if raw_path.is_symlink():
        raise IntegrityError("raw outcome source cannot be a symlink")
    if raw_path.exists():
        if raw_path.read_bytes() != raw:
            raise IntegrityError("raw source hash path conflicts")
    else:
        with raw_path.open("xb") as output:
            output.write(raw)
    write_receipt(raw_directory / f"capture-{digest(metadata)}.json", metadata)
    return raw, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", required=True)
    parser.add_argument("--input-record-id", required=True)
    parser.add_argument("--raw-directory", type=Path, default=Path(".local-data/prospective-outcomes"))
    parser.add_argument("--correct-outcomes", action="store_true")
    parser.add_argument("--correction-reason")
    args = parser.parse_args()
    if args.correct_outcomes != (args.correction_reason is not None):
        parser.error("--correct-outcomes and --correction-reason must be supplied together")
    store = Ledger()
    try:
        view, forecasts = issued_context(store, args.input_record_id, args.event)
        if not forecasts or _now() < utc(view["event"]["event_starts_at"]):
            result = {"schema_version": "nba-prospective-grading-status-v1", "checked_at": stamp(_now()),
                      "event_id": args.event, "status": "PENDING", "source_requests": 0,
                      "reason": "NO_ISSUED_FORECASTS" if not forecasts else "EVENT_NOT_STARTED",
                      "next_eligible_source_check_at": view["event"]["event_starts_at"],
                      "outcomes_created": 0, "grades_created": 0, "financial_settlement": "NOT_EVALUATED"}
        else:
            raw, capture = capture_summary(view["event"], args.raw_directory)
            normalized = normalize_summary(raw, view["event"], view["candidates"], observed_at=utc(capture["observed_at"]))
            result = persist_grades(store, forecasts, normalized, correction_reason=args.correction_reason)
            result["input_record_id"] = args.input_record_id
            result["capture_metadata"] = capture
            path = store.root / "evidence" / "data" / f"prospective-outcomes-{digest(result)}.json"
            write_receipt(path, result)
            verify_report(Ledger(store.root), read_receipt(path))
            result = {"report_path": str(path), **result}
        print(json.dumps(result, indent=2))
    except (IntegrityError, ValueError, KeyError, OSError) as error:
        parser.exit(1, f"outcome grading blocked: {error}\n")


if __name__ == "__main__":
    main()
