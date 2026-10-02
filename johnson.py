"""Johnson graphs from k-subsets, using single-element replacements for edges."""
from __future__ import annotations

import itertools
import math
import networkx as nx

DEFAULT_PARAMETERS = ((8, 4),)
DEFAULT_MAX_VERTICES = 2_000


def johnson_order(m: int, k: int) -> int:
    if type(m) is not int or type(k) is not int or not 1 <= k < m:
        raise ValueError("Johnson parameters require integers 1 <= k < m")
    return math.comb(m, k)


def parse_parameters(value: str) -> tuple[int, int]:
    try:
        m, k = map(int, value.split(","))
    except ValueError as exc:
        raise ValueError("Use an m,k pair, for example 8,4") from exc
    johnson_order(m, k)
    return m, k


def johnson_graph(m: int, k: int, *, max_vertices: int = DEFAULT_MAX_VERTICES) -> nx.Graph:
    order = johnson_order(m, k)
    if max_vertices < 1 or order > max_vertices:
        raise ValueError(f"J({m},{k}) has {order} vertices; construction limit is {max_vertices}")
    original_k, k = k, min(k, m - k)
    masks = [sum(1 << v for v in subset) for subset in itertools.combinations(range(m), k)]
    indices = {mask: i for i, mask in enumerate(masks)}
    graph = nx.Graph()
    graph.add_nodes_from(range(order))
    for vertex, mask in enumerate(masks):
        for removed in range(m):
            if not mask & (1 << removed):
                continue
            for added in range(m):
                if mask & (1 << added):
                    continue
                neighbor = indices[mask ^ (1 << removed) ^ (1 << added)]
                if vertex < neighbor:
                    graph.add_edge(vertex, neighbor)
    graph.graph.update(name=f"J({m},{original_k})", ground_set_size=m, subset_size=original_k)
    return graph
