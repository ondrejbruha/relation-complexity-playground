# Contributing

Contributions to the algorithm, reproducibility, examples, and documentation are
welcome. Start with the [README](README.md) and [algorithm note](docs/algorithm.md).

## Development setup

Use Python 3.12 or 3.13. Create a virtual environment, activate it using the
instructions in the README, and install the direct dependencies:

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

For generator-backend development, install `requirements-group.txt` instead.
Without igraph, generator-specific tests are skipped; CI installs it and tests
both backends, including a parallel symmetric-family experiment.

Tests use the standard library's `unittest`; no separate test package is required.
Check the parallel runner and real plotting/export path with a small offline run:

```sh
python main.py --mode atlas --max-n 5 --workers 2 --output results/smoke
python main.py --plot-only --output results/smoke
```

GitHub Actions runs these checks on Windows and Linux, using Python 3.12 and 3.13.

## Reporting a problem

Include the command, Python and dependency versions, expected behavior, and actual
output. For a disputed mathematical value, include the graph in graph6 or as an
edge list, its computed bounds/status, and an independent argument or witness if
available. For interrupted runs, say whether the result was exact or limited.

Do not attach a full database when a small graph and command reproduce the issue.

## Pull requests

- Keep each change focused and explain the mathematical or user-visible effect.
- Add independent checks for changes to the computation. In particular, a bound
  must not become an exact value unless it is justified.
- Preserve the distinction between structural rc, group arity, and k-closure.
- Include a witness or a small independently verifiable example for new results.
- If cached results would change meaning, update `ENGINE_VERSION` and explain the
  compatibility impact. Family-generation changes can affect task IDs and graph6
  encodings, so review existing checkpoint compatibility too.
- Report the tests run. Performance changes should include graph order, graph6 or
  family, limits, worker count, versions, and timing methodology.
- Keep generated databases, full catalogues, environments, and IDE files out of
  the repository. Small documented figures and summaries belong in `examples/`.

## Useful next steps

The Bliss generator backend and independent VF2 witness checks are implemented.
Further stabilizer-chain implementations, specialized geometric actions, and
targeted strongly regular graph searches are useful next steps. Profile a bottleneck before
adding GPU machinery. Packaging for PyPI is a later step rather than a requirement
for working on this repository.

Contributions are made under the project's [MIT License](LICENSE).

## Publishing the first version

Review and commit the prepared files locally. Create an empty **public** repository
on GitHub; the README, license, and ignore rules are already supplied here. Do not
initialize additional copies of those files on GitHub.

After your local commit, replace the placeholder URL and run:

```sh
git branch -M main
git remote add origin https://github.com/YOUR-ACCOUNT/relation-complexity-playground.git
git push -u origin main
```

Wait for all four GitHub Actions jobs to pass before creating the first release.
Then update the unreleased changelog heading with the release date, commit that
change, and create the `v0.1.0` tag and release. Attach small figures or summaries
if useful; keep full databases and third-party catalogues out of the repository.

The preparation work does not create a commit, remote, tag, or GitHub release.
