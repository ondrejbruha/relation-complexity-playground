"""Grassmann graphs over finite fields, constructed from subspace incidence.

No additional dependencies are required. Extension fields use a deterministic
polynomial basis over their prime field, rather than arithmetic modulo q.
"""
from __future__ import annotations

import itertools
import math

import networkx as nx

DEFAULT_MAX_VERTICES = 2_000
DEFAULT_PARAMETERS = ((2, 4, 2),)


def _prime_power(q: int) -> tuple[int, int]:
    if not isinstance(q, int) or isinstance(q, bool) or q < 2:
        raise ValueError("q must be a prime power >= 2")
    p = next((p for p in range(2, math.isqrt(q) + 1) if q % p == 0), q)
    remainder, exponent = q, 0
    while remainder % p == 0:
        remainder //= p
        exponent += 1
    if remainder != 1:
        raise ValueError(f"q={q} is not a prime power")
    return p, exponent


def grassmann_order(q: int, d: int, k: int) -> int:
    """Number of vertices of J_q(d,k), the Gaussian binomial coefficient."""
    _prime_power(q)
    if not isinstance(d, int) or not isinstance(k, int) or not 1 <= k < d:
        raise ValueError("Grassmann parameters require 1 <= k < d")
    answer = 1
    for i in range(min(k, d - k)):
        answer = answer * (q ** (d - i) - 1) // (q ** (i + 1) - 1)
    return answer


def parse_parameters(value: str) -> tuple[int, int, int]:
    """Parse one CLI q,d,k triple and validate its mathematical parameters."""
    try:
        q, d, k = map(int, value.split(","))
    except ValueError as exc:
        raise ValueError("Use a q,d,k triple, for example 2,4,2") from exc
    grassmann_order(q, d, k)
    return q, d, k


def _remainder(coefficients, divisor, p):
    coefficients = list(coefficients)
    while coefficients and coefficients[-1] == 0:
        coefficients.pop()
    while len(coefficients) >= len(divisor):
        factor, shift = coefficients[-1], len(coefficients) - len(divisor)
        for i, value in enumerate(divisor):
            coefficients[i + shift] = (coefficients[i + shift] - factor * value) % p
        while coefficients and coefficients[-1] == 0:
            coefficients.pop()
    return coefficients


class _FiniteField:
    def __init__(self, q):
        p, exponent = _prime_power(q)
        if exponent == 1:
            self.add = [[(a + b) % p for b in range(q)] for a in range(q)]
            self.mul = [[a * b % p for b in range(q)] for a in range(q)]
        else:
            divisors = [(*coefficients, 1) for degree in range(1, exponent // 2 + 1)
                        for coefficients in itertools.product(range(p), repeat=degree)]
            polynomial = next((*coefficients, 1)
                              for coefficients in itertools.product(range(p), repeat=exponent)
                              if coefficients[0] and all(
                                  _remainder((*coefficients, 1), divisor, p) for divisor in divisors))
            digits = [tuple(a // p ** i % p for i in range(exponent)) for a in range(q)]

            def encode(values):
                return sum(value * p ** i for i, value in enumerate(values))

            self.add = [[encode([(x + y) % p for x, y in zip(a, b)])
                         for b in digits] for a in digits]
            self.mul = []
            for a in digits:
                row = []
                for b in digits:
                    product = [0] * (2 * exponent - 1)
                    for i, x in enumerate(a):
                        for j, y in enumerate(b):
                            product[i + j] = (product[i + j] + x * y) % p
                    row.append(encode(_remainder(product, polynomial, p)))
                self.mul.append(row)
        self.neg = [next(b for b in range(q) if self.add[a][b] == 0) for a in range(q)]
        self.inv = [0] + [next(b for b in range(1, q) if self.mul[a][b] == 1)
                         for a in range(1, q)]


def _rref(rows, field):
    """Canonical reduced row-echelon basis; zero rows are discarded."""
    matrix = [list(row) for row in rows]
    if not matrix:
        return ()
    pivot = 0
    add, mul, neg, inv = field.add, field.mul, field.neg, field.inv
    for col in range(len(matrix[0])):
        source = next((row for row in range(pivot, len(matrix)) if matrix[row][col]), None)
        if source is None:
            continue
        matrix[pivot], matrix[source] = matrix[source], matrix[pivot]
        scalar = inv[matrix[pivot][col]]
        matrix[pivot] = [mul[scalar][value] for value in matrix[pivot]]
        for row in range(len(matrix)):
            if row != pivot and matrix[row][col]:
                scalar = matrix[row][col]
                matrix[row] = [add[value][neg[mul[scalar][basis]]]
                               for value, basis in zip(matrix[row], matrix[pivot])]
        pivot += 1
        if pivot == len(matrix):
            break
    return tuple(tuple(row) for row in matrix[:pivot])


def _subspaces(q, d, k):
    # Every subspace has exactly one RREF basis. Only entries to the right
    # of a row's pivot in nonpivot columns are free.
    for pivots in itertools.combinations(range(d), k):
        free = [(row, col) for row, pivot in enumerate(pivots)
                for col in range(pivot + 1, d) if col not in pivots]
        for values in itertools.product(range(q), repeat=len(free)):
            matrix = [[0] * d for _ in range(k)]
            for row, pivot in enumerate(pivots):
                matrix[row][pivot] = 1
            for (row, col), value in zip(free, values):
                matrix[row][col] = value
            yield tuple(tuple(row) for row in matrix)


def grassmann_graph(q: int, d: int, k: int, *, max_vertices: int = DEFAULT_MAX_VERTICES) -> nx.Graph:
    """Return a graph isomorphic to J_q(d,k), with deterministic integer labels.

    q must be a prime power. Duality reduces k to min(k,d-k). Vertices are
    enumerated as RREF bases; edges join subspaces sharing a hyperplane.
    max_vertices bounds construction, not the subsequent complexity search.
    """
    order = grassmann_order(q, d, k)
    if max_vertices < 1 or order > max_vertices:
        raise ValueError(f"J_{q}({d},{k}) has {order} vertices; construction limit is {max_vertices}")
    original_k, k = k, min(k, d - k)
    if k == 1:
        graph = nx.complete_graph(order)
    else:
        field = _FiniteField(q)
        incidence = {}
        graph = nx.Graph()
        for vertex, basis in enumerate(_subspaces(q, d, k)):
            graph.add_node(vertex)
            # A hyperplane in this k-space is the kernel of one projective
            # linear form. Normalize its first nonzero coefficient to 1.
            for pivot in range(k):
                for tail in itertools.product(range(q), repeat=k - pivot - 1):
                    coefficients = (0,) * pivot + (1,) + tail
                    kernel = [tuple(field.add[basis[row][col]][
                                field.neg[field.mul[coefficients[row]][basis[pivot][col]]]]
                                for col in range(d)) for row in range(k) if row != pivot]
                    key = _rref(kernel, field)
                    incidence.setdefault(key, []).append(vertex)
        if len(graph) != order:
            raise RuntimeError("Subspace enumeration disagrees with the Gaussian binomial coefficient")
        for vertices in incidence.values():
            graph.add_edges_from(itertools.combinations(vertices, 2))
    graph.graph.update(name=f"J_{q}({d},{original_k})", q=q, ambient_dimension=d,
                       subspace_dimension=original_k)
    return graph
