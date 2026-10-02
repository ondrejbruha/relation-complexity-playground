# Relational Complexity Playground

A research tool for computing the **structural relational complexity of finite
simple graphs** and exploring its growth with the number of vertices.

[Český návod](README.cs.md) · [Algorithm](docs/algorithm.md) ·
[Contributing](CONTRIBUTING.md) · [MIT license](LICENSE)

The project studies the extremal function

```text
f(n) = max { rc(G) : G is a simple graph with n vertices }
```

It computes exact values when a search finishes, saves proven bounds when a
limit is reached, and distinguishes exhaustive maxima from sampled lower bounds.
This is a research prototype; finite experiments alone cannot establish whether
`f(n) = Θ(log n)`.

![Exact maxima for graphs with 1 to 9 vertices](examples/catalog/plot.png)

## Quick start

Use **Python 3.12 or 3.13**; local verification used Python 3.13. The direct
dependencies are NetworkX and matplotlib. No GPU or external graph generator
is needed for the first experiment.

From the repository directory, create a virtual environment:

```sh
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Or on Linux/macOS:

```sh
source .venv/bin/activate
```

Then install dependencies and enumerate all graphs with up to 7 vertices:

```sh
python -m pip install -r requirements.txt
python main.py --mode atlas --max-n 7 --workers 4 --output results/atlas
```

Run `python main.py --help` for all options. `python -m main` is also supported;
the module name after `-m` has no `.py` suffix.

## Experiments

| Mode | Graphs examined | Can certify the global maximum? |
|---|---|---|
| `atlas` | All nonisomorphic graphs through n = 7, including disconnected graphs | Yes, with complete coverage and sufficient bounds |
| `catalog` | Atlas plus complete McKay catalogues for n = 8 and 9 | Yes, subject to the source catalogue's completeness |
| `families` | Selected named families | Provides lower bounds |
| `circulant` | A systematic sequence of circulant connection sets | Provides lower bounds |
| `random` | Reproducible G(n,p) samples | Provides lower bounds |
| `graph6` | Graphs from a user-supplied graph6 file | Provides lower bounds |
| `geng` | Nonisomorphic graphs streamed from an external nauty `geng` executable | Yes, with complete generation and sufficient bounds |

Complete enumeration through n = 9:

```sh
python main.py --mode catalog --max-n 9 --workers 4 --plot-every 25000 --output results/catalog
```

This downloads the n = 8 and n = 9 catalogues from
[Brendan McKay's graph collection](https://users.cecs.anu.edu.au/~bdm/data/graphs.html)
and caches them in the output directory. Counts and duplicate records are checked;
SHA-256 hashes detect later changes to cached files. Completeness up to isomorphism
comes from the published catalogue, rather than from the record count alone.

Compare symmetric families:

```sh
python main.py --mode families --min-n 3 --max-n 35 --families cycle cube petersen rook kneser --workers 4 --output results/families
```

Available families are paths, cycles, complete graphs, balanced complete bipartite
graphs, Petersen, hypercubes, square rook graphs `L(K(s,s))`, and odd Kneser graphs
`KG(2k+1,k)`, plus explicitly selected Grassmann graphs `J_q(d,k)`.
Their order is the number of graph vertices: a hypercube has `2^d`
vertices, a square rook graph `s²`, and an odd Kneser graph `binom(2k+1,k)`.

Grassmann parameters specify field size, ambient dimension, and subspace dimension;
`--max-n` still bounds the number of graph vertices:

```sh
python main.py --mode families --families grassmann --grassmann 2,4,2 --max-n 35 --output results/grassmann
python main.py --mode families --families grassmann --grassmann 2,4,2 2,5,2 2,6,2 --max-n 651 --generate-only --output results/grassmann-graphs
```

The second command writes graphs without computing rc. Prime-power fields are
supported without additional construction dependencies. Install the optional
generator backend for complexity calculations on larger symmetric graphs:

```sh
python -m pip install -r requirements-group.txt
python main.py --mode families --families grassmann --grassmann 2,4,2 2,5,2 2,6,2 --max-n 651 --backend bliss --workers 2 --timeout 30 --output results/grassmann-bliss
```

`auto` uses enumeration through n=9 and Bliss for larger graphs when installed.
Bliss stores generators and computes full point stabilizers instead of enumerating
the group. Difficult subset searches can still time out. [Grassmann guide](docs/grassmann.md).

Johnson graphs are also available through explicit parameter pairs; the vertex
count is `binom(m,k)`, not m:

```sh
python main.py --mode families --families johnson --johnson 7,3 8,4 9,4 --max-n 126 --backend bliss --output results/johnson
```

`--johnson-max-vertices` limits construction to 2,000 vertices by default.
Johnson and Grassmann selections can be extended in the same output directory.

Other examples:

```sh
python main.py --mode circulant --min-n 6 --max-n 20 --samples 1000 --workers 4 --output results/circulants
python main.py --mode random --min-n 5 --max-n 30 --samples 100 --p 0.3 --seed 42 --workers 4 --output results/random
python main.py --mode graph6 --input graphs.g6 --min-n 10 --max-n 40 --workers 4 --output results/custom
python main.py --mode geng --geng /path/to/geng --min-n 10 --max-n 10 --workers 4 --plot-every 25000 --output results/geng
```

Install [nauty/Traces](https://users.cecs.anu.edu.au/~bdm/nauty/) separately for
`geng`; on Windows, supply the path to `geng.exe`. The full `geng` executable is
not part of this project. Its streaming interface has been checked with a small
substitute generator. There are already 12,005,168 nonisomorphic graphs at n = 10.

Circulant connection sets are visited in binary order, up to `--samples` per n.
Complement symmetry skips half of the sets, but isomorphic duplicates can remain.
These are candidate searches, not uniform samples of all graphs. Random graphs
often have trivial automorphism groups and rc = 1, so they are weak candidates
for finding high extremal complexity. Johnson/Kneser, Grassmann, and strongly
regular graphs are more relevant larger families. Use the generator backend to
avoid the cost of enumerating their large automorphism groups.

`--connected` restricts atlas/catalog/geng/graph6 experiments to connected graphs;
those runs are not marked as certified maxima over all graphs.

## Checkpoints and results

Each graph is committed to SQLite immediately. Re-running a command skips completed
exact results. You may extend the vertex range, increase sample counts, change
worker counts, or add/remove a family selection. Previously saved families remain
in the database and exports. Use a separate output directory for a separate
comparison or a different dataset mode, random seed, probability, or input file.

| File | Contents |
|---|---|
| `experiment.sqlite` | Durable per-graph checkpoints, metadata, and coverage |
| `values.csv` | Graph6, values or bounds, witnesses, backend, group/search times, generator and oracle counts |
| `summary.csv` | Counts, observed maxima, bounds, and `maximum_certified` |
| `distribution.csv` | Counts of exact values at each graph order |
| `plot.png`, `plot.svg` | Exact values in linear/logarithmic views; a separate unfinished-bounds panel when needed |
| `extremal_candidates.g6` | One candidate per summary row, including isolated-vertex padding |

`observed_lower_bound` uses the graphs directly examined at that order.
`padded_lower_bound` also carries forward smaller examples by adding isolated
vertices. The padded lower bound is a faint dashed step curve, not a measured
family curve. Both main panels show exact graph values; certified global maxima
have separate markers. Unfinished graphs appear as lower/upper intervals in their
own panel. The `log2(n)` curve is a visual reference, not a proved bound or fit.
Means and distributions include only completed exact computations, which may
bias them if searches reached limits. [Details of the conventions](docs/algorithm.md).

Exports are refreshed every `--plot-every` new graphs, approximately every minute,
and at exit. Larger export intervals help with large datasets. To redraw saved data:

```sh
python main.py --plot-only --output results/catalog
```

The first Ctrl+C stops new submissions and lets the bounded queue finish and save.
A second Ctrl+C interrupts waiting. Completed checkpoints survive interruption;
an unfinished graph starts over on the next run. Run one writer per output directory.

## Limits and correctness

The default timeout is 30 seconds per graph. The enumeration backend additionally
limits stored automorphisms to 100,000; this limit does not restrict a Bliss group's
order. Limits are cooperative: an internal isomorphism call can run longer before
the next check. Limited results have an empty `rc`, an explicit status, and proven
lower/upper bounds unless those bounds coincide. Retry them:

```sh
python main.py --mode catalog --max-n 9 --timeout 120 --max-automorphisms 500000 --retry-incomplete --workers 4 --plot-every 25000 --output results/catalog
```

`0` disables either limit. `--max-search-nodes` adds a deterministic exhaustive
search limit. For larger graphs, use verified witness search without exhaustive
certification:

```sh
python main.py --mode families --families grassmann --grassmann 2,5,2 --max-n 155 --backend bliss --bounds-only --heuristic-trials 32 --search-seed 0 --output results/grassmann-bounds
```

Witness restarts improve lower bounds; they never certify exactness by sampling.
Equal proved bounds can certify a value even in bounds-only mode. `verify_witness`
checks normalized certificates with an independent VF2 isomorphism algorithm.
The subset search remains exponential. Each process has its own bounded stabilizer
cache or enumeration bitsets. There is no GPU backend.

The exactness claim depends on the algorithm and complete source coverage. Tests
compare all graphs through n = 6 against an independent exhaustive partial-map
implementation, compare both backends on all atlas graphs through n=7, and cover
known examples, witnesses, complements, relabelling,
limits, and checkpoint/resume behavior. GitHub Actions is configured to run tests
and a parallel plotting smoke test on Windows and Linux with Python 3.12 and 3.13.

```sh
python -m unittest discover -s tests -v
```

## Example results

The bundled [example summaries](examples/README.md) contain results from 288,266
graphs with orders 1 through 9, all completed exactly:

| n | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|
| f(n) | 0 | 0 | 1 | 1 | 1 | 2 | 2 | 2 | 2 |

Petersen and `KG(7,3)` have rc = 3. `Q4`, `Q5`, `L(K4,4)`, and `L(K5,5)` were
computed with rc = 4. These examples give lower bounds at their respective orders,
not certified global maxima for those larger orders.

![Computed families and lower bounds](examples/families/plot.png)

## Project layout

`main.py` is the CLI entry point, `experiment.py` manages experiments and exports,
`relational_complexity.py` contains the computation API, `group_backend.py` provides
Bliss stabilizers, and `grassmann.py` and `johnson.py` construct geometric and subset
families. The optional backend dependencies are in `requirements-group.txt`.
`gpt_rc_brute_force.py` is a historical k-closure draft; it does not compute this
project's structural relational complexity. See [the algorithm note](docs/algorithm.md).

Development plans are in [CONTRIBUTING.md](CONTRIBUTING.md). The first version is
prepared as **0.1.0**, with release notes in [CHANGELOG.md](CHANGELOG.md).

## License

Project code, documentation, and the small computed example summaries are licensed
under the [MIT License](LICENSE). Dependencies retain their own licenses. Full
third-party graph catalogues and generated SQLite databases are not bundled.
