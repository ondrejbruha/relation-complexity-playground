import contextlib
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
                record = experiment._worker(task, None, 1)
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
                limited = experiment._worker(task, None, 1)
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
