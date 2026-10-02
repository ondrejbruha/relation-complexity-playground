"""Exact structural relational complexity of finite simple, uncoloured graphs.

The original binary edge relation is retained. Already ultrahomogeneous graphs
have rc=0. This is not the k-closure of the automorphism group (which is always
2-closed for a graph). See docs/algorithm.md for the obstruction algorithm proof.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from time import perf_counter

import networkx as nx

ENGINE_VERSION = "minimal-obstructions-v1"


@dataclass
class ComplexityResult:
    n: int
    edges: int
    rc: int | None
    lower_bound: int
    upper_bound: int
    status: str
    automorphisms: int | None
    pair_orbits: int
    search_nodes: int
    seconds: float
    witness: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _equal_cliques(graph: nx.Graph) -> bool:
    sizes = set()
    for component in nx.connected_components(graph):
        size = len(component)
        if graph.subgraph(component).number_of_edges() != size * (size - 1) // 2:
            return False
        sizes.add(size)
    return len(sizes) <= 1


def is_ultrahomogeneous(graph: nx.Graph) -> bool:
    """Recognize finite ultrahomogeneous graphs using Gardiner's classification."""
    n = len(graph)
    if _equal_cliques(graph) or _equal_cliques(nx.complement(graph)):
        return True
    if n == 5 and nx.is_connected(graph) and all(d == 2 for _, d in graph.degree()):
        return True
    return n == 9 and nx.is_isomorphic(graph, nx.line_graph(nx.complete_bipartite_graph(3, 3)))


def compute_relational_complexity(
    graph: nx.Graph,
    *,
    timeout: float | None = 30.0,
    max_automorphisms: int | None = 100_000,
) -> ComplexityResult:
    """Return an exact value, or explicit proven bounds if a limit is reached.

    Limits are cooperative, including during NetworkX automorphism enumeration.
    Node/edge attributes are ignored; directed graphs, multigraphs and loops are
    rejected. Witness vertex numbers refer to list(graph.nodes()) order.
    """
    if graph.is_directed() or graph.is_multigraph() or nx.number_of_selfloops(graph):
        raise ValueError("Only simple undirected graphs without loops are supported.")
    if timeout is not None and timeout <= 0:
        raise ValueError("timeout must be positive or None")
    if max_automorphisms is not None and max_automorphisms < 1:
        raise ValueError("max_automorphisms must be positive or None")
    # Rebuild to deliberately ignore arbitrary input attributes.
    nodes = list(graph.nodes())
    indices = {v: i for i, v in enumerate(nodes)}
    g = nx.Graph()
    g.add_nodes_from(range(len(nodes)))
    g.add_edges_from((indices[u], indices[v]) for u, v in graph.edges())
    started = perf_counter()
    n = len(g)
    best, witness = 1, None
    aut_count = None
    pair_count = search_nodes = 0

    def result(status: str) -> ComplexityResult:
        exact = status == "exact"
        return ComplexityResult(n, g.number_of_edges(), best if exact else None,
                                best, best if exact else max(0, n - 1), status,
                                aut_count, pair_count, search_nodes,
                                perf_counter() - started, witness)

    def check_time() -> None:
        if timeout is not None and perf_counter() - started >= timeout:
            raise TimeoutError

    if is_ultrahomogeneous(g):
        best = 0
        return result("exact")

    try:
        automorphisms = []
        matcher = nx.algorithms.isomorphism.GraphMatcher(g, g)
        for mapping in matcher.isomorphisms_iter():
            check_time()
            if max_automorphisms is not None and len(automorphisms) >= max_automorphisms:
                return result("automorphism_limit")
            automorphisms.append(tuple(mapping[i] for i in range(n)))
        aut_count = len(automorphisms)
        if aut_count == 1:  # Unary singleton orbits distinguish all vertices.
            return result("exact")

        # transport[x][y]: bits for automorphisms taking x to y.
        transport = [[0] * n for _ in range(n)]
        for index, permutation in enumerate(automorphisms):
            check_time()
            bit = 1 << index
            for x, y in enumerate(permutation):
                transport[x][y] |= bit
        fixed = [transport[v][v] for v in range(n)]

        # Only one ordered pair per Aut(G)-orbit needs to be considered.
        seen_pairs = set()
        for x in range(n):
            for y in range(n):
                check_time()
                if x == y or not transport[x][y] or (x, y) in seen_pairs:
                    continue
                seen_pairs.update((p[x], p[y]) for p in automorphisms)
                pair_count += 1
                # identity on S plus x -> y must be an induced graph isomorphism.
                allowed = [v for v in range(n) if v != x and v != y
                           and g.has_edge(x, v) == g.has_edge(y, v)]
                # Strong constraints first; no effect on correctness.
                allowed.sort(key=lambda v: (fixed[v] & transport[x][y]).bit_count())
                chosen: list[int] = []

                def search(start: int, compatible: int) -> None:
                    nonlocal best, witness, search_nodes
                    check_time()
                    search_nodes += 1
                    # Even using all remaining vertices cannot improve the answer.
                    if len(chosen) + len(allowed) - start + 1 <= best:
                        return
                    for pos in range(start, len(allowed)):
                        check_time()
                        v = allowed[pos]
                        remaining = compatible & fixed[v]
                        if remaining == compatible:
                            continue  # Redundant constraints cannot be minimal.
                        chosen.append(v)
                        if remaining:
                            search(pos + 1, remaining)
                        elif len(chosen) + 1 > best:
                            # Is every one-vertex deletion extendable? Prefix/suffix
                            # intersections avoid a quadratic number of ANDs.
                            prefix = [transport[x][y]]
                            for u in chosen:
                                prefix.append(prefix[-1] & fixed[u])
                            suffix = (1 << aut_count) - 1
                            minimal = True
                            for i in range(len(chosen) - 1, -1, -1):
                                if not (prefix[i] & suffix):
                                    minimal = False
                                    break
                                suffix &= fixed[chosen[i]]
                            if minimal:
                                best = len(chosen) + 1
                                witness = {"fixed_vertices": sorted(chosen),
                                           "source": x, "target": y}
                        chosen.pop()

                search(0, transport[x][y])
        return result("exact")
    except TimeoutError:
        return result("timeout")


def relational_complexity(graph: nx.Graph, verbose: bool = False, **kwargs) -> int:
    """Convenient exact-only API; raises rather than returning a bound as a value."""
    result = compute_relational_complexity(graph, **kwargs)
    if verbose:
        print(result.to_dict())
    if result.rc is None:
        raise RuntimeError(f"{result.status}: {result.lower_bound} <= rc <= {result.upper_bound}")
    return result.rc
