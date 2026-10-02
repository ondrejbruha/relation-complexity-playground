import itertools
import unittest

import networkx as nx

from grassmann import _FiniteField, grassmann_graph, grassmann_order, parse_parameters


class GrassmannTests(unittest.TestCase):
    def test_orders_and_parameter_validation(self):
        for parameters, expected in [((2, 4, 2), 35), ((2, 5, 2), 155),
                                     ((2, 6, 2), 651), ((3, 4, 2), 130),
                                     ((4, 4, 2), 357), ((2, 6, 3), 1395)]:
            self.assertEqual(grassmann_order(*parameters), expected)
        self.assertEqual(parse_parameters("2,4,2"), (2, 4, 2))
        for value in ("6,4,2", "1,4,2", "2,4,4", "2,4,0", "2,4", "bad"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_parameters(value)
        with self.assertRaisesRegex(ValueError, "651 vertices"):
            grassmann_graph(2, 6, 2, max_vertices=650)

    def test_prime_and_extension_field_axioms(self):
        for q, characteristic in ((2, 2), (3, 3), (4, 2), (8, 2), (9, 3)):
            field = _FiniteField(q)
            with self.subTest(q=q):
                value = 0
                for _ in range(characteristic):
                    value = field.add[value][1]
                self.assertEqual(value, 0)
                for a in range(q):
                    self.assertEqual(field.add[a][0], a)
                    self.assertEqual(field.add[a][field.neg[a]], 0)
                    if a:
                        self.assertEqual(field.mul[a][field.inv[a]], 1)
                for a, b, c in itertools.product(range(q), repeat=3):
                    self.assertEqual(field.mul[a][field.add[b][c]],
                                     field.add[field.mul[a][b]][field.mul[a][c]])
                    self.assertEqual(field.add[field.add[a][b]][c], field.add[a][field.add[b][c]])
                    self.assertEqual(field.mul[field.mul[a][b]][c], field.mul[a][field.mul[b][c]])

    def test_binary_graph_against_independent_point_set_construction(self):
        # A binary 2-space has exactly three nonzero vectors: a, b, a XOR b.
        # Enumerate arbitrary bases, independently of RREF and hyperplanes.
        spaces = sorted({frozenset((a, b, a ^ b))
                         for a, b in itertools.combinations(range(1, 16), 2)},
                        key=lambda space: tuple(sorted(space)))
        reference = nx.Graph()
        reference.add_nodes_from(range(len(spaces)))
        reference.add_edges_from((i, j) for i, j in itertools.combinations(range(len(spaces)), 2)
                                 if spaces[i] & spaces[j])
        graph = grassmann_graph(2, 4, 2)
        self.assertEqual(len(graph), 35)
        self.assertEqual(graph.number_of_edges(), 315)
        self.assertTrue(nx.is_isomorphic(graph, reference))

    def test_strongly_regular_parameters_including_gf4(self):
        for q, order, degree, adjacent, nonadjacent in ((2, 35, 18, 9, 9),
                                                       (3, 130, 48, 20, 16),
                                                       (4, 357, 100, 35, 25)):
            graph = grassmann_graph(q, 4, 2)
            neighbors = {v: set(graph[v]) for v in graph}
            with self.subTest(q=q):
                self.assertEqual(len(graph), order)
                self.assertEqual(set(dict(graph.degree()).values()), {degree})
                for a, b in itertools.combinations(graph, 2):
                    self.assertEqual(len(neighbors[a] & neighbors[b]),
                                     adjacent if graph.has_edge(a, b) else nonadjacent)

    def test_higher_dimension_distance_layers_and_duality(self):
        graph = grassmann_graph(2, 6, 3)
        self.assertEqual(set(dict(graph.degree()).values()), {98})
        layers = {}
        for distance in nx.single_source_shortest_path_length(graph, 0).values():
            layers[distance] = layers.get(distance, 0) + 1
        self.assertEqual(layers, {0: 1, 1: 98, 2: 784, 3: 512})
        graph = grassmann_graph(2, 5, 2)
        dual = grassmann_graph(2, 5, 3)
        self.assertEqual(set(graph.edges()), set(dual.edges()))
        self.assertEqual(set(dict(graph.degree()).values()), {42})
        self.assertEqual(nx.to_graph6_bytes(graph), nx.to_graph6_bytes(grassmann_graph(2, 5, 2)))


if __name__ == "__main__":
    unittest.main()
