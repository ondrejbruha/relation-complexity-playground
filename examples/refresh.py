"""Refresh the small example snapshots from completed local experiment exports."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import shutil
import sqlite3

ROOT = Path(__file__).resolve().parent.parent
EXPORTS = ("plot.png", "plot.svg", "summary.csv", "distribution.csv")
EXPECTED_CATALOG_COUNTS = {1: 1, 2: 2, 3: 4, 4: 11, 5: 34, 6: 156, 7: 1044,
                           8: 12346, 9: 274668}


def inspect_source(directory: Path, mode: str) -> dict:
    for name in (*EXPORTS, "experiment.sqlite"):
        if not (directory / name).is_file():
            raise ValueError(f"Missing {directory / name}; finish the experiment and export it first.")
    db = sqlite3.connect((directory / "experiment.sqlite").resolve().as_uri() + "?mode=ro", uri=True)
    try:
        metadata = dict(db.execute("SELECT key, value FROM metadata"))
        signature = json.loads(metadata["signature"])
        if signature["mode"] != mode:
            raise ValueError(f"{directory} is a {signature['mode']} experiment, expected {mode}.")
        counts = {n: {"graphs": count, "exact": exact} for n, count, exact in db.execute(
            "SELECT n, count(*), sum(status='exact') FROM results GROUP BY n ORDER BY n")}
    finally:
        db.close()
    with (directory / "summary.csv").open(encoding="utf-8", newline="") as stream:
        summary = list(csv.DictReader(stream))
    orders = [int(row["n"]) for row in summary]
    if len(set(orders)) != len(orders) or set(orders) != set(counts):
        raise ValueError(f"Summary orders differ from database coverage in {directory}.")
    for row in summary:
        count = counts[int(row["n"])]
        if int(row["processed"]) != count["graphs"] or int(row["exact_count"]) != count["exact"]:
            raise ValueError(f"Stale summary in {directory}; run main.py --plot-only first.")
    if mode == "catalog":
        actual = {n: row["graphs"] for n, row in counts.items()}
        if signature.get("connected") or actual != EXPECTED_CATALOG_COUNTS:
            raise ValueError("The catalogue snapshot requires all graphs with orders 1 through 9.")
        if any(row["exact"] != row["graphs"] for row in counts.values()):
            raise ValueError("The catalogue snapshot contains incomplete per-graph computations.")
        if any(row["maximum_certified"] != "True" for row in summary):
            raise ValueError("The catalogue snapshot contains uncertified maxima.")
    return {"signature": signature, "graphs": sum(row["graphs"] for row in counts.values()),
            "exact_graphs": sum(row["exact"] for row in counts.values()),
            "counts_by_order": counts,
            "catalogue_sha256": {key.split(":")[-1]: value for key, value in metadata.items()
                                 if key.startswith("catalog-sha256:")}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-dir", type=Path, default=ROOT / "results/catalog")
    parser.add_argument("--families-dir", type=Path, default=ROOT / "results/families")
    args = parser.parse_args(argv)
    sources = {"catalog": args.catalog_dir, "families": args.families_dir}
    try:
        # Validate both sources before changing any published snapshot.
        snapshots = {mode: inspect_source(directory, mode) for mode, directory in sources.items()}
        manifest = {"snapshot_utc": datetime.now(timezone.utc).isoformat(),
                    "snapshot_environment": {"python": platform.python_version(),
                                             "networkx": version("networkx"),
                                             "matplotlib": version("matplotlib")},
                    "datasets": snapshots}
        for mode, source in sources.items():
            destination = ROOT / "examples" / mode
            destination.mkdir(parents=True, exist_ok=True)
            hashes = {}
            for name in EXPORTS:
                target = destination / name
                if target.suffix in (".csv", ".svg"):
                    # Keep hashes valid after Git's LF checkout normalization.
                    target.write_bytes((source / name).read_bytes().replace(b"\r\n", b"\n"))
                else:
                    shutil.copyfile(source / name, target)
                hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
            snapshots[mode]["export_sha256"] = hashes
        (ROOT / "examples/provenance.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (KeyError, OSError, ValueError, sqlite3.Error) as exc:
        parser.error(str(exc))
    print("Refreshed example figures, summaries, and provenance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
