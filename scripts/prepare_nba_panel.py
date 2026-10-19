#!/usr/bin/env python3
"""Prepare the audited reconstructed NBA panel offline; never score forecasts.

Optional PyArrow is imported only while reading explicit local Parquet inputs.
Normal application and software-test execution do not require that dependency.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from multisport_lab.nba_data import (  # noqa: E402
    COUNT_FIELDS, NBAPlayerGame, audit_rows, normalize_sdv_rows, with_sdv_schedule,
)

MAX_ASSET_BYTES = 2 * 1024 * 1024
MAX_ROWS = 40_000
MAX_DECODED_BYTES = 128 * 1024 * 1024
STANDARD_TEAMS = frozenset(str(value) for value in range(1, 31))
BLOCKED_OUTPUT_PARTS = {"web", "output", "evidence"}


def validate_output_path(path: Path) -> Path:
    """Keep raw normalized source rows outside normal Git and Pages paths."""
    expanded = path.expanduser().absolute()
    resolved = expanded.resolve()
    if BLOCKED_OUTPUT_PARTS.intersection(expanded.parts) or BLOCKED_OUTPUT_PARTS.intersection(resolved.parts):
        raise ValueError("normalized source rows cannot be written under web, output or evidence")
    if not (resolved.is_relative_to(Path("/tmp")) or resolved.is_relative_to(ROOT / ".local-data")):
        raise ValueError("output must be under /tmp or this repository's ignored .local-data")
    if expanded.is_symlink() or resolved.exists():
        raise ValueError("output already exists; create-only preparation will not overwrite it")
    if not resolved.parent.is_dir():
        raise ValueError("output parent directory must already exist")
    return resolved


def read_parquet(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Bound compressed bytes, row count and declared decoded storage first."""
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("Parquet input must be a regular file, not a symlink")
    with path.open("rb") as handle:
        raw = handle.read(MAX_ASSET_BYTES + 1)
    if len(raw) > MAX_ASSET_BYTES:
        raise ValueError("Parquet input exceeds the 2 MiB asset budget")
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as error:
        raise ValueError("optional PyArrow is needed for this offline command; see DATA_FEASIBILITY.md") from error
    parquet = pq.ParquetFile(pa.BufferReader(raw))
    if parquet.metadata.num_rows > MAX_ROWS:
        raise ValueError("Parquet input exceeds the 40,000-row budget")
    declared_size = sum(
        parquet.metadata.row_group(group).column(column).total_uncompressed_size
        for group in range(parquet.metadata.num_row_groups)
        for column in range(parquet.metadata.num_columns)
    )
    if declared_size > MAX_DECODED_BYTES:
        raise ValueError("Parquet input exceeds the 128 MiB decoded-storage budget")
    table = parquet.read()
    if table.nbytes > MAX_DECODED_BYTES:
        raise ValueError("decoded Arrow table exceeds the 128 MiB budget")
    return table.to_pylist(), {
        "path": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw), "rows": table.num_rows, "columns": table.num_columns,
        "arrow_decoded_bytes": table.nbytes, "pyarrow_version": pa.__version__,
    }


def prepare_panel(
    player_rows: list[Mapping[str, Any]], schedule_rows: list[Mapping[str, Any]]
) -> tuple[list[NBAPlayerGame], dict[str, Any]]:
    """Apply the already documented cohort; retain every upstream exclusion."""
    if len(player_rows) > MAX_ROWS or len(schedule_rows) > MAX_ROWS:
        raise ValueError("source rows exceed the 40,000-row budget")
    index = {}
    for schedule in schedule_rows:
        source_id = schedule.get("game_id")
        if type(source_id) is not int or source_id <= 0:
            raise ValueError("schedule needs a positive integer source game ID")
        key = str(source_id)
        if key in index:
            raise ValueError("duplicate schedule game ID; revisions cannot be silently selected")
        index[key] = schedule
    normalized, rejected = normalize_sdv_rows(player_rows, max_rows=MAX_ROWS)
    audit = audit_rows(normalized, max_rows=MAX_ROWS)
    if audit["duplicate_event_player_rows"] or audit["identity_failures"]:
        raise ValueError("source contains duplicate identities or inconsistent count arithmetic")
    join_rejections = Counter()
    cohort_exclusions = Counter()
    joined, selected = [], []
    for row in normalized:
        if row.event_id not in index:
            join_rejections["missing_schedule_event"] += 1
            continue
        try:
            row = with_sdv_schedule(row, index[row.event_id], standard_team_ids=STANDARD_TEAMS)
        except (ValueError, TypeError) as error:
            join_rejections[str(error)] += 1
            continue
        joined.append(row)
        # Same fixed, exclusive precedence as the root's research input contract.
        if row.id_namespace != "espn":
            reason = "unsupported_identity_namespace"
        elif row.team_id not in STANDARD_TEAMS or row.opponent_id not in STANDARD_TEAMS:
            reason = "nonstandard_nba_teams_including_all_star"
        elif row.season_type != "2":
            reason = "outside_source_stage2"
        elif row.final_status != "FINAL":
            reason = "not_explicitly_final"
        elif row.participation != "APPEARED":
            reason = "dnp" if row.participation == "DNP" else "unknown_participation"
        elif row.minutes is None or any(getattr(row, field) is None for field in COUNT_FIELDS):
            reason = "incomplete_primitive_or_minutes"
        elif row.minutes_precision not in {"seconds", "rounded_whole_minutes"}:
            reason = "unknown_minutes_precision"
        else:
            reason = None
        if reason:
            cohort_exclusions[reason] += 1
        else:
            selected.append(row)
    exclusions = len(rejected) + sum(join_rejections.values()) + sum(cohort_exclusions.values())
    if len(selected) + exclusions != len(player_rows):
        raise ValueError("row accounting failed")
    return selected, {
        "schema_version": "nba-panel-preparation-v1",
        "purpose": "RECONSTRUCTED_RESEARCH_PREPARATION_NO_EVALUATION",
        "population": "identified complete APPEARED, archived FINAL, source stage2, reviewed standard teams1..30; stage2 may include NBA Cup final",
        "raw_player_rows": len(player_rows), "schedule_rows": len(schedule_rows),
        "normalized_player_rows": len(normalized), "schedule_joined_rows": len(joined),
        "upstream_exclusions": {
            "normalization_rejected": len(rejected),
            "normalization_rejection_reasons": dict(sorted(Counter(r["reason"] for r in rejected).items())),
            "schedule_join_rejected": sum(join_rejections.values()),
            "schedule_join_rejection_reasons": dict(sorted(join_rejections.items())),
            "cohort_exclusion_precedence": ["unsupported_identity_namespace", "nonstandard_nba_teams_including_all_star",
                "outside_source_stage2", "not_explicitly_final", "dnp_or_unknown_participation",
                "incomplete_primitive_or_minutes", "unknown_minutes_precision"],
            "cohort_exclusion_counts": dict(sorted(cohort_exclusions.items())),
            "total_excluded_rows": exclusions,
        },
        "output_rows": len(selected), "output_events": len({row.event_id for row in selected}),
        "claims": {"historical_asof_verified": False, "pregame_roster_verified": False,
                   "model_evaluated": False, "source_permission_established": False},
    }


def write_create_only(path: Path, rows: list[NBAPlayerGame]) -> dict[str, Any]:
    """Atomically create exact audited JSONL bytes without replacing any file."""
    destination = validate_output_path(path)
    checksum = hashlib.sha256()
    size = 0
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".nba-panel-", delete=False) as handle:
            temporary = Path(handle.name)
            for row in rows:
                # Preserve the initial audited panel's order and serialization.
                encoded = (json.dumps(row.to_record(), allow_nan=False) + "\n").encode("utf-8")
                handle.write(encoded)
                checksum.update(encoded)
                size += len(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"path": str(destination), "sha256": checksum.hexdigest(), "bytes": size,
            "publication": "local_create_only; not a durable prospective ledger"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--players", type=Path, required=True)
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        validate_output_path(args.output)
        players, player_source = read_parquet(args.players)
        schedule, schedule_source = read_parquet(args.schedule)
        rows, report = prepare_panel(players, schedule)
        report["input_assets"] = {"players": player_source, "schedule": schedule_source}
        report["output"] = write_create_only(args.output, rows)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
