import itertools
import unittest

import networkx as nx

from johnson import johnson_graph, johnson_order, parse_parameters


class JohnsonTests(unittest.TestCase):
    def test_construction_against_independent_intersection_definition(self):
        for m, k in ((5, 2), (6, 3), (8, 4)):
            graph = johnson_graph(m, k)
            subsets = list(map(set, itertools.combinations(range(m), k)))
            for i in range(len(subsets)):
                for j in range(i):
                    self.assertEqual(graph.has_edge(i, j), len(subsets[i] & subsets[j]) == k - 1)
            self.assertEqual(set(dict(graph.degree()).values()), {k * (m - k)})

    def test_duality_small_cases_and_validation(self):
        self.assertEqual(johnson_order(8, 4), 70)
        self.assertEqual(parse_parameters("8,4"), (8, 4))
        self.assertTrue(nx.is_isomorphic(johnson_graph(6, 4), johnson_graph(6, 2)))
        self.assertTrue(nx.is_isomorphic(johnson_graph(7, 1), nx.complete_graph(7)))
        for value in ("6,0", "4,4", "x,2", "2,3,4"):
            with self.assertRaises(ValueError):
                parse_parameters(value)
        with self.assertRaises(ValueError):
            johnson_graph(8, 4, max_vertices=69)
