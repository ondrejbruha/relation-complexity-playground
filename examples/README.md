# Computed examples

These small figures and CSV summaries are snapshots of local completed experiments.
They are included so the project can be inspected without downloading catalogues
or running a long enumeration. Full catalogues and SQLite databases are excluded.

## Complete catalogues

![Exact maxima through 9 vertices](catalog/plot.png)

[Summary CSV](catalog/summary.csv) · [Distribution CSV](catalog/distribution.csv) ·
[SVG figure](catalog/plot.svg)

The experiment contains all 288,266 nonisomorphic simple graphs with 1 to 9
vertices, including disconnected graphs. Every per-graph computation completed
exactly. The certified maxima are `0, 0, 1, 1, 1, 2, 2, 2, 2`, using the
structural convention that an already ultrahomogeneous graph has rc = 0.

Orders up to 7 come from NetworkX's graph atlas. Orders 8 and 9 use the complete
catalogues from [Brendan McKay](https://users.cecs.anu.edu.au/~bdm/data/graphs.html).
Catalogue hashes and snapshot dependency versions are recorded in
[provenance.json](provenance.json). Catalogue completeness is supplied by the
source; the result is not an independent formal proof of source completeness.

Reproduce from the repository root after installing dependencies:

```sh
python main.py --mode catalog --min-n 1 --max-n 9 --workers 4 --plot-every 25000 --output results/catalog
```

## Selected families

![Named families and their lower bounds](families/plot.png)

[Summary CSV](families/summary.csv) · [Distribution CSV](families/distribution.csv) ·
[SVG figure](families/plot.svg)

This snapshot includes cycles, hypercubes, Petersen, square rook graphs, and odd
Kneser graphs with orders 2 to 35. It certifies individual graph values, not global
maxima over all graphs of those orders. The lower envelope carries smaller
examples forward by isolated-vertex padding. Marker sizes count graphs in the
selected dataset, rather than all graphs at that order.

```sh
python main.py --mode families --min-n 2 --max-n 35 --families cycle cube petersen rook kneser --workers 4 --output results/families
```

For an independent snapshot of exactly this selection, use a new output directory.
Reusing one with additional saved families retains those older results in exports.
Matplotlib rendering may vary by operating system; reproduce numerical summaries
and statuses rather than requiring identical image bytes.

## Refreshing these files

Finish the two runs, then copy their current small exports and record provenance:

```sh
python examples/refresh.py
```

Custom source directories can be supplied with `--catalog-dir` and `--families-dir`.
The refresh command requires complete exact catalogue coverage for orders 1 to 9,
and checks summary counts against the source databases. It copies only the figures
and small summary/distribution CSVs, normalizing text exports to LF line endings
so their recorded hashes also match Git checkouts. It does not copy graph catalogues, SQLite
databases, or per-graph timing tables. Run it after the experiment writer has exited.
