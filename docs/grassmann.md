# Grassmann graphs

The Grassmann graph **J_q(d,k)** has one vertex for each k-dimensional subspace
of GF(q)^d. Two vertices are adjacent when their intersection has dimension k-1.
Here q is a prime power, d is the ambient vector-space dimension, and 1 <= k < d.
This is the convention used by
[SageMath's GrassmannGraph](https://doc.sagemath.org/html/en/reference/graphs/sage/graphs/graph_generators.html#sage.graphs.graph_generators.GraphGenerators.GrassmannGraph).

The graph order N is a Gaussian binomial coefficient, rather than d or k:

```text
N = [d choose k]_q = product((q^(d-i) - 1) / (q^(k-i) - 1), i=0,...,k-1)
```

| Graph | Vertices N | Degree |
|---|---:|---:|
| J_2(4,2) | 35 | 18 |
| J_2(5,2) | 155 | 42 |
| J_2(6,2) | 651 | 90 |
| J_2(7,2) | 2,667 | 186 |
| J_3(4,2) | 130 | 48 |
| J_3(5,2) | 1,210 | 156 |
| J_4(4,2) | 357 | 100 |

For k=1 or k=d-1 the graph is complete, so its structural rc is 0. The first
noncomplete binary example is J_2(4,2), with 35 vertices.

## Compute and plot

Select the family explicitly and give one or more comma-separated triples:

```sh
python main.py --mode families --families grassmann --grassmann 2,4,2 --max-n 35 --workers 1 --timeout 30 --output results/grassmann
```

Omitting `--grassmann` selects `2,4,2`. Grassmann graphs are excluded from the
default family selection so existing default experiments keep their workload.
The vertex range always refers to **N**, so `--max-n 7` excludes J_2(4,2).
A Grassmann-only selection outside the range reports an error with its orders.

To examine larger examples and compare other families:

```sh
python main.py --mode families --families grassmann cube rook kneser --grassmann 2,4,2 2,5,2 2,6,2 --max-n 651 --workers 4 --timeout 30 --output results/grassmann-comparison
```

This also selects all matching cube, rook, and odd Kneser graphs through N=651.
For a smaller experiment, use only `--families grassmann`. Nonbinary examples:

```sh
python main.py --mode families --families grassmann --grassmann 3,4,2 4,4,2 --max-n 357 --workers 2 --output results/grassmann-other-fields
```

The existing SQLite checkpoints, limits, retries, CSVs, and plots apply unchanged.
Different parameter triples have different task IDs, even if they share an order.
Changing or extending `--grassmann` in the same output directory retains all
previously saved results and records the union of parameter selections.
Completed exact graphs are reused; bounded results need `--retry-incomplete`.
Use a new directory when you want exports containing only the current selection.

## Generate graphs without computing rc

Construction is much easier than the generic automorphism and obstruction search.
To obtain graphs for inspection or a different solver:

```sh
python main.py --mode families --families grassmann --grassmann 2,4,2 2,5,2 2,6,2 --max-n 651 --generate-only --output results/grassmann-graphs
```

This writes `graphs.g6` and `graphs.csv`, whose rows label the graphs in file order
and record their parameters through the graph names, orders, and edge counts.
It performs no rc computation and creates no experiment database or rc plot.
It also works for the other named families. To compute from the saved graph6 file:

```sh
python main.py --mode graph6 --input results/grassmann-graphs/graphs.g6 --max-n 651 --workers 3 --timeout 30 --output results/grassmann-from-file
```

The graph6 mode uses line labels; the families mode retains the J_q(d,k) names in
its plots and records. The native generator is also available as a Python API:

```python
from grassmann import grassmann_graph, grassmann_order

print(grassmann_order(2, 5, 2))  # 155
graph = grassmann_graph(2, 5, 2)
```

## Construction and limits

`grassmann.py` enumerates unique subspaces as reduced row-echelon bases. It builds
edges through shared (k-1)-subspaces, avoiding pairwise rank tests for every pair
of vertices. Duality reduces k to min(k,d-k), producing an isomorphic graph.
Prime-power fields use polynomial arithmetic over their prime field, with a
deterministically selected irreducible polynomial. No SageMath or new dependency
is required. Tests cover finite-field arithmetic and graph construction.

Construction is limited to 2,000 vertices per Grassmann graph by default. Raising
`--max-n` alone does not disable this guard. To deliberately generate a larger one:

```sh
python main.py --mode families --families grassmann --grassmann 2,7,2 --max-n 2667 --grassmann-max-vertices 3000 --generate-only --output results/grassmann-larger
```

The construction limit also applies to the Python API's `max_vertices` argument.
It does not impose a memory or time bound. The rc timeout starts after construction
and remains cooperative, as documented in the [algorithm note](algorithm.md).

For complexity calculations, install `requirements-group.txt` and select the
generator backend:

```sh
python -m pip install -r requirements-group.txt
python main.py --mode families --families grassmann --grassmann 2,4,2 2,5,2 2,6,2 --max-n 651 --backend bliss --workers 2 --timeout 30 --output results/grassmann-bliss
```

Bliss computes full automorphism generators and coloured point stabilizers, avoiding
group enumeration. In local verification J_2(4,2) completed with rc=5; its minimal
obstruction was independently verified by VF2. Larger examples can still time out
during subset search, retaining improved lower and upper bounds. `--bounds-only`
searches verified witnesses, while `--retry-incomplete` resumes a previously bounded
experiment by retrying those graphs. The cache engine signature remains compatible
with earlier exact values and bounds. No theoretical rc formula or asymptotic claim
is substituted for a computation.
