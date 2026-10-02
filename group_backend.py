"""Full automorphism generators and point stabilizers, without group enumeration.

Bliss computes Aut(G)_(S) by giving each vertex of S its own singleton colour.
Generator orbits decide whether identity on S plus x -> y extends. The bounded
LRU caches oracle answers, never merges obstruction-search branches by subgroup.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import random
from time import perf_counter

from relational_complexity import ComplexityResult, is_ultrahomogeneous


@dataclass
class _Stabilizer:
    generators: list
    labels: list[int]
    sizes: list[int]
    order: int | None


def _orbits(n, generators):
    parent = list(range(n))

    def root(v):
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v

    for permutation in generators:
        for v, image in enumerate(permutation):
            a, b = root(v), root(image)
            if a != b:
                parent[b] = a
    labels = [root(v) for v in range(n)]
    sizes = [0] * n
    for label in labels:
        sizes[label] += 1
    return labels, sizes


class StabilizerOracle:
    def __init__(self, graph, check_time, cache_size=512):
        try:
            import igraph
        except ImportError as exc:
            raise ValueError("The bliss backend requires igraph; install requirements-group.txt") from exc
        self.graph = igraph.Graph(n=len(graph), edges=list(graph.edges()), directed=False)
        self.n = len(graph)
        self.check_time = check_time
        self.cache_size = cache_size
        self.cache = OrderedDict()
        self.calls = self.hits = 0

    def get(self, fixed=(), candidates=None):
        self.check_time()
        fixed = tuple(sorted(fixed))
        mask = None if candidates is None else sum(1 << v for v in candidates)
        key = fixed, mask
        if key in self.cache:
            self.hits += 1
            self.cache.move_to_end(key)
            return self.cache[key]
        colors = [0] * self.n
        if candidates is not None:
            for v in candidates:
                colors[v] = 1
        for color, v in enumerate(fixed, 2):
            colors[v] = color
        generators = self.graph.automorphism_group(color=colors)
        self.check_time()
        order = self.graph.count_automorphisms(color=colors) if candidates is None else None
        self.check_time()
        labels, sizes = _orbits(self.n, generators)
        state = _Stabilizer(generators, labels, sizes, order)
        self.calls += 1
        self.cache[key] = state
        if len(self.cache) > self.cache_size:
            self.cache.popitem(last=False)
        return state

    def transporter_size(self, fixed, x, y):
        state = self.get(fixed)
        if state.labels[x] != state.labels[y]:
            return 0
        return state.order // state.sizes[state.labels[x]]


def compute_with_bliss(graph, *, started, timeout, heuristic_trials, search_seed,
                       max_search_nodes, bounds_only, cache_size):
    n = len(graph)
    best, witness = 1, None
    upper = max(0, n - 1)
    group_order = generators = None
    pair_count = search_nodes = heuristic_nodes = 0
    group_seconds = 0.0
    oracle = None

    class NodeLimit(Exception):
        pass

    def check_time():
        if timeout is not None and perf_counter() - started >= timeout:
            raise TimeoutError

    def result(status):
        exact = status == "exact" or best == upper
        elapsed = perf_counter() - started
        return ComplexityResult(n, graph.number_of_edges(), best if exact else None,
                                best, best if exact else upper, "exact" if exact else status,
                                group_order, pair_count, search_nodes, elapsed, witness,
                                backend="bliss", generators=generators,
                                stabilizer_calls=oracle.calls if oracle else 0,
                                cache_hits=oracle.hits if oracle else 0,
                                heuristic_nodes=heuristic_nodes, group_seconds=group_seconds,
                                search_seconds=max(0.0, elapsed - group_seconds))

    if is_ultrahomogeneous(graph):
        best = upper = 0
        return result("exact")

    def save_obstruction(chosen, x, y):
        nonlocal best, witness
        if len(chosen) + 1 <= best:
            return
        # Independently check every deletion before publishing a certificate.
        if oracle.transporter_size(chosen, x, y):
            return
        for v in chosen:
            if not oracle.transporter_size([u for u in chosen if u != v], x, y):
                return
        best = len(chosen) + 1
        witness = {"fixed_vertices": sorted(chosen), "source": x, "target": y}

    try:
        check_time()
        oracle = StabilizerOracle(graph, check_time, cache_size)
        full = oracle.get()
        group_order = full.order
        generators = len(full.generators)
        group_seconds = perf_counter() - started
        upper = min(upper, group_order.bit_length())
        if group_order == 1:
            return result("exact")

        # Ordered pair orbits: representatives of vertex orbits, then orbits
        # of each representative's point stabilizer on its own vertex orbit.
        pairs = []
        seen_vertices = set()
        for x in range(n):
            check_time()
            if full.labels[x] in seen_vertices:
                continue
            seen_vertices.add(full.labels[x])
            point = oracle.get((x,))
            seen_targets = set()
            for y in range(n):
                if y == x or full.labels[x] != full.labels[y] or point.labels[y] in seen_targets:
                    continue
                seen_targets.add(point.labels[y])
                allowed = tuple(v for v in range(n) if v not in (x, y)
                                and graph.has_edge(x, v) == graph.has_edge(y, v))
                transporter = group_order // full.sizes[full.labels[x]]
                bound = min(n - 1, len(allowed) + 1, transporter.bit_length() + 1)
                pairs.append([x, y, allowed, bound])
        pair_count = len(pairs)
        upper = min(upper, max([1] + [pair[3] for pair in pairs]))
        rng = random.Random(search_seed)

        # Give all pair orbits a chance to produce a witness before exhaustively
        # searching any single orbit. Never use sampled generators as Aut(G).
        heuristic_budget = min(2.0, timeout * 0.25) if timeout is not None else 2.0
        heuristic_deadline = perf_counter() + heuristic_budget
        active = []
        for pair in pairs:
            x, y, allowed, bound = pair
            if not allowed or oracle.transporter_size(allowed, x, y):
                pair[3] = 1  # Even fixing every eligible vertex still extends.
                continue
            active.append(pair)
            for trial in range(heuristic_trials):
                if perf_counter() >= heuristic_deadline:
                    break
                order = list(allowed)
                if trial:
                    rng.shuffle(order)
                chosen = []
                compatible = oracle.transporter_size(chosen, x, y)
                for v in order:
                    check_time()
                    heuristic_nodes += 1
                    remaining = oracle.transporter_size([*chosen, v], x, y)
                    if remaining == compatible:
                        continue
                    chosen.append(v)
                    compatible = remaining
                    if not remaining:
                        for u in chosen[:]:
                            subset = [w for w in chosen if w != u]
                            if not oracle.transporter_size(subset, x, y):
                                chosen = subset
                        save_obstruction(chosen, x, y)
                        break
        upper = min(upper, max([1] + [pair[3] for pair in pairs]))
        if bounds_only or best == upper:
            return result("bounded")

        for x, y, allowed, bound in active:
            if bound <= best:
                continue

            def search(chosen, candidates, compatible):
                nonlocal search_nodes
                check_time()
                if max_search_nodes is not None and search_nodes >= max_search_nodes:
                    raise NodeLimit
                search_nodes += 1
                if len(chosen) + len(candidates) + 1 <= best:
                    return
                if len(chosen) + compatible.bit_length() + 1 <= best:
                    return
                candidates = set(candidates)
                while candidates:
                    check_time()
                    # Only use symmetries fixing x,y,S AND preserving the current
                    # candidate set. Inclusion removes one vertex; exclusion
                    # removes its entire orbit. This covers every subset orbit.
                    symmetry = oracle.get((*chosen, x, y), candidates)
                    v = min(candidates)
                    orbit = {u for u in candidates if symmetry.labels[u] == symmetry.labels[v]}
                    child = [*chosen, v]
                    remaining = oracle.transporter_size(child, x, y)
                    if remaining != compatible:
                        if not remaining:
                            save_obstruction(child, x, y)
                        elif all(oracle.transporter_size([u for u in child if u != omit], x, y)
                                 != remaining for omit in chosen):
                            search(child, candidates - {v}, remaining)
                    candidates.difference_update(orbit)
                    if len(chosen) + len(candidates) + 1 <= best:
                        break

            search([], allowed, oracle.transporter_size((), x, y))
        return result("exact")
    except TimeoutError:
        return result("timeout")
    except NodeLimit:
        return result("node_limit")
