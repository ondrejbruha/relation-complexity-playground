import contextlib
import csv
import io
import json
from pathlib import Path
import signal
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import networkx as nx

import experiment


class ExperimentTests(unittest.TestCase):
    def test_mixed_legacy_and_generator_rows_export_without_certifying_bounds(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            with contextlib.closing(experiment.open_database(output / "test.sqlite", {"engine": "test"})) as db:
                task = {"task_id": "family:petersen:10", "graph6": experiment.graph_code(nx.petersen_graph()),
                        "label": "petersen"}
                legacy = experiment._worker(task, None, None, "enumeration")
                for key in ("backend", "generators", "stabilizer_calls", "cache_hits", "heuristic_nodes",
                            "group_seconds", "search_seconds"):
                    legacy.pop(key)
                experiment.save_result(db, legacy)
                cube = nx.convert_node_labels_to_integers(nx.hypercube_graph(4))
                task = {"task_id": "family:cube:16", "graph6": experiment.graph_code(cube), "label": "cube"}
                experiment.save_result(db, experiment._worker(task, None, None, "enumeration", 8, 0, None, True))
                experiment.export(db, output, "families")
                _, summary = experiment.summaries(db)
                self.assertTrue(all(not row["maximum_certified"] for row in summary))
            with (output / "values.csv").open(encoding="utf-8", newline="") as stream:
                records = list(csv.DictReader(stream))
            self.assertEqual(records[0]["backend"], "")
            self.assertEqual(records[1]["backend"], "enumeration")
            self.assertEqual(records[1]["rc"], "")
            self.assertTrue((output / "plot.png").exists())
            self.assertTrue((output / "plot.svg").exists())

    def test_johnson_selection_resumes_with_dual_cached_graphs(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            base = ["--mode", "families", "--families", "johnson", "--max-n", "7",
                    "--workers", "1", "--output", str(output)]
            with contextlib.redirect_stdout(io.StringIO()), patch.object(experiment, "export"):
                self.assertEqual(experiment.main(base + ["--johnson", "6,1"]), 0)
                with patch.object(experiment, "_worker", side_effect=AssertionError("Cached graph recomputed")):
                    self.assertEqual(experiment.main(base + ["--johnson", "6,5"]), 0)
                self.assertEqual(experiment.main(base + ["--johnson", "7,1"]), 0)
            with contextlib.closing(sqlite3.connect(output / "experiment.sqlite")) as db:
                signature = json.loads(db.execute("SELECT value FROM metadata WHERE key='signature'").fetchone()[0])
                self.assertEqual(signature["johnson"], [[6, 1], [6, 5], [7, 1]])
                records, _ = experiment.summaries(db)
                self.assertEqual(len(records), 3)
                self.assertTrue(all(r["rc"] == 0 for r in records))

    def test_johnson_generation_and_validation_precede_database_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            base = ["--mode", "families", "--families", "johnson", "--output", str(output)]
            for options in ([], ["--johnson", "8,0"], ["--max-n", "70", "--johnson-max-vertices", "69"],
                            ["--bounds-only", "--heuristic-trials", "0"]):
                with self.subTest(options=options), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    experiment.main(base + options)
            self.assertFalse((output / "experiment.sqlite").exists())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(experiment.main(base + ["--johnson", "7,3", "8,4", "--max-n", "70",
                                                         "--generate-only"]), 0)
            self.assertEqual([len(g) for g in nx.read_graph6(output / "graphs.g6")], [35, 70])
            self.assertFalse((output / "experiment.sqlite").exists())

    def test_generate_grassmann_graphs_without_complexity_search(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            with contextlib.redirect_stdout(io.StringIO()), patch.object(
                    experiment, "_worker", side_effect=AssertionError("Unexpected rc computation")):
                self.assertEqual(experiment.main([
                    "--mode", "families", "--families", "grassmann", "--grassmann", "2,4,2", "2,5,2",
                    "--max-n", "155", "--generate-only", "--output", str(output)]), 0)
            graphs = list(nx.read_graph6(output / "graphs.g6"))
            self.assertEqual([(len(g), g.number_of_edges()) for g in graphs], [(35, 315), (155, 3255)])
            with (output / "graphs.csv").open(encoding="utf-8", newline="") as stream:
                records = list(csv.DictReader(stream))
            self.assertEqual([r["label"] for r in records], ["J_2(4,2)", "J_2(5,2)"])
            self.assertFalse((output / "experiment.sqlite").exists())

    def test_grassmann_parameter_selection_resumes_and_distinguishes_same_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            args = ["--mode", "families", "--families", "grassmann", "--max-n", "7",
                    "--workers", "1", "--output", str(output)]
            with contextlib.redirect_stdout(io.StringIO()), patch.object(experiment, "export"):
                legacy = ["--mode", "families", "--families", "cycle", "--min-n", "3", "--max-n", "3",
                          "--workers", "1", "--output", str(output)]
                self.assertEqual(experiment.main(legacy), 0)
                self.assertEqual(experiment.main(args + ["--grassmann", "2,3,1"]), 0)
                with patch.object(experiment, "_worker", side_effect=AssertionError("Cached graph recomputed")):
                    self.assertEqual(experiment.main(args + ["--grassmann", "2,3,2"]), 0)
                    self.assertEqual(experiment.main(args + ["--grassmann", "2,3,1", "2,3,2"]), 0)
                self.assertEqual(experiment.main(args + ["--grassmann", "4,2,1"]), 0)
                with patch.object(experiment, "_worker", side_effect=AssertionError("Cached cycle recomputed")):
                    self.assertEqual(experiment.main(legacy), 0)
            with contextlib.closing(sqlite3.connect(output / "experiment.sqlite")) as db:
                records, _ = experiment.summaries(db)
                self.assertEqual(len(records), 4)
                self.assertEqual({r["label"] for r in records}, {"cycle", "J_2(3,1)", "J_2(3,2)", "J_4(2,1)"})
                self.assertTrue(all(r["rc"] == 0 for r in records))
                signature = json.loads(db.execute("SELECT value FROM metadata WHERE key='signature'").fetchone()[0])
                self.assertEqual(signature["families"], ["cycle", "grassmann"])
                self.assertEqual(signature["grassmann"], [[2, 3, 1], [2, 3, 2], [4, 2, 1]])

    def test_grassmann_range_and_construction_errors_precede_database_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            base = ["--mode", "families", "--families", "grassmann", "--output", str(output)]
            for options in ([], ["--grassmann", "6,4,2", "--max-n", "35"],
                            ["--max-n", "35", "--grassmann-max-vertices", "34"],
                            ["--max-n", "35", "--generate-only", "--plot-only"]):
                with self.subTest(options=options), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(
                        SystemExit) as raised:
                    experiment.main(base + options)
                self.assertEqual(raised.exception.code, 2)
            self.assertFalse((output / "experiment.sqlite").exists())

    def test_stop_resume_and_skip_completed_graphs(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            args = ["--mode", "atlas", "--max-n", "5", "--workers", "1", "--output", str(output)]
            worker = experiment._worker
            calls = []
            def stop_after_one(*arguments):
                record = worker(*arguments)
                calls.append(record)
                signal.raise_signal(signal.SIGINT)
                return record
            with contextlib.redirect_stdout(io.StringIO()), patch.object(experiment, "export"):
                with patch.object(experiment, "_worker", side_effect=stop_after_one):
                    self.assertEqual(experiment.main(args), 130)
                self.assertEqual(len(calls), 1)
                with contextlib.closing(sqlite3.connect(output / "experiment.sqlite")) as db:
                    self.assertEqual(db.execute("SELECT count(*) FROM results").fetchone()[0], 1)
                self.assertEqual(experiment.main(args), 0)
                with patch.object(experiment, "_worker", side_effect=AssertionError("Unexpected recomputation")):
                    self.assertEqual(experiment.main(args), 0)
            with contextlib.closing(sqlite3.connect(output / "experiment.sqlite")) as db:
                records, summary = experiment.summaries(db)
                self.assertEqual(len(records), 52)
                self.assertTrue(all(row["maximum_certified"] for row in summary))

    def test_incomplete_coverage_and_limits_cannot_certify_maximum(self):
        with tempfile.TemporaryDirectory() as temporary:
            with contextlib.closing(experiment.open_database(Path(temporary) / "test.sqlite", {"engine": "test"})) as db:
                graph = nx.petersen_graph()
                task = {"task_id": "test", "graph6": experiment.graph_code(graph), "label": "test"}
                record = experiment._worker(task, None, 1, "enumeration")
                experiment._coverage(db, 10, 2, True)
                experiment.save_result(db, record)
                _, summary = experiment.summaries(db)
                self.assertFalse(summary[0]["maximum_certified"])
                self.assertEqual(summary[0]["incomplete_count"], 1)
                self.assertEqual(summary[0]["global_upper_bound"], 9)
                experiment._coverage(db, 10, 1, True)
                _, summary = experiment.summaries(db)
                self.assertFalse(summary[0]["maximum_certified"])

    def test_retry_keeps_stronger_previous_bounds(self):
        with tempfile.TemporaryDirectory() as temporary:
            with contextlib.closing(experiment.open_database(Path(temporary) / "test.sqlite", {"engine": "test"})) as db:
                task = {"task_id": "test", "graph6": experiment.graph_code(nx.petersen_graph()), "label": "test"}
                limited = experiment._worker(task, None, 1, "enumeration")
                experiment.save_result(db, {**limited, "lower_bound": 2})
                experiment.save_result(db, limited)
                saved = json.loads(db.execute("SELECT payload FROM results").fetchone()[0])
                self.assertEqual(saved["lower_bound"], 2)
                self.assertIsNone(saved["rc"])
                exact = experiment._worker(task, None, None)
                experiment.save_result(db, exact)
                self.assertEqual(json.loads(db.execute("SELECT payload FROM results").fetchone()[0])["rc"], 3)

    def test_refuses_mixing_datasets(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "test.sqlite"
            experiment.open_database(path, {"seed": 42}).close()
            with self.assertRaises(ValueError):
                experiment.open_database(path, {"seed": 43})

    def test_legacy_family_database_allows_changed_selection_and_keeps_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            previous_signature = {"engine": experiment.ENGINE_VERSION, "mode": "families",
                                  "connected": False, "families": ["cycle", "petersen"]}
            with contextlib.closing(experiment.open_database(output / "experiment.sqlite", previous_signature)) as db:
                for family, graph in [("cycle", nx.cycle_graph(6)), ("petersen", nx.petersen_graph())]:
                    task = {"task_id": f"family:{family}:{len(graph)}",
                            "graph6": experiment.graph_code(graph), "label": family}
                    experiment.save_result(db, experiment._worker(task, None, None))
            args = ["--mode", "families", "--min-n", "6", "--max-n", "10",
                    "--workers", "1", "--output", str(output)]
            with contextlib.redirect_stdout(io.StringIO()), patch.object(experiment, "export"):
                self.assertEqual(experiment.main(args + ["--families", "cube", "cycle"]), 0)
                with patch.object(experiment, "_worker", side_effect=AssertionError("Unexpected recomputation")):
                    self.assertEqual(experiment.main(args + ["--families", "cycle"]), 0)
            with contextlib.closing(sqlite3.connect(output / "experiment.sqlite")) as db:
                records, _ = experiment.summaries(db)
                self.assertEqual(len(records), 7)
                self.assertEqual({r["label"] for r in records}, {"cycle", "cube", "petersen"})
                signature = json.loads(db.execute("SELECT value FROM metadata WHERE key='signature'").fetchone()[0])
                self.assertEqual(signature["families"], ["cube", "cycle", "petersen"])

    def test_cli_dataset_mismatch_explains_difference_without_traceback(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            previous = {"engine": experiment.ENGINE_VERSION, "mode": "random", "connected": False,
                        "seed": 42, "probability": 0.3}
            experiment.open_database(output / "experiment.sqlite", previous).close()
            errors = io.StringIO()
            with contextlib.redirect_stderr(errors), self.assertRaises(SystemExit) as raised:
                experiment.main(["--mode", "random", "--seed", "43", "--output", str(output)])
            self.assertEqual(raised.exception.code, 2)
            self.assertIn("seed: stored=42, requested=43", errors.getvalue())
            self.assertNotIn("Traceback", errors.getvalue())
            with contextlib.closing(sqlite3.connect(output / "experiment.sqlite")) as db:
                saved = json.loads(db.execute("SELECT value FROM metadata WHERE key='signature'").fetchone()[0])
                self.assertEqual(saved, previous)

    def test_padding_propagates_lower_bound_to_larger_orders(self):
        with tempfile.TemporaryDirectory() as temporary:
            with contextlib.closing(experiment.open_database(Path(temporary) / "test.sqlite", {"engine": "test"})) as db:
                for label, graph in [("cube", nx.convert_node_labels_to_integers(nx.hypercube_graph(4))),
                                     ("cycle", nx.cycle_graph(17))]:
                    task = {"task_id": label, "graph6": experiment.graph_code(graph), "label": label}
                    experiment.save_result(db, experiment._worker(task, None, None))
                _, summary = experiment.summaries(db)
                self.assertEqual(summary[1]["observed_lower_bound"], 2)
                self.assertEqual(summary[1]["padded_lower_bound"], 4)
                candidate = nx.from_graph6_bytes(summary[1]["padded_graph6"].encode())
                self.assertEqual(len(candidate), 17)
                self.assertEqual(experiment._worker({"graph6": summary[1]["padded_graph6"]}, None, None)["rc"], 4)


if __name__ == "__main__":
    unittest.main()
