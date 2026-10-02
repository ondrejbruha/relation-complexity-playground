import itertools
import unittest

import networkx as nx

from relational_complexity import compute_relational_complexity, relational_complexity


def reference_complexity(graph):
    """Independent exhaustive test over ALL induced partial isomorphisms.

    A minimal nonextendable partial graph isomorphism of size r forces rc >= r.
    Deliberately does not use the optimized identity-on-S normalization.
    """
    n = len(graph)
    autos = list(nx.algorithms.isomorphism.GraphMatcher(graph, graph).isomorphisms_iter())
    answer = 0
    for r in range(1, n):
        for domain in itertools.combinations(range(n), r):
            for image in itertools.permutations(range(n), r):
                if any(graph.has_edge(domain[i], domain[j]) != graph.has_edge(image[i], image[j])
                       for i in range(r) for j in range(i)):
                    continue
                if any(all(a[x] == y for x, y in zip(domain, image)) for a in autos):
                    continue
                if all(any(all(a[domain[i]] == image[i] for i in range(r) if i != omit)
                           for a in autos) for omit in range(r)):
                    answer = max(answer, r)
    return answer


class ComplexityTests(unittest.TestCase):
    def test_all_graphs_through_six_against_independent_reference(self):
        for index, graph in enumerate(nx.graph_atlas_g()):
            if len(graph) > 6:
                break
            with self.subTest(index=index):
                self.assertEqual(relational_complexity(graph, timeout=None), reference_complexity(graph))

    def test_known_values(self):
        for graph, expected in [(nx.complete_graph(20), 0), (nx.empty_graph(20), 0),
                                (nx.cycle_graph(5), 0), (nx.cycle_graph(6), 2),
                                (nx.path_graph(3), 1), (nx.petersen_graph(), 3),
                                (nx.line_graph(nx.complete_bipartite_graph(3, 3)), 0),
                                (nx.disjoint_union(nx.cycle_graph(5), nx.cycle_graph(5)), 2)]:
            with self.subTest(n=len(graph), edges=graph.number_of_edges()):
                self.assertEqual(relational_complexity(graph, timeout=None), expected)

    def test_complement_and_relabelling(self):
        graph = nx.petersen_graph()
        self.assertEqual(relational_complexity(nx.complement(graph)), 3)
        labelled = nx.relabel_nodes(graph, {v: f"vertex-{9-v}" for v in graph})
        self.assertEqual(relational_complexity(labelled), 3)

    def test_witness_is_minimal(self):
        graph = nx.petersen_graph()
        result = compute_relational_complexity(graph)
        witness = result.witness
        self.assertIsNotNone(witness)
        mapping = {v: v for v in witness["fixed_vertices"]}
        mapping[witness["source"]] = witness["target"]
        self.assertEqual(len(mapping), result.rc)
        autos = list(nx.algorithms.isomorphism.GraphMatcher(graph, graph).isomorphisms_iter())
        self.assertFalse(any(all(a[x] == y for x, y in mapping.items()) for a in autos))
        for omit in mapping:
            self.assertTrue(any(all(a[x] == y for x, y in mapping.items() if x != omit) for a in autos))

    def test_limits_are_not_reported_as_exact_values(self):
        for kwargs, status in [({"max_automorphisms": 1}, "automorphism_limit"),
                               ({"timeout": 1e-12}, "timeout")]:
            result = compute_relational_complexity(nx.petersen_graph(), **kwargs)
            self.assertIsNone(result.rc)
            self.assertEqual(result.status, status)
            self.assertLessEqual(result.lower_bound, 3)
            self.assertGreaterEqual(result.upper_bound, 3)

    def test_rejects_unsupported_graph_types(self):
        for graph in (nx.DiGraph([(0, 1)]), nx.MultiGraph([(0, 1)]), nx.Graph([(0, 0)])):
            with self.assertRaises(ValueError):
                relational_complexity(graph)


if __name__ == "__main__":
    unittest.main()
