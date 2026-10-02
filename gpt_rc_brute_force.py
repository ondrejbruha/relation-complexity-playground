"""Historical k-closure draft, not a structural relational-complexity solver.

Use main.py or relational_complexity.py for the production computation. See
docs/algorithm.md for the distinction between k-closure and structural rc.
"""
from __future__ import annotations

import itertools
from typing import Dict, List, Tuple, Set

import networkx as nx


Permutation = Tuple[int, ...]
KTuple = Tuple[int, ...]


def all_automorphisms(graph: nx.Graph) -> List[Permutation]:
    """
    Vrátí všechny automorfismy grafu.

    Vrcholy jsou interně přečíslovány na 0, ..., n-1.
    Permutace p je reprezentována tak, že p[i] je obraz vrcholu i.
    """
    nodes = list(graph.nodes())
    node_to_idx = {v: i for i, v in enumerate(nodes)}

    gm = nx.algorithms.isomorphism.GraphMatcher(graph, graph)

    automorphisms = []

    for mapping in gm.isomorphisms_iter():
        p = tuple(
            node_to_idx[mapping[nodes[i]]]
            for i in range(len(nodes))
        )
        automorphisms.append(p)

    return automorphisms


def apply_permutation(p: Permutation, t: KTuple) -> KTuple:
    """
    Působení permutace na uspořádanou k-tici:
        p.(v1,...,vk) = (p(v1),...,p(vk))
    """
    return tuple(p[x] for x in t)


def compute_orbit_ids(
    n: int,
    automorphisms: List[Permutation],
    k: int,
) -> Dict[KTuple, int]:
    """
    Spočítá orbity působení Aut(G) na V^k.

    Výsledkem je:
        k-tice -> ID její orbity
    """
    tuples = list(itertools.product(range(n), repeat=k))

    orbit_id: Dict[KTuple, int] = {}
    current_id = 0

    for t in tuples:
        if t in orbit_id:
            continue

        orbit = {
            apply_permutation(g, t)
            for g in automorphisms
        }

        for x in orbit:
            orbit_id[x] = current_id

        current_id += 1

    return orbit_id


def preserves_k_orbits(
    p: Permutation,
    orbit_ids: Dict[KTuple, int],
) -> bool:
    """
    Testuje, zda permutace p zachovává každou orbitu na V^k.

    Tj. pro každou k-tici t musí t a p(t)
    ležet ve stejné orbitě Aut(G).
    """
    for t, oid in orbit_ids.items():
        pt = apply_permutation(p, t)

        if orbit_ids[pt] != oid:
            return False

    return True


def k_closure(
    n: int,
    automorphisms: List[Permutation],
    k: int,
) -> Set[Permutation]:
    """
    Spočítá k-closure grupy Aut(G).

    POZOR:
    Enumeruje všech n! permutací, takže je vhodné jen pro malé grafy.
    """
    orbit_ids = compute_orbit_ids(
        n=n,
        automorphisms=automorphisms,
        k=k,
    )

    closure = set()

    for p in itertools.permutations(range(n)):
        if preserves_k_orbits(p, orbit_ids):
            closure.add(p)

    return closure


def relational_complexity(
    graph: nx.Graph,
    verbose: bool = True,
) -> int:
    """
    Vrátí relační komplexitu grafu.

    Hledá nejmenší k takové, že

        Aut(G)^(k) = Aut(G).

    Pro n >= 2 zkouší k = 1,...,n.
    """
    n = graph.number_of_nodes()

    if n == 0:
        return 0

    automorphisms = all_automorphisms(graph)
    aut_set = set(automorphisms)

    if verbose:
        print(f"|V| = {n}")
        print(f"|Aut(G)| = {len(automorphisms)}")

    for k in range(1, n + 1):
        closure = k_closure(
            n=n,
            automorphisms=automorphisms,
            k=k,
        )

        if verbose:
            print(
                f"k={k}: "
                f"počet orbit = "
                f"{len(set(compute_orbit_ids(n, automorphisms, k).values()))}, "
                f"|G^({k})| = {len(closure)}"
            )

        if closure == aut_set:
            return k

    raise RuntimeError(
        "Relační komplexita nebyla nalezena."
    )


if __name__ == "__main__":
    # -----------------------------------------------------
    # Příklad 1: cesta P3
    #
    # 0 --- 1 --- 2
    # -----------------------------------------------------


    G = nx.gnp_random_graph(
        n=8,  # počet vrcholů
        p=0.3,  # pravděpodobnost existence hrany
        seed=42  # pro reprodukovatelnost
    )

    print(G.nodes())
    print(G.edges())

    rc = relational_complexity(G, verbose=True)

    print()
    print(f"Relační komplexita P3: {rc}")
