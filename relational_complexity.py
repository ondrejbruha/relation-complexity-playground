"""Exact structural relational complexity of finite simple, uncoloured graphs.

The original binary edge relation is retained. Already ultrahomogeneous graphs
have rc=0. This is not the k-closure of the automorphism group (which is always
2-closed for a graph). See docs/algorithm.md for the obstruction algorithm proof.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from collections import Counter
import importlib.util
from time import perf_counter

import networkx as nx

ENGINE_VERSION = "minimal-obstructions-v1"
BACKENDS = ("auto", "enumeration", "bliss")


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
    backend: str = "enumeration"
    generators: int | None = None
    stabilizer_calls: int = 0
    cache_hits: int = 0
    heuristic_nodes: int = 0
    group_seconds: float = 0.0
    search_seconds: float = 0.0

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


def _compute_enumerated(
    graph: nx.Graph,
    *,
    timeout: float | None = 30.0,
    max_automorphisms: int | None = 100_000,
    heuristic_trials: int = 0,
    search_seed: int = 0,
    max_search_nodes: int | None = None,
    bounds_only: bool = False,
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
    heuristic_nodes = 0
    group_seconds = 0.0
    upper = max(0, n - 1)

    class NodeLimit(Exception):
        pass

    def result(status: str) -> ComplexityResult:
        exact = status == "exact" or best == upper
        return ComplexityResult(n, g.number_of_edges(), best if exact else None,
                                best, best if exact else upper, "exact" if exact else status,
                                aut_count, pair_count, search_nodes,
                                perf_counter() - started, witness,
                                heuristic_nodes=heuristic_nodes, group_seconds=group_seconds,
                                search_seconds=max(0.0, perf_counter() - started - group_seconds))

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
        group_seconds = perf_counter() - started
        # Each essential fixed vertex strictly decreases a point stabilizer.
        upper = min(upper, aut_count.bit_length())
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
        import random
        rng = random.Random(search_seed)

        def save_obstruction(chosen, x, y):
            nonlocal best, witness
            if len(chosen) + 1 <= best:
                return
            prefix = [transport[x][y]]
            for u in chosen:
                prefix.append(prefix[-1] & fixed[u])
            suffix = (1 << aut_count) - 1
            for i in range(len(chosen) - 1, -1, -1):
                if not (prefix[i] & suffix):
                    return
                suffix &= fixed[chosen[i]]
            best = len(chosen) + 1
            witness = {"fixed_vertices": sorted(chosen), "source": x, "target": y}

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
                for trial in range(heuristic_trials):
                    check_time()
                    order = allowed[:]
                    if trial:
                        rng.shuffle(order)
                    candidate = []
                    compatible = transport[x][y]
                    for v in order:
                        check_time()
                        heuristic_nodes += 1
                        remaining = compatible & fixed[v]
                        if remaining == compatible:
                            continue
                        candidate.append(v)
                        compatible = remaining
                        if not compatible:
                            for u in candidate[:]:
                                check_time()
                                other = transport[x][y]
                                for w in candidate:
                                    if w != u:
                                        other &= fixed[w]
                                if not other:
                                    candidate.remove(u)
                            save_obstruction(candidate, x, y)
                            break
                if bounds_only:
                    continue
                chosen: list[int] = []

                def search(start: int, compatible: int) -> None:
                    nonlocal best, witness, search_nodes
                    check_time()
                    if max_search_nodes is not None and search_nodes >= max_search_nodes:
                        raise NodeLimit
                    search_nodes += 1
                    # Even using all remaining vertices cannot improve the answer.
                    if len(chosen) + len(allowed) - start + 1 <= best:
                        return
                    # Every nonempty strict transporter intersection at least
                    # halves its size; at most one final empty step remains.
                    if len(chosen) + compatible.bit_count().bit_length() + 1 <= best:
                        return
                    for pos in range(start, len(allowed)):
                        check_time()
                        v = allowed[pos]
                        remaining = compatible & fixed[v]
                        if remaining == compatible:
                            continue  # Redundant constraints cannot be minimal.
                        chosen.append(v)
                        if remaining:
                            # A previously selected condition that is now redundant
                            # can never become essential again after more ANDs.
                            essential = True
                            for omit in chosen[:-1]:
                                other = transport[x][y]
                                for u in chosen:
                                    if u != omit:
                                        other &= fixed[u]
                                if other == remaining:
                                    essential = False
                                    break
                            if essential:
                                search(pos + 1, remaining)
                        elif len(chosen) + 1 > best:
                            save_obstruction(chosen, x, y)
                        chosen.pop()

                search(0, transport[x][y])
        return result("exact" if not bounds_only or best == upper else "bounded")
    except TimeoutError:
        return result("timeout")
    except NodeLimit:
        return result("node_limit")


def compute_relational_complexity(
    graph: nx.Graph,
    *,
    timeout: float | None = 30.0,
    max_automorphisms: int | None = 100_000,
    backend: str = "auto",
    heuristic_trials: int = 8,
    search_seed: int = 0,
    max_search_nodes: int | None = None,
    bounds_only: bool = False,
    cache_size: int = 512,
) -> ComplexityResult:
    """Compute structural rc, preserving certified bounds on interruption.

    Auto uses enumeration through n=9 and Bliss for larger graphs when igraph is
    installed. Explicit enumeration remains available for independent comparisons.
    max_automorphisms applies only to enumeration, not to a generated group's order.
    bounds_only runs verified witness search without exhaustive certification.
    Limits are cooperative, including native graph-isomorphism calls.
    """
    if graph.is_directed() or graph.is_multigraph() or nx.number_of_selfloops(graph):
        raise ValueError("Only simple undirected graphs without loops are supported.")
    if backend not in BACKENDS:
        raise ValueError(f"backend must be one of {BACKENDS}")
    if timeout is not None and timeout <= 0:
        raise ValueError("timeout must be positive or None")
    if max_automorphisms is not None and max_automorphisms < 1:
        raise ValueError("max_automorphisms must be positive or None")
    if heuristic_trials < 0 or cache_size < 1:
        raise ValueError("heuristic_trials must be nonnegative and cache_size positive")
    if max_search_nodes is not None and max_search_nodes < 1:
        raise ValueError("max_search_nodes must be positive or None")
    if bounds_only and heuristic_trials == 0:
        raise ValueError("bounds_only requires at least one heuristic trial")
    started = perf_counter()
    # Deliberately discard attributes; witness indices follow the input node order.
    nodes = list(graph)
    indices = {v: i for i, v in enumerate(nodes)}
    g = nx.Graph()
    g.add_nodes_from(range(len(nodes)))
    g.add_edges_from((indices[u], indices[v]) for u, v in graph.edges())
    if backend != "enumeration" and len(g) >= 6 and all(d == 2 for _, d in g.degree()) and nx.is_connected(g):
        # Cycles are metrically ultrahomogeneous, so invariant distances give
        # rc <= 2. Fix the fourth vertex while sending the first to the second:
        # both pairs are nonedges, but distances 3 and 2 prohibit extension.
        first = 0
        second = next(iter(g[first]))
        third = next(v for v in g[second] if v != first)
        fourth = next(v for v in g[third] if v != second)
        return ComplexityResult(len(g), g.number_of_edges(), 2, 2, 2, "exact", 2 * len(g),
                                0, 0, perf_counter() - started,
                                {"fixed_vertices": [fourth], "source": first, "target": second},
                                backend="cycle")
    selected = backend
    if selected == "auto":
        selected = "bliss" if (len(g) > 9 and importlib.util.find_spec("igraph") is not None) else "enumeration"
    if selected == "bliss":
        from group_backend import compute_with_bliss
        return compute_with_bliss(g, started=started, timeout=timeout,
                                  heuristic_trials=heuristic_trials, search_seed=search_seed,
                                  max_search_nodes=max_search_nodes, bounds_only=bounds_only,
                                  cache_size=cache_size)
    return _compute_enumerated(g, timeout=timeout, max_automorphisms=max_automorphisms,
                              heuristic_trials=heuristic_trials if bounds_only else 0,
                              search_seed=search_seed, max_search_nodes=max_search_nodes,
                              bounds_only=bounds_only)


def _refine_isomorphism_colors(graph, domain, image, check_time):
    """Joint 1-WL refinement; differing cell counts prove nonisomorphism."""
    while True:
        check_time()
        old_count = len(set(domain) | set(image))
        signatures = {}
        refined = []
        for colors in (domain, image):
            side = []
            for v in range(len(graph)):
                check_time()
                neighbors = tuple(sorted(Counter(colors[u] for u in graph[v]).items()))
                signature = colors[v], neighbors
                side.append(signatures.setdefault(signature, len(signatures)))
            refined.append(side)
        domain, image = refined
        if Counter(domain) != Counter(image):
            return None
        if len(signatures) == old_count:
            return domain, image


def verify_witness(graph: nx.Graph, witness: dict | None, *, timeout: float | None = 30.0) -> bool:
    """Independently verify a minimal obstruction using constrained isomorphism.

    Uses colour refinement and VF2 rather than Bliss stabilizer orbits; may still
    be expensive on large graphs. A cooperative limit raises TimeoutError rather
    than returning False for a certificate that was not fully checked.
    Coordinates refer to the input node order, as in ComplexityResult.witness.
    """
    if not isinstance(witness, dict):
        return False
    if timeout is not None and timeout <= 0:
        raise ValueError("timeout must be positive or None")
    started = perf_counter()

    def check_time():
        if timeout is not None and perf_counter() - started >= timeout:
            raise TimeoutError("Independent witness verification exceeded its timeout")
    if graph.is_directed() or graph.is_multigraph() or nx.number_of_selfloops(graph):
        raise ValueError("Only simple undirected graphs without loops are supported.")
    fixed = witness.get("fixed_vertices")
    x, y = witness.get("source"), witness.get("target")
    n = len(graph)
    if not isinstance(fixed, list) or any(type(v) is not int or not 0 <= v < n for v in [*fixed, x, y]):
        return False
    if len(set(fixed)) != len(fixed) or x == y or x in fixed or y in fixed:
        return False
    nodes = list(graph)
    graph = nx.relabel_nodes(graph, {v: i for i, v in enumerate(nodes)}, copy=True)
    if any(graph.has_edge(x, v) != graph.has_edge(y, v) for v in fixed):
        return False
    native = None
    if importlib.util.find_spec("igraph") is not None:
        import igraph
        native = igraph.Graph(n=n, edges=list(graph.edges()), directed=False)

    def extends(vertices):
        check_time()
        domain, image = [0] * n, [0] * n
        for color, v in enumerate(vertices, 1):
            domain[v] = image[v] = color
        domain[x] = image[y] = len(vertices) + 1
        refined = _refine_isomorphism_colors(graph, domain, image, check_time)
        if refined is None:
            return False
        domain, image = refined
        if native is not None:
            expired = False
            def compatible(*args):
                nonlocal expired
                # igraph ignores exceptions raised inside compatibility callbacks.
                # Reject every remaining candidate to unwind the native search,
                # then raise on the Python side rather than returning False.
                if expired or (timeout is not None and perf_counter() - started >= timeout):
                    expired = True
                    return False
                return True
            matched = native.isomorphic_vf2(native, color1=domain, color2=image,
                                            node_compat_fn=compatible if timeout is not None else None)
            if expired:
                raise TimeoutError("Independent witness verification exceeded its timeout")
            check_time()
            return matched
        left, right = nx.Graph(), nx.Graph()
        for v in range(n):
            left.add_node(v, color=domain[v])
            right.add_node(v, color=image[v])
        left.add_edges_from(graph.edges())
        right.add_edges_from(graph.edges())
        def node_match(a, b):
            check_time()
            return a["color"] == b["color"]
        return nx.is_isomorphic(left, right, node_match=node_match)

    return not extends(fixed) and extends([]) and all(extends([u for u in fixed if u != v]) for v in fixed)


def relational_complexity(graph: nx.Graph, verbose: bool = False, **kwargs) -> int:
    """Convenient exact-only API; raises rather than returning a bound as a value."""
    result = compute_relational_complexity(graph, **kwargs)
    if verbose:
        print(result.to_dict())
    if result.rc is None:
        raise RuntimeError(f"{result.status}: {result.lower_bound} <= rc <= {result.upper_bound}")
    return result.rc
