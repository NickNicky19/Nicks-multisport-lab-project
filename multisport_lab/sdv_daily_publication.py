"""Independent, bounded publication of retained daily-snapshot research.

Publication reads originals; it never captures inputs, generates a forecast,
grants operating approval or turns a development preview into issuance.
Licensed source CSV originals remain in the records archive, outside Pages.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from .integrity import IntegrityError, canonical, digest, load_json, stamp, utc
from .ledger import LedgerRef
from .sdv_daily_inputs import PROTOCOL_ID, make_policy, validate_input, validate_policy, freshness

SCHEMA = "nba-sdv-daily-publication-v1"
MAX_ASSET_BYTES = 1024 * 1024
REMOTE_URL = "https://github.com/NickNicky19/Nicks-multisport-lab-project.git"
MAX_REMOTE_SECONDS = 60
FIELDS = {"schema_version", "protocol_id", "generated_at", "policy", "cycle", "inputs",
          "forecasts", "outcomes", "grades", "corrections", "activation", "counts", "status",
          "reason", "qualification", "financial_settlement", "asset_id"}
COUNTS = {"development_forecasts", "genuine_forecasts", "eligible_forecasts", "pending_grades"}


def require(ok, message):
    if not ok:
        raise IntegrityError(message)


def exact(value, fields, label):
    require(type(value) is dict and set(value) == set(fields), "Invalid daily public " + label)


def text(value):
    require(type(value) is str and 0 < len(value) <= 2048 and value.strip() == value,
            "Invalid daily public explanation")


def clock(value):
    require(type(value) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", value),
            "Daily publication requires precise UTC clocks")
    return utc(value)


def sealed(value, key):
    require(value.get(key) == digest({k: v for k, v in value.items() if k != key}),
            "Daily public original checksum mismatch")


def active_grades(asset):
    """A correction is an appended edge; never replace the original grade."""
    superseded = {row["original_ref"]["record_id"] for row in asset["corrections"]}
    outcomes = {row["reference"]["record_id"]: row["body"]["outcome_id"]
                for row in asset["outcomes"] if row["reference"]["record_id"] in superseded}
    return [row for row in asset["grades"]
            if row["reference"]["record_id"] not in superseded
            and row["body"]["outcome_id"] not in outcomes.values()]


def _admission(value, body, generated, policy):
    exact(value, {"eligible", "local_persistence_completed_at", "remote_recovery_completed_at", "reasons"}, "admission")
    require(type(value["eligible"]) is bool and type(value["reasons"]) is list
            and len(value["reasons"]) <= 16, "Invalid daily public eligibility")
    for reason in value["reasons"]:
        text(reason)
    previous = clock(body["verified_at"])
    complete = []
    for key in ("local_persistence_completed_at", "remote_recovery_completed_at"):
        item = value[key]
        if item is not None:
            actual = clock(item)
            require(previous <= actual <= generated, "Daily persistence chronology differs")
            previous = actual
            complete.append(actual)
        else:
            complete.append(None)
    require(complete[1] is None or complete[0] is not None,
            "Daily remote recovery lacks local persistence")
    if value["eligible"]:
        require(body["mode"] == "PROSPECTIVE_RESEARCH" and not value["reasons"]
                and all(item is not None for item in complete), "Daily eligibility lacks genuine completion")
        cutoff = clock(body["cutoff_at"])
        require(cutoff <= complete[0] <= complete[1]
                <= cutoff + timedelta(seconds=policy["issuance_window_seconds"])
                and complete[1] - clock(body["generation_started_at"])
                <= timedelta(seconds=policy["maximum_original_latency_seconds"]),
                "Daily original missed its actual completion deadline")
    else:
        require(bool(value["reasons"]), "Ineligible daily original needs an explanation")


def _counts(asset):
    forecasts = asset["forecasts"]
    final = {row["body"]["forecast_id"] for row in active_grades(asset)
             if row["body"]["status"] in {"SCORED", "DNP_NOT_SCORED"}}
    return {"development_forecasts": sum(row["body"]["mode"] == "DEVELOPMENT_ONLY" for row in forecasts),
            "genuine_forecasts": sum(row["body"]["mode"] == "PROSPECTIVE_RESEARCH" for row in forecasts),
            "eligible_forecasts": sum(row["admission"]["eligible"] for row in forecasts),
            "pending_grades": len(forecasts) - len(final)}


def _status(asset):
    counts = _counts(asset)
    if not asset["forecasts"]:
        return "INACTIVE"
    if counts["development_forecasts"]:
        return "DEVELOPMENT_PREVIEW"
    expected = 2 * len(asset["inputs"][0]["candidates"])
    if len(asset["forecasts"]) < expected or counts["eligible_forecasts"] < expected:
        return "PARTIAL"
    return "ISSUED" if counts["pending_grades"] else "COMPLETED"


def validate_asset(asset, *, now):
    from . import sdv_daily_producer as producer
    exact(asset, FIELDS, "asset")
    require(asset["schema_version"] == SCHEMA and asset["protocol_id"] == PROTOCOL_ID
            and asset["qualification"] == "UNAVAILABLE"
            and asset["financial_settlement"] == "NOT_EVALUATED", "Invalid daily public scope")
    generated = clock(asset["generated_at"])
    require(generated <= utc(now), "Daily public generation is in the future")
    text(asset["reason"])
    validate_policy(asset["policy"])
    exact(asset["counts"], COUNTS, "counts")
    require(all(type(value) is int and value >= 0 for value in asset["counts"].values()),
            "Invalid daily public counts")
    for field, ceiling in (("inputs", 1), ("forecasts", 8), ("outcomes", 16), ("grades", 32), ("corrections", 16)):
        require(type(asset[field]) is list and len(asset[field]) <= ceiling,
                "Daily publication record ceiling exceeded")
    inputs = {}
    for body in asset["inputs"]:
        validate_input(body)
        require(body["policy"] == asset["policy"] and clock(body["normalized_at"]) <= generated,
                "Daily public input policy/clock differs")
        inputs[body["input_id"]] = body
    cycle = asset["cycle"]
    if cycle is not None:
        producer.validate_cycle(cycle)
        require(cycle["policy_id"] == asset["policy"]["policy_id"]
                and clock(cycle["registered_at"]) <= generated, "Daily cycle policy/clock differs")
        for input_body in inputs.values():
            require(all(cycle["event"][key] == input_body["event"][key] for key in cycle["event"])
                    and cycle["candidates"] == input_body["candidates"],
                    "Daily input differs from registered event or cohort")
            require(all(all(source[key] == expected[key] for key in
                            ("role", "release_tag", "asset_name", "asset_url"))
                        for source, expected in zip(input_body["sources"], cycle["source_assets"])),
                    "Daily input differs from registered publisher releases")
    activation = asset["activation"]
    if activation is not None:
        require(cycle is not None, "Daily authorization lacks its registered cycle")
        producer.validate_authorization(activation, cycle=cycle, now=generated)
        require(clock(activation["checked_at"]) <= generated, "Daily authorization follows publication")
    forecasts, outcomes, grades, refs, subjects = {}, {}, {}, {}, set()
    modes = set()
    for plural, kind, index, id_key in (("forecasts", "forecasts", forecasts, "forecast_id"),
                                        ("outcomes", "outcomes", outcomes, "outcome_id"),
                                        ("grades", "grades", grades, "grade_id")):
        for row in asset[plural]:
            exact(row, {"reference", "body", *(["admission"] if plural == "forecasts" else [])}, "record")
            ref = LedgerRef.from_record(row["reference"])
            body = row["body"]
            require(ref.kind == kind and type(body) is dict and body.get(id_key) not in index
                    and ref.record_id not in refs, "Duplicate or wrong-kind daily public reference")
            require(body.get("schema_version") == "nba-sdv-daily-" + plural[:-1] + "-v1"
                    and body.get("protocol_id") == PROTOCOL_ID, "Wrong daily public typed original")
            if plural == "forecasts":
                input_body = inputs.get(body.get("input_id"))
                require(input_body is not None, "Daily forecast lacks its exact input")
                producer.validate_forecast(body, input_body, now=generated)
                require(cycle is not None and body["cycle_id"] == cycle["cycle_id"],
                        "Daily forecast lacks its registered cycle")
                require(body["history_ref"]["record_id"] == cycle["history_record_id"]
                        and body["history_panel_sha256"] == cycle["history_panel_sha256"],
                        "Daily forecast changed the registered fixed history")
                key = (body["player_id"], body["model_key"])
                require(key not in subjects, "Duplicate daily player/model original")
                subjects.add(key)
                modes.add(body["mode"])
                _admission(row["admission"], body, generated, asset["policy"])
                if row["admission"]["eligible"]:
                    freshness(input_body, at=clock(row["admission"]["remote_recovery_completed_at"]),
                              require_retrieval_window=True)
                if body["mode"] == "PROSPECTIVE_RESEARCH":
                    require(activation is not None, "Prospective daily publication lacks operating authorization")
                    producer.validate_authorization(activation, cycle=cycle,
                                                    producer_binding=body["producer_binding"], now=generated)
                    freshness(input_body, at=clock(body["issued_at"]), require_retrieval_window=True)
                else:
                    require(not row["admission"]["eligible"] and body["issued_at"] is None,
                            "Development preview cannot become prospective issuance")
            elif plural == "outcomes":
                producer.validate_outcome(body)
            index[body[id_key]] = body
            refs[ref.record_id] = (ref, body)
    require(len(modes) <= 1, "Development and genuine originals cannot share a daily cycle")
    for outcome in outcomes.values():
        require(any(all(outcome[key] == forecast[key] for key in
                        ("cycle_id", "event_id", "event_snapshot_id", "event_starts_at", "player_id", "team_id", "opponent_id", "mode"))
                    and (forecast["issued_at"] is None or clock(forecast["issued_at"]) <= clock(outcome["source_observed_at"]))
                    for forecast in forecasts.values()), "Daily outcome identity has no original forecast")
        require(clock(outcome["source_observed_at"]) <= clock(outcome["normalized_at"]) <= generated,
                "Daily outcome clocks follow publication")
    for grade in grades.values():
        forecast = forecasts.get(grade.get("forecast_id"))
        outcome = outcomes.get(grade.get("outcome_id"))
        require(forecast is not None and outcome is not None, "Daily grade lacks original forecast/outcome")
        producer.validate_grade(grade, forecast, outcome)
        require(clock(grade["graded_at"]) <= generated, "Daily grade follows publication")
    edges = {}
    for correction in asset["corrections"]:
        exact(correction, {"reference", "original_ref", "replacement_ref", "reason"}, "correction")
        ref = LedgerRef.from_record(correction["reference"])
        before = LedgerRef.from_record(correction["original_ref"])
        after = LedgerRef.from_record(correction["replacement_ref"])
        text(correction["reason"])
        require(ref.kind == "corrections" and before.kind == after.kind and before.kind in {"outcomes", "grades"}
                and before.record_id in refs and after.record_id in refs
                and before.record_id != after.record_id and before.record_id not in edges,
                "Invalid daily correction references")
        old_ref, old = refs[before.record_id]
        new_ref, new = refs[after.record_id]
        require(old_ref == before and new_ref == after and all(old[key] == new[key] for key in
                ("cycle_id", "event_id", "player_id", "mode")), "Daily correction changed its original subject")
        if before.kind == "grades":
            require(old["forecast_id"] == new["forecast_id"], "Daily correction changed the original forecast")
        require(clock(new["graded_at"] if before.kind == "grades" else new["source_observed_at"])
                >= clock(old["graded_at"] if before.kind == "grades" else old["source_observed_at"]),
                "Daily correction clock precedes its original")
        edges[before.record_id] = after.record_id
    for original in edges:
        seen, cursor = set(), original
        while cursor in edges:
            require(cursor not in seen, "Daily correction cycle")
            seen.add(cursor)
            cursor = edges[cursor]
    active = active_grades(asset)
    require(len({row["body"]["forecast_id"] for row in active}) == len(active),
            "Multiple active daily grades for one original")
    require(asset["counts"] == _counts(asset) and asset["status"] == _status(asset),
            "Daily public summary differs from exact originals")
    sealed(asset, "asset_id")
    require(len(canonical(asset)) <= MAX_ASSET_BYTES, "Complete daily asset exceeds 1-MiB limit")
    return asset


def make_asset(root, *, now):
    from .sdv_daily_store import DailyStore
    store = DailyStore(root)
    recovery = store.recover()
    pairs = recovery["records"]
    def bodies(schema):
        return [(ref, body) for ref, body in pairs if body["schema_version"] == "nba-sdv-daily-" + schema + "-v1"]
    forecasts = [{"reference": ref.to_record(), "body": body, "admission": store.admission(ref)}
                 for ref, body in bodies("forecast")]
    inputs = [body for _, body in bodies("input")]
    cycles, auth = bodies("cycle"), bodies("authorization")
    require(len(cycles) <= 1 and len(auth) <= 1, "Separate daily cycles need separate publication versions")
    asset = {"schema_version": SCHEMA, "protocol_id": PROTOCOL_ID, "generated_at": stamp(now),
        "policy": inputs[0]["policy"] if inputs else make_policy(),
        "cycle": cycles[0][1] if cycles else None, "inputs": inputs, "forecasts": forecasts,
        "outcomes": [{"reference": ref.to_record(), "body": body} for ref, body in bodies("outcome")],
        "grades": [{"reference": ref.to_record(), "body": body} for ref, body in bodies("grade")],
        "corrections": recovery.get("corrections", []), "activation": auth[0][1] if auth else None,
        "counts": {}, "status": "INACTIVE", "reason": "", "qualification": "UNAVAILABLE",
        "financial_settlement": "NOT_EVALUATED"}
    for field in ("forecasts", "outcomes", "grades"):
        asset[field].sort(key=lambda row: row["reference"]["record_id"])
    asset["counts"] = _counts(asset)
    asset["status"] = _status(asset)
    asset["reason"] = {
        "INACTIVE": "No daily-snapshot research forecast has been issued. A reviewed operating cycle and timely admitted daily assets are required.",
        "DEVELOPMENT_PREVIEW": "Development-only preview using retained publisher-release inputs. These records were not issued before a future game and never count as genuine forecasts.",
        "PARTIAL": "Some daily-snapshot originals are missing or lack timely durable recovery. Retained originals remain evidence; no late partner is substituted.",
        "ISSUED": "Genuine daily-snapshot pregame research forecasts are retained. Verified outcomes and individual statistical grades are pending.",
        "COMPLETED": "Daily-snapshot research originals and individual statistical grades are retained. This is not model or betting qualification."
    }[asset["status"]]
    asset["asset_id"] = digest(asset)
    return validate_asset(asset, now=now)


def read_asset(data_dir, descriptor, *, now):
    exact(descriptor, {"path", "sha256", "generated_at", "status", "retained", "error"}, "descriptor")
    require(type(descriptor["sha256"]) is str and re.fullmatch(r"[a-f0-9]{64}", descriptor["sha256"])
            and descriptor["path"] == "sdv-daily." + descriptor["sha256"] + ".json"
            and descriptor["status"] == "DAILY_SNAPSHOT_RESEARCH" and type(descriptor["retained"]) is bool,
            "Invalid daily public descriptor")
    if descriptor["error"] is not None:
        text(descriptor["error"])
    require(clock(descriptor["generated_at"]) <= utc(now), "Future daily descriptor")
    path = Path(data_dir) / descriptor["path"]
    asset = load_json(path, max_bytes=MAX_ASSET_BYTES)
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == descriptor["sha256"] and raw == canonical(asset)
            and asset["generated_at"] == descriptor["generated_at"], "Daily public bytes/clock differ")
    return validate_asset(asset, now=now)


def _validate_remote_records(staging, root, registered, *, now, git):
    """Use this release's trusted validators; execute no fetched Python code."""
    from .sdv_daily_store import DailyStore
    from . import sdv_daily_producer as producer
    recovered = DailyStore(staging).recover()
    asset = make_asset(staging, now=now)
    require(asset["cycle"] == registered, "Published records changed the registered daily cycle")
    forecasts = asset["forecasts"]
    require(forecasts and asset["counts"]["development_forecasts"] == 0
            and asset["counts"]["eligible_forecasts"] > 0
            and all(row["body"]["mode"] == "PROSPECTIVE_RESEARCH" for row in forecasts),
            "Remote daily branch has no admitted genuine research originals")
    require(recovered["genuine_issued"] == asset["counts"]["eligible_forecasts"],
            "Public eligibility differs from independently recovered originals")
    bindings = {digest(row["body"]["producer_binding"]): row["body"]["producer_binding"] for row in forecasts}
    require(len(bindings) == 1 and asset["activation"] is not None,
            "Remote daily originals disagree on their reviewed producer")
    binding = next(iter(bindings.values()))
    producer.validate_authorization(asset["activation"], cycle=registered, producer_binding=binding, now=now)
    current = producer.make_source_binding(root=root)
    require(current["files"] == binding["files"] and current["law_sha256"] == binding["law_sha256"],
            "Current release differs from the authorized original producer bytes")
    commit = binding["commit"]
    require(type(commit) is str and re.fullmatch(r"[a-f0-9]{40}", commit),
            "Remote daily records lack an exact reviewed producer commit")
    git("fetch", "--no-tags", "--depth=1", "origin", commit)
    for filename, expected in binding["files"].items():
        raw = git("show", commit + ":" + filename, binary=True).stdout
        require(len(raw) <= 2 * 1024 * 1024 and hashlib.sha256(raw).hexdigest() == expected,
                "Original producer commit does not contain its declared source bytes")
    return asset


def prepare_published_records(root, commit=None, *, now=None):
    """Read the fixed authorized records branch into an independent object store.

    This is called only by the existing main-branch Pages build. It publishes
    admitted originals without merging operating records into application code.
    The fetched branch never supplies executable code; only bounded immutable
    JSON records enter the checked-out release. A failed import aborts the build,
    leaving the previous deployed site intact. No branch means inactive software.
    """
    from .ledger import Ledger, KINDS, MAX_LEDGER_BYTES, MAX_LEDGER_RECORDS, MAX_RECORD_BYTES
    from .sdv_daily_store import DailyStore
    from .sdv_daily_producer import validate_cycle
    root = Path(root).absolute()
    for path in (root, *root.parents):
        require(not path.is_symlink(), "Daily publication root traverses a symlink")
    actual = utc(now or datetime.now(timezone.utc))
    registered = load_json(root / "config/sdv_daily_cycle_v1.json", max_bytes=32 * 1024)
    validate_cycle(registered)
    branch = registered["records_branch"]
    require(type(branch) is str and re.fullmatch(r"records/sdv-daily-[a-z0-9-]{1,80}", branch),
            "Daily publication destination differs from the fixed records branch")
    if commit is not None:
        require(type(commit) is str and re.fullmatch(r"[a-f0-9]{40}", commit),
                "Daily publication needs an exact records commit")
    deadline = time.monotonic() + MAX_REMOTE_SECONDS
    with tempfile.TemporaryDirectory(prefix="nml-daily-publication-readback-") as folder:
        staging = Path(folder)

        def git(*args, binary=False):
            remaining = deadline - time.monotonic()
            require(remaining > 0, "Daily publication readback exceeded its operation budget")
            try:
                result = subprocess.run(["git", *args], cwd=staging, capture_output=True,
                                        text=not binary, check=False, timeout=remaining)
            except subprocess.TimeoutExpired as exc:
                raise IntegrityError("Daily publication Git read timed out") from exc
            require(result.returncode == 0, "Daily publication Git read failed: " + args[0])
            return result

        git("init", "--quiet")
        git("remote", "add", "origin", REMOTE_URL)

        def remote_head():
            result = git("ls-remote", "--heads", "origin", "refs/heads/" + branch).stdout.strip()
            if not result:
                return None
            fields = result.split()
            require(len(fields) == 2 and fields[1] == "refs/heads/" + branch
                    and re.fullmatch(r"[a-f0-9]{40}", fields[0]), "Ambiguous daily publication remote branch")
            return fields[0]

        head = remote_head()
        if head is None:
            require(commit is None, "Requested daily records branch does not exist")
            return {"status": "NO_RECORDS", "commit": None, "records": 0, "eligible_forecasts": 0}
        require(commit is None or commit == head, "Requested daily records commit differs from the current fixed branch head")
        git("fetch", "--no-tags", "--depth=1", "origin", "refs/heads/" + branch)
        require(git("rev-parse", "FETCH_HEAD").stdout.strip() == head,
                "Daily records branch changed during independent fetch")
        listing = git("ls-tree", "-r", "-z", "--long", head, "--", "records", "daily/records", binary=True).stdout
        require(len(listing) <= 256 * 1024, "Daily record inventory exceeds its metadata budget")
        inventory = []
        for entry in listing.split(b"\0"):
            if not entry:
                continue
            try:
                metadata, path = entry.decode("utf-8").split("\t", 1)
                mode, kind, oid, size_text = metadata.split()
                size = int(size_text)
            except (ValueError, UnicodeDecodeError) as exc:
                raise IntegrityError("Malformed independent daily record inventory") from exc
            parts = path.split("/")
            prefix = "daily/records/" if path.startswith("daily/records/") else "records/"
            suffix = path[len(prefix):].split("/")
            require(mode == "100644" and kind == "blob" and re.fullmatch(r"[a-f0-9]{40}", oid)
                    and len(suffix) == 2 and suffix[0] in KINDS
                    and re.fullmatch(r"[a-f0-9]{64}\.json", suffix[1])
                    and 0 < size <= MAX_RECORD_BYTES, "Unsafe or oversized daily record path")
            inventory.append((path, oid, size))
        require(len(inventory) <= MAX_LEDGER_RECORDS and sum(row[2] for row in inventory) <= MAX_LEDGER_BYTES,
                "Independent daily snapshot exceeds unchanged ledger limits")
        for filename, oid, size in inventory:
            raw = git("cat-file", "blob", oid, binary=True).stdout
            require(len(raw) == size, "Independent daily record size differs")
            target = staging / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        # Authenticate every original parent record against the current release,
        # including legitimate newer records. The records branch cannot replace it.
        parent, _, _ = Ledger(root)._inventory()
        expected = {str(Path("records") / kind / path.name): path.read_bytes()
                    for kind, files in parent.items() for path, _ in files}
        fetched_parent = {path: (staging / path).read_bytes() for path, _, _ in inventory if path.startswith("records/")}
        require(expected == fetched_parent, "Daily publication branch changed the existing original records")
        asset = _validate_remote_records(staging, root, registered, now=actual, git=git)
        require(asset["cycle"] == registered and asset["activation"] is not None
                and asset["counts"]["development_forecasts"] == 0
                and asset["counts"]["eligible_forecasts"] > 0
                and asset["forecasts"] and all(row["body"]["mode"] == "PROSPECTIVE_RESEARCH" for row in asset["forecasts"]),
                "Development or unadmitted remote records cannot enter the public build")
        require(remote_head() == head, "Daily records branch changed before publication import")
        daily = [(path, (staging / path).read_bytes()) for path, _, _ in inventory if path.startswith("daily/records/")]
        existing, _, _ = DailyStore(root).ledger._inventory()
        fetched = {path: raw for path, raw in daily}
        require(all(fetched.get(str(Path("daily/records") / kind / path.name)) == path.read_bytes()
                    for kind, files in existing.items() for path, _ in files),
                "Daily publication cannot drop or replace retained originals")
        for filename, raw in daily:
            target = root / filename
            for path in (target, *target.parents):
                require(not path.is_symlink(), "Daily publication copy traverses a symlink")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                require(target.read_bytes() == raw, "Daily publication cannot overwrite an original")
                continue
            descriptor, temporary = tempfile.mkstemp(prefix="daily-publication-", dir=target.parent)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    os.link(temporary, target)
                except FileExistsError:
                    require(target.read_bytes() == raw, "Concurrent daily publication original differs")
            finally:
                Path(temporary).unlink(missing_ok=True)
        DailyStore(root).recover()
        require(time.monotonic() <= deadline, "Daily publication recovery exceeded its operation budget")
        return {"status": "IMPORTED", "commit": head, "records": len(daily),
                "eligible_forecasts": asset["counts"]["eligible_forecasts"]}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Read-only import of authorized daily originals for the existing Pages build")
    parser.add_argument("--records-commit")
    args = parser.parse_args()
    result = prepare_published_records(Path(__file__).resolve().parents[1], args.records_commit)
    print(result)


if __name__ == "__main__":
    main()
