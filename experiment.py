"""Resumable graph experiments with SQLite checkpoints and PNG/SVG plots."""
from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
import csv
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
from time import monotonic
import urllib.request

import networkx as nx

from relational_complexity import ENGINE_VERSION, compute_relational_complexity

FAMILIES = ("path", "cycle", "complete", "bipartite", "petersen", "rook", "cube", "kneser")
CATALOG_COUNTS = {8: 12_346, 9: 274_668}
CATALOG_URL = "https://users.cecs.anu.edu.au/~bdm/data/graph{n}.g6"


def graph_code(graph: nx.Graph) -> str:
    return nx.to_graph6_bytes(graph, header=False).strip().decode("ascii")


def _worker(task: dict, timeout: float | None, max_aut: int | None) -> dict:
    graph = nx.from_graph6_bytes(task["graph6"].encode("ascii"))
    return {**task, **compute_relational_complexity(
        graph, timeout=timeout, max_automorphisms=max_aut).to_dict()}


def _worker_init() -> None:
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def _signature(args) -> dict:
    signature = {"engine": ENGINE_VERSION, "mode": args.mode, "connected": args.connected}
    if args.mode == "random":
        signature.update(seed=args.seed, probability=args.p)
    elif args.mode == "families":
        signature["families"] = sorted(set(args.families))
    elif args.mode == "graph6":
        digest = hashlib.sha256()
        with args.input.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        signature["input_sha256"] = digest.hexdigest()
    elif args.mode == "geng":
        signature["geng"] = args.geng
    elif args.mode == "catalog":
        signature["catalog"] = CATALOG_URL
    return signature


def open_database(path: Path, signature: dict) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS results (
                task_id TEXT PRIMARY KEY, graph6 TEXT NOT NULL, n INTEGER NOT NULL,
                status TEXT NOT NULL, payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS graph_index ON results(graph6, status);
            CREATE TABLE IF NOT EXISTS coverage (
                n INTEGER PRIMARY KEY, expected_count INTEGER NOT NULL, exhaustive INTEGER NOT NULL
            );
        """)
        stored = db.execute("SELECT value FROM metadata WHERE key='signature'").fetchone()
        requested = dict(signature)
        if stored:
            previous = json.loads(stored[0])
            old_identity, new_identity = dict(previous), dict(requested)
            # A family selection is a run scope, like the vertex range. Task IDs
            # already distinguish families, so changing this scope is resumable.
            # This also accepts databases produced by the original strict check.
            if previous.get("mode") == requested.get("mode") == "families":
                old_identity.pop("families", None)
                new_identity.pop("families", None)
                requested["families"] = sorted(set(previous.get("families", []))
                                               | set(requested.get("families", [])))
            if old_identity != new_identity:
                differences = [f"{key}: stored={old_identity.get(key)!r}, requested={new_identity.get(key)!r}"
                               for key in sorted(old_identity.keys() | new_identity.keys())
                               if old_identity.get(key) != new_identity.get(key)]
                raise ValueError("Output directory contains an incompatible dataset/engine ("
                                 + "; ".join(differences) + "). Choose a different --output directory.")
        with db:
            db.execute("INSERT OR REPLACE INTO metadata VALUES ('signature', ?)",
                       (json.dumps(requested, sort_keys=True),))
        return db
    except Exception:
        db.close()
        raise


def save_result(db: sqlite3.Connection, record: dict) -> None:
    previous = db.execute("SELECT payload FROM results WHERE task_id=?", (record["task_id"],)).fetchone()
    if previous:
        old = json.loads(previous[0])
        if old["lower_bound"] > record["lower_bound"]:
            record = {**record, "lower_bound": old["lower_bound"], "witness": old["witness"]}
        record = {**record, "upper_bound": min(old["upper_bound"], record["upper_bound"])}
        if record["lower_bound"] > record["upper_bound"]:
            raise ValueError("New result contradicts saved bounds; check the algorithm/dataset")
        if record["lower_bound"] == record["upper_bound"]:
            record = {**record, "rc": record["lower_bound"], "status": "exact"}
    with db:  # Every graph is its own durable checkpoint.
        db.execute("INSERT OR REPLACE INTO results VALUES (?, ?, ?, ?, ?)",
                   (record["task_id"], record["graph6"], record["n"], record["status"],
                    json.dumps(record, sort_keys=True)))


def _coverage(db, n, count, exhaustive):
    with db:
        db.execute("INSERT OR REPLACE INTO coverage VALUES (?, ?, ?)", (n, count, int(exhaustive)))


def tasks(args, db):
    def make(task_id, graph, label):
        return {"task_id": task_id, "graph6": graph_code(graph), "label": label}

    if args.mode in ("atlas", "catalog"):
        selected = [(i, g) for i, g in enumerate(nx.graph_atlas_g())
                    if args.min_n <= len(g) <= args.max_n
                    and (not args.connected or (len(g) > 0 and nx.is_connected(g)))]
        for n in range(args.min_n, min(7, args.max_n) + 1):
            _coverage(db, n, sum(len(g) == n for _, g in selected), not args.connected)
        for index, graph in selected:
            yield make(f"atlas:{index}", graph, f"atlas #{index}")
        if args.mode == "catalog":
            for n in range(max(8, args.min_n), args.max_n + 1):
                url = CATALOG_URL.format(n=n)
                cache = args.output / f"graph{n}.g6"
                if not cache.exists():
                    print(f"Downloading complete n={n} catalogue from {url}", flush=True)
                    temporary = cache.with_suffix(".download")
                    with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as destination:
                        while chunk := response.read(1024 * 1024):
                            destination.write(chunk)
                    temporary.replace(cache)
                # Completeness up to isomorphism relies on McKay's published catalogue.
                codes = cache.read_bytes().splitlines()
                codes = [line.strip() for line in codes if line.strip() and line.strip() != b">>graph6<<"]
                if len(codes) != CATALOG_COUNTS[n] or len(set(codes)) != len(codes):
                    raise ValueError(f"Unexpected count or duplicate records in {cache}")
                digest = hashlib.sha256(cache.read_bytes()).hexdigest()
                with db:
                    key = f"catalog-sha256:{n}"
                    old = db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
                    if old and old[0] != digest:
                        raise ValueError(f"Cached catalogue changed: {cache}")
                    db.execute("INSERT OR IGNORE INTO metadata VALUES (?, ?)", (key, digest))
                _coverage(db, n, CATALOG_COUNTS[n], not args.connected)
                for index, code in enumerate(codes):
                    graph = nx.from_graph6_bytes(code)
                    if len(graph) != n:
                        raise ValueError(f"Unexpected graph order in {cache}")
                    if not args.connected or nx.is_connected(graph):
                        yield make(f"catalog:{n}:{index}", graph, f"McKay n={n} #{index}")
    elif args.mode == "random":
        for n in range(args.min_n, args.max_n + 1):
            for sample in range(args.samples):
                seed = int.from_bytes(hashlib.sha256(f"{args.seed}:{n}:{sample}".encode()).digest()[:8], "big")
                yield make(f"random:{n}:{sample}", nx.gnp_random_graph(n, args.p, seed=seed), f"sample {sample}")
    elif args.mode == "families":
        for n in range(args.min_n, args.max_n + 1):
            for family in sorted(set(args.families)):
                label = family
                if family == "path":
                    graph = nx.path_graph(n)
                elif family == "cycle" and n >= 3:
                    graph = nx.cycle_graph(n)
                elif family == "complete":
                    graph = nx.complete_graph(n)
                elif family == "bipartite":
                    graph = nx.complete_bipartite_graph(n // 2, n - n // 2)
                elif family == "petersen" and n == 10:
                    graph = nx.petersen_graph()
                elif family == "rook" and n >= 4 and math.isqrt(n) ** 2 == n:
                    side = math.isqrt(n)
                    graph = nx.line_graph(nx.complete_bipartite_graph(side, side))
                elif family == "cube" and n >= 2 and n & (n - 1) == 0:
                    graph = nx.hypercube_graph(n.bit_length() - 1)
                elif family == "kneser":
                    k = next((k for k in range(2, n.bit_length() + 1) if math.comb(2 * k + 1, k) == n), None)
                    if k is None:
                        continue
                    subsets = list(itertools.combinations(range(2 * k + 1), k))
                    masks = [sum(1 << v for v in subset) for subset in subsets]
                    graph = nx.Graph()
                    graph.add_nodes_from(range(n))
                    graph.add_edges_from((i, j) for i in range(n) for j in range(i) if masks[i] & masks[j] == 0)
                    label = f"KG({2*k+1},{k})"
                else:
                    continue
                graph = nx.convert_node_labels_to_integers(graph)
                yield make(f"family:{family}:{n}", graph, label)
    elif args.mode == "circulant":
        for n in range(max(1, args.min_n), args.max_n + 1):
            # All symmetric connection sets, with duplicate isomorphism types.
            # Complement symmetry halves the search; this remains a candidate set.
            distances = list(range(1, n // 2 + 1))
            limit = 1 << max(0, len(distances) - 1)
            for mask in range(min(limit, args.samples)):
                graph = nx.Graph()
                graph.add_nodes_from(range(n))
                for bit, distance in enumerate(distances):
                    if mask & (1 << bit):
                        graph.add_edges_from((v, (v + distance) % n) for v in range(n))
                yield make(f"circulant:{n}:{mask}", graph, f"circulant mask={mask}")
    elif args.mode == "graph6":
        with args.input.open("rb") as stream:
            for index, line in enumerate(stream, 1):
                line = line.strip()
                if not line or line == b">>graph6<<":
                    continue
                try:
                    graph = nx.from_graph6_bytes(line)
                except Exception as exc:
                    raise ValueError(f"Invalid graph6 on line {index}: {exc}") from exc
                if args.min_n <= len(graph) <= args.max_n:
                    if not args.connected or (len(graph) > 0 and nx.is_connected(graph)):
                        yield make(f"graph6:{index}", graph, f"line {index}")
    elif args.mode == "geng":
        for n in range(args.min_n, args.max_n + 1):
            executable = str(Path(args.geng).resolve()) if Path(args.geng).is_file() else args.geng
            command = [executable, "-q", "-g"] + (["-c"] if args.connected else []) + [str(n)]
            with (args.output / "geng.log").open("ab") as errors:
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
                count = 0
                try:
                    for line in process.stdout:
                        if not line.strip() or line.strip() == b">>graph6<<":
                            continue
                        graph = nx.from_graph6_bytes(line.strip())
                        if len(graph) != n:
                            raise ValueError("geng returned an unexpected graph order")
                        yield make(f"geng:{n}:{count}", graph, f"geng #{count}")
                        count += 1
                    if process.wait() != 0:
                        raise RuntimeError("geng failed; inspect geng.log")
                    _coverage(db, n, count, not args.connected)
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.wait()
                    process.stdout.close()


def summaries(db):
    records = [json.loads(row[0]) for row in db.execute("SELECT payload FROM results ORDER BY n, task_id")]
    coverage = {n: (count, exhaustive) for n, count, exhaustive in db.execute("SELECT * FROM coverage")}
    grouped = {}
    for record in records:
        grouped.setdefault(record["n"], []).append(record)
    output = []
    padded_best = 0
    best_graph6 = None
    for n, group in sorted(grouped.items()):
        exact = [r for r in group if r["rc"] is not None]
        expected, exhaustive = coverage.get(n, (None, False))
        all_present = exhaustive and expected == len(group)
        lower = max(r["lower_bound"] for r in group)
        upper = max(r["upper_bound"] for r in group) if all_present else max(0, n - 1)
        representative = max(group, key=lambda r: r["lower_bound"])["graph6"]
        if best_graph6 is None or lower >= padded_best:
            padded_best, best_graph6 = lower, representative
        # Proposition 3.4: adding isolated vertices retains a lower bound on rc.
        padded_graph = nx.from_graph6_bytes(best_graph6.encode("ascii"))
        padded_graph.add_nodes_from(range(len(padded_graph), n))
        if padded_best > upper:
            raise ValueError("Results contradict the lower bound obtained by isolated-vertex padding")
        output.append({"n": n, "processed": len(group), "exact_count": len(exact),
                       "incomplete_count": len(group) - len(exact),
                       "mean_rc_exact": sum(r["rc"] for r in exact) / len(exact) if exact else None,
                       "max_rc_exact": max((r["rc"] for r in exact), default=None),
                       "observed_lower_bound": lower, "padded_lower_bound": padded_best,
                       "global_upper_bound": upper,
                       "expected_count": expected, "maximum_certified": bool(all_present and padded_best == upper),
                       "representative_graph6": representative, "padded_graph6": graph_code(padded_graph)})
    return records, output


def _csv(path, records):
    if not records:
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        for record in records:
            writer.writerow({key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list))
                             else value for key, value in record.items()})
    temporary.replace(path)


def export(db, directory, mode):
    records, summary = summaries(db)
    if not records:
        return
    _csv(directory / "values.csv", records)
    _csv(directory / "summary.csv", summary)
    candidates = directory / "extremal_candidates.g6"
    temporary_candidates = candidates.with_suffix(".g6.tmp")
    temporary_candidates.write_text("\n".join(s["padded_graph6"] for s in summary) + "\n", encoding="ascii")
    temporary_candidates.replace(candidates)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    with plt.rc_context({"font.size": 11, "axes.spines.top": False,
                         "axes.spines.right": False, "svg.fonttype": "none"}):
        fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), layout="constrained")
        exact = [r for r in records if r["rc"] is not None]
        ns = [s["n"] for s in summary]
        for ax in axes:
            ax.plot(ns, [s["padded_lower_bound"] for s in summary], color="#b45309", linewidth=2,
                    label="Proven lower bound for f(n), including isolated padding")
            if any(s["observed_lower_bound"] < s["padded_lower_bound"] for s in summary):
                ax.plot(ns, [s["observed_lower_bound"] for s in summary], color="#b45309", linestyle=":",
                        alpha=0.5, label="Observed maximum at each n")
            for certified, marker, face, label in [
                (True, "o", "#b45309", "Certified exact f(n)"),
                (False, "^", "white", "Global maximum not certified")]:
                selected = [s for s in summary if s["maximum_certified"] == certified]
                if selected:
                    ax.scatter([s["n"] for s in selected], [s["padded_lower_bound"] for s in selected],
                               s=50, marker=marker, facecolors=face, edgecolors="#b45309", zorder=5, label=label)
            ax.set(ylabel="Structural relational complexity", ylim=(-0.15, None))
            ax.yaxis.set_major_locator(MaxNLocator(integer=True))
            ax.grid(alpha=0.18)
        frequencies = {}
        for record in exact:
            pair = record["n"], record["rc"]
            frequencies[pair] = frequencies.get(pair, 0) + 1
        distribution = [{"n": n, "rc": rc, "count": count} for (n, rc), count in sorted(frequencies.items())]
        _csv(directory / "distribution.csv", distribution)
        axes[0].scatter([r["n"] for r in distribution], [r["rc"] for r in distribution],
                        s=[12 + 9 * math.log2(r["count"]) for r in distribution],
                        alpha=0.28, color="#64748b", label="Exact values (area scales with log count)")
        axes[0].set(xlabel="Number of vertices n", title=f"Measured values - {mode}")
        axes[0].xaxis.set_major_locator(MaxNLocator(integer=True))
        axes[1].set(xlabel="Number of vertices n (log2 scale)", title="View for comparing growth")
        # There is no log(0). Do not claim any reference curve is a proven bound.
        if all(n > 0 for n in ns):
            axes[1].set_xscale("log", base=2)
            axes[1].set_xticks(ns if len(ns) <= 15 else [2 ** k for k in range(max(ns).bit_length())])
            from matplotlib.ticker import ScalarFormatter
            axes[1].xaxis.set_major_formatter(ScalarFormatter())
            axes[1].plot(ns, [math.log2(n) for n in ns], linestyle="--", color="#0369a1",
                         alpha=0.7, label="log2(n), reference curve only")
        else:
            axes[1].set_xlabel("Number of vertices n (linear; dataset includes n=0)")
        if mode == "families":
            for label in sorted({r["label"] for r in exact}):
                group = sorted((r for r in exact if r["label"] == label), key=lambda r: r["n"])
                axes[0].plot([r["n"] for r in group], [r["rc"] for r in group],
                             marker="o", markersize=4, linestyle="none", alpha=0.7, label=label)
        for ax in axes:
            top = max([max(line.get_ydata()) for line in ax.lines] + [0])
            ax.set_ylim(-0.15, max(0.75, top + 0.3))
            if mode == "families" and ax is axes[0]:
                ax.legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=3)
            else:
                ax.legend(fontsize=7, loc="upper left")
        for extension in ("png", "svg"):
            temporary = directory / f"plot.tmp.{extension}"
            fig.savefig(temporary, dpi=180)
            temporary.replace(directory / f"plot.{extension}")
        plt.close(fig)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--mode", choices=("atlas", "catalog", "random", "families", "circulant", "graph6", "geng"), default="atlas")
    result.add_argument("--min-n", type=int, default=1)
    result.add_argument("--max-n", type=int, default=7)
    result.add_argument("--samples", type=int, default=100, help="Random samples / circulant masks per order")
    result.add_argument("--p", type=float, default=0.3)
    result.add_argument("--seed", type=int, default=42)
    result.add_argument("--families", nargs="+", choices=FAMILIES, default=list(FAMILIES))
    result.add_argument("--input", type=Path, help="graph6 file")
    result.add_argument("--geng", default="geng", help="Path to nauty geng executable")
    result.add_argument("--connected", action="store_true", help="Connected atlas/geng/graph6 graphs only")
    result.add_argument("--workers", type=int, default=max(1, min(4, (os.cpu_count() or 2) - 1)))
    result.add_argument("--timeout", type=float, default=30, help="Cooperative seconds per graph; 0 = unlimited")
    result.add_argument("--max-automorphisms", type=int, default=100_000, help="0 = unlimited")
    result.add_argument("--output", type=Path, default=Path("results/atlas"))
    result.add_argument("--retry-incomplete", action="store_true", help="Retry bounded results with current limits")
    result.add_argument("--plot-only", action="store_true", help="Export existing DB without computing")
    result.add_argument("--plot-every", type=int, default=100, help="Export every this many graphs; also every 60s")
    return result


def main(argv=None):
    arguments = parser()
    args = arguments.parse_args(argv)
    if args.workers < 1 or args.samples < 1 or args.plot_every < 1:
        arguments.error("workers, samples and plot-every must be positive")
    if args.min_n < 0 or args.max_n < args.min_n or not 0 <= args.p <= 1:
        arguments.error("Invalid vertex range or edge probability")
    if args.timeout < 0 or args.max_automorphisms < 0:
        arguments.error("Limits must be non-negative")
    if not args.plot_only and args.mode == "atlas" and args.max_n > 7:
        arguments.error("Complete atlas ends at n=7; use --mode catalog (up to 9) or geng")
    if args.mode == "catalog" and args.max_n > 9:
        arguments.error("Built-in complete catalogues end at n=9; use --mode geng beyond this")
    if args.mode == "geng" and args.min_n < 1:
        arguments.error("geng requires n >= 1")
    if not args.plot_only and args.mode == "graph6" and not args.input:
        arguments.error("--mode graph6 requires --input")
    if args.connected and args.mode not in ("atlas", "catalog", "geng", "graph6"):
        arguments.error("--connected requires atlas, catalog, geng or graph6")
    args.output.mkdir(parents=True, exist_ok=True)
    database_path = args.output / "experiment.sqlite"
    if args.plot_only and not database_path.exists():
        arguments.error("No existing experiment.sqlite in --output")
    if args.plot_only:
        db = sqlite3.connect(database_path)
        try:
            signature = json.loads(db.execute("SELECT value FROM metadata WHERE key='signature'").fetchone()[0])
            export(db, args.output, signature["mode"])
        finally:
            db.close()
        print(f"Exports written to {args.output.resolve()}")
        return 0
    try:
        db = open_database(database_path, _signature(args))
    except (ValueError, OSError, sqlite3.Error) as exc:
        arguments.error(str(exc))
    if args.mode == "families":
        stored_signature = json.loads(db.execute("SELECT value FROM metadata WHERE key='signature'").fetchone()[0])
        saved_families = stored_signature.get("families", [])
        if set(saved_families) != set(args.families):
            print("Previous family results are retained; exports include all saved families. "
                  "Current task selection: " + ", ".join(sorted(set(args.families))), flush=True)
    stopped = False
    def stop(signum, frame):
        nonlocal stopped
        if stopped:
            raise KeyboardInterrupt
        stopped = True
        print("\nStopping new tasks; finishing and saving running graphs...", flush=True)
    old_handler = signal.signal(signal.SIGINT, stop)
    source = tasks(args, db)
    new_count = skipped = 0
    last_export = monotonic()

    def accept(record):
        nonlocal new_count, last_export
        save_result(db, record)
        new_count += 1
        if new_count % args.plot_every == 0 or monotonic() - last_export >= 60:
            export(db, args.output, args.mode)
            last_export = monotonic()
            print(f"Saved {new_count} new graphs; skipped {skipped}; latest n={record['n']}, "
                  f"rc={record['rc'] if record['rc'] is not None else (record['lower_bound'], record['upper_bound'])}", flush=True)

    def pending_tasks():
        nonlocal skipped
        for task in source:
            if stopped:
                break
            old = db.execute("SELECT status FROM results WHERE task_id=?", (task["task_id"],)).fetchone()
            if old and (old[0] == "exact" or not args.retry_incomplete):
                skipped += 1
                continue
            cached = db.execute("SELECT payload FROM results WHERE graph6=? AND status='exact' LIMIT 1", (task["graph6"],)).fetchone()
            if cached:
                accept({**json.loads(cached[0]), **task, "seconds": 0.0})
            else:
                yield task

    print(f"Mode={args.mode}, n={args.min_n}..{args.max_n}, workers={args.workers}; checkpoint={database_path.resolve()}", flush=True)
    iterator = pending_tasks()
    pool = None
    failed = False
    try:
        if args.workers == 1:
            for task in iterator:
                if stopped:
                    break
                accept(_worker(task, args.timeout or None, args.max_automorphisms or None))
        else:
            pool = ProcessPoolExecutor(max_workers=args.workers, initializer=_worker_init)
            pending = {}
            exhausted = False
            while pending or not exhausted:
                while not stopped and not exhausted and len(pending) < 2 * args.workers:
                    try:
                        task = next(iterator)
                    except StopIteration:
                        exhausted = True
                        break
                    pending[pool.submit(_worker, task, args.timeout or None, args.max_automorphisms or None)] = task
                if stopped:
                    exhausted = True
                if pending:
                    done, _ = wait(pending, timeout=1, return_when=FIRST_COMPLETED)
                    for future in done:
                        del pending[future]
                        accept(future.result())
                    if monotonic() - last_export >= 60:
                        export(db, args.output, args.mode)
                        last_export = monotonic()
                        print(f"Working: saved {new_count}, skipped {skipped}, pending {len(pending)}", flush=True)
    except KeyboardInterrupt:
        stopped = True
    except Exception as exc:
        failed = True
        print(f"Experiment stopped: {exc}", file=sys.stderr, flush=True)
    finally:
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=True)
        iterator.close()
        source.close()
        try:
            export(db, args.output, args.mode)
            _, summary = summaries(db)
            for entry in summary:
                kind = "exact f(n)" if entry["maximum_certified"] else "observed lower bound"
                print(f"n={entry['n']}: {kind}={entry['observed_lower_bound']}; exact={entry['exact_count']}/{entry['processed']}")
        finally:
            db.close()
            signal.signal(signal.SIGINT, old_handler)
    print(f"Saved {new_count} new graphs, skipped {skipped}. Outputs: {args.output.resolve()}")
    return 1 if failed else (130 if stopped else 0)
