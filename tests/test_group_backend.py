import importlib.util
import itertools
import unittest
from unittest.mock import patch

import networkx as nx

from grassmann import grassmann_graph
from relational_complexity import compute_relational_complexity, verify_witness


@unittest.skipUnless(importlib.util.find_spec("igraph"), "Optional igraph backend not installed")
class GroupBackendTests(unittest.TestCase):
    def test_all_atlas_graphs_against_enumeration_without_heuristics(self):
        for index, graph in enumerate(nx.graph_atlas_g()):
            with self.subTest(index=index):
                old = compute_relational_complexity(graph, backend="enumeration", timeout=None)
                new = compute_relational_complexity(graph, backend="bliss", heuristic_trials=0, timeout=None)
                self.assertEqual(new.rc, old.rc)
                if new.witness:
                    self.assertTrue(verify_witness(graph, new.witness))

    def test_stabilizers_and_transporter_sizes_against_full_group(self):
        from group_backend import StabilizerOracle
        graph = nx.petersen_graph()
        autos = list(nx.algorithms.isomorphism.GraphMatcher(graph, graph).isomorphisms_iter())
        oracle = StabilizerOracle(graph, lambda: None, cache_size=4)
        for r in range(4):
            for fixed in itertools.combinations(range(10), r):
                selected = [a for a in autos if all(a[v] == v for v in fixed)]
                state = oracle.get(fixed)
                self.assertEqual(state.order, len(selected))
                for y in range(10):
                    self.assertEqual(oracle.transporter_size(fixed, 0, y), sum(a[0] == y for a in selected))
        self.assertLessEqual(len(oracle.cache), 4)
        self.assertGreater(oracle.hits, 0)

    def test_larger_examples_and_independent_vf2_certificates(self):
        for graph, expected in [(nx.hypercube_graph(4), 4),
                                (nx.line_graph(nx.complete_bipartite_graph(6, 6)), 4),
                                (grassmann_graph(2, 4, 2), 5)]:
            with self.subTest(n=len(graph)):
                result = compute_relational_complexity(graph, backend="bliss", timeout=15)
                self.assertEqual(result.rc, expected)
                self.assertTrue(verify_witness(graph, result.witness))
                self.assertEqual(len(result.witness["fixed_vertices"]) + 1, expected)

    def test_symmetry_and_cache_eviction_preserve_value(self):
        graph = nx.hypercube_graph(4)
        for modified in (graph, nx.complement(graph), nx.relabel_nodes(graph, {v: str(v) for v in graph})):
            result = compute_relational_complexity(modified, backend="bliss", heuristic_trials=0,
                                                   cache_size=2, timeout=15)
            self.assertEqual(result.rc, 4)
            self.assertTrue(verify_witness(modified, result.witness))

    def test_heuristic_and_node_limits_keep_verified_bounds(self):
        graph = nx.hypercube_graph(4)
        for options, status in [({"bounds_only": True}, "bounded"),
                                ({"max_search_nodes": 1}, "node_limit")]:
            result = compute_relational_complexity(graph, backend="bliss", timeout=None, **options)
            self.assertIsNone(result.rc)
            self.assertEqual(result.status, status)
            self.assertEqual(result.lower_bound, 4)
            self.assertGreaterEqual(result.upper_bound, 4)
            self.assertTrue(verify_witness(graph, result.witness))
        expired = compute_relational_complexity(graph, backend="bliss", timeout=1e-12)
        self.assertEqual(expired.status, "timeout")
        self.assertIsNone(expired.rc)

    def test_large_group_does_not_hit_enumeration_limit(self):
        result = compute_relational_complexity(nx.line_graph(nx.complete_bipartite_graph(6, 6)),
                                               backend="bliss", max_automorphisms=1, timeout=15)
        self.assertEqual(result.rc, 4)
        self.assertEqual(result.automorphisms, 1_036_800)
        self.assertLess(result.generators, 20)


class WitnessAndDispatchTests(unittest.TestCase):
    def test_auto_falls_back_when_optional_backend_is_missing(self):
        with patch("relational_complexity.importlib.util.find_spec", return_value=None):
            result = compute_relational_complexity(nx.petersen_graph())
            self.assertEqual((result.backend, result.rc), ("enumeration", 3))
            self.assertTrue(verify_witness(nx.petersen_graph(), result.witness))

    def test_missing_explicit_backend_has_actionable_error(self):
        with patch.dict("sys.modules", {"igraph": None}):
            with self.assertRaisesRegex(ValueError, "requirements-group.txt"):
                compute_relational_complexity(nx.petersen_graph(), backend="bliss")

    def test_cycle_shortcut_and_witness_on_large_relabelled_graph(self):
        graph = nx.relabel_nodes(nx.cycle_graph(1000), {v: f"v{v}" for v in range(1000)})
        result = compute_relational_complexity(graph)
        self.assertEqual((result.rc, result.backend, result.automorphisms), (2, "cycle", 2000))
        self.assertTrue(verify_witness(graph, result.witness))

    def test_malformed_and_nonminimal_certificates_are_rejected(self):
        graph = nx.petersen_graph()
        for witness in (None, {}, {"fixed_vertices": [3, 3], "source": 0, "target": 1},
                        {"fixed_vertices": [], "source": 0, "target": 1},
                        {"fixed_vertices": [100], "source": 0, "target": 1},
                        {"fixed_vertices": [1], "source": 0, "target": 1}):
            self.assertFalse(verify_witness(graph, witness))

    def test_enumeration_bounds_mode_and_node_limit(self):
        for options in ({"bounds_only": True}, {"max_search_nodes": 1}):
            result = compute_relational_complexity(nx.hypercube_graph(4), backend="enumeration",
                                                   timeout=None, **options)
            self.assertIsNone(result.rc)
            self.assertLessEqual(result.lower_bound, 4)
            self.assertGreaterEqual(result.upper_bound, 4)
            if result.witness:
                self.assertTrue(verify_witness(nx.hypercube_graph(4), result.witness))

    def test_invalid_search_options(self):
        for options in ({"backend": "unknown"}, {"cache_size": 0}, {"heuristic_trials": -1},
                        {"max_search_nodes": 0}, {"bounds_only": True, "heuristic_trials": 0}):
            with self.assertRaises(ValueError):
                compute_relational_complexity(nx.petersen_graph(), **options)

    def test_certificate_verification_timeout_is_not_false(self):
        graph = nx.petersen_graph()
        result = compute_relational_complexity(graph)
        with self.assertRaises(TimeoutError):
            verify_witness(graph, result.witness, timeout=1e-12)
        with self.assertRaises(ValueError):
            verify_witness(graph, result.witness, timeout=0)
        self.assertTrue(verify_witness(graph, result.witness, timeout=None))
        # Force expiry during native matching, bypassing refinement. The native
        # callback must unwind without throwing an ignored C callback exception.
        with patch("relational_complexity._refine_isomorphism_colors",
                   side_effect=lambda graph, domain, image, check: (domain, image)), patch(
                   "relational_complexity.perf_counter", side_effect=itertools.count(0, 0.1)):
            with self.assertRaises(TimeoutError):
                verify_witness(graph, result.witness, timeout=0.25)
