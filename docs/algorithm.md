# Structural relational complexity

## Convention

For a finite simple uncoloured graph G, retain its original binary edge relation
and add all relations invariant under Aut(G) of arity at most k. The structural
relational complexity rc(G) is the smallest nonnegative k making that expansion
ultrahomogeneous: every induced partial isomorphism extends to an automorphism.

Already ultrahomogeneous graphs have rc = 0, including the empty graph under this
project's convention. A rigid nonhomogeneous graph has rc = 1, since invariant
unary singleton relations distinguish all vertices. For n >= 1, rc <= n - 1.

This differs from permutation-group arity conventions that already count the
binary relations. It also differs from k-closure. Aut(G) is always 2-closed in
its graph action: a permutation preserving every ordered-pair orbit preserves
edges. Thus the historical `gpt_rc_brute_force.py` k-closure test cannot compute
structural complexities greater than 2.

## Minimal obstructions

Call an induced partial graph isomorphism a minimal obstruction when it does not
extend to an automorphism, but every proper restriction does. If it has r distinct
domain vertices, each proper restriction lies in an automorphism orbit, so it
preserves every invariant relation of arity smaller than r. Its full ordered
domain tuple and image tuple lie in different orbits, distinguished by an
invariant r-ary relation. It therefore forces rc >= r.

Conversely, any nonextendable induced partial isomorphism contains a minimal
obstruction. Once invariants of arity at most the largest obstruction size are
added, none of those obstructions can remain a partial isomorphism. Hence rc is
exactly the largest minimal obstruction size, or 0 when there are no obstructions.
Repeated coordinates do not introduce extra cases: an injective partial map
preserves equality, and repetitions use no more distinct domain vertices.

## Normalizing the search

For an obstruction of size r >= 2, choose one domain vertex x. Its restriction
to the other r - 1 vertices extends to an automorphism g. Compose the original
partial map with g^(-1) on the image. The resulting equivalent obstruction is
**identity on a set S, plus x -> y**, where x != y and neither is in S.

Both x and y belong to the same vertex orbit because the original singleton map
extends. For each v in S, adjacency from x to v must equal adjacency from y to v
so that the normalized map remains a graph isomorphism.

The implementation therefore searches subsets S rather than all ordered tuples
or all partial permutations:

1. Detect ultrahomogeneous graphs with Gardiner's classification: equal-size
   disjoint cliques, their complements, C5, and L(K3,3).
2. Obtain the full automorphism group. The enumeration backend uses NetworkX
   and integer bitsets; the Bliss backend stores generators without enumeration.
   Return 1 for a rigid nonhomogeneous graph.
3. Test whether x and y are in the same orbit of the pointwise stabilizer of S.
   This is equivalent to a nonempty transporter x -> y fixing S.
4. Search one representative per ordered-pair orbit, using adjacency-compatible
   vertices as possible elements of S.
5. Intersect bitsets or compute stabilizer orbits. Stop extending an inconsistent
   set; skip redundant constraints, including earlier constraints that become
   redundant after adding another vertex.
6. When an intersection becomes empty, check whether deleting any one fixed-point
   constraint restores an automorphism. Deleting x -> y already leaves the
   identity. Record the largest minimal obstruction and its witness.

Pair-orbit normalization is valid because conjugating by a graph automorphism
preserves adjacency, extendability, and minimality. Search pruning only skips
branches that cannot improve the largest obstruction already proved.

## Generator backend and symmetry

Install the optional `requirements-group.txt` dependencies and select
`--backend bliss`. `auto` uses enumeration through n=9, and Bliss for larger
graphs when igraph is installed. Explicit `enumeration` remains available for
comparison. `--max-automorphisms` limits enumeration only; a group represented
by generators may have arbitrarily more elements.

Bliss is accessed through igraph. Assigning each vertex of S a different colour
computes generators of the **full** pointwise stabilizer Aut(G)_(S). Generator
orbits are found by joining v with g(v) for every generator. No randomly sampled
subgroup is substituted for the full group. Group orders are exact integers.
Stabilizers are recomputed on the coloured graph, rather than using a SymPy/GAP
Schreier-Sims chain; local probes found this faster for the selected families.
Oracle answers use a bounded LRU cache keyed by fixed vertices and, for symmetry
queries, the candidate set. Search states are not merged merely because their
stabilizers coincide: the deletion conditions of a witness can differ.

Ordered-pair representatives are obtained from vertex orbits and the orbits of
each representative's point stabilizer. During subset search, the symmetry group
must fix x, y and S pointwise **and preserve the current candidate set setwise**.
For a representative v of one candidate orbit, the inclusion branch removes only
v, while the exclusion branch removes the entire orbit. Every subset meeting
that orbit is equivalent to a subset containing v; subsets missing the orbit
remain in the exclusion branch. This proves coverage without relying on a
possibly noninvariant increasing-index suffix.

Cycles of length at least 6 have a separate exact shortcut. Their metric
expansion is ultrahomogeneous, giving rc <= 2. For four successive vertices
a,b,c,d, identity on {d} plus a -> b preserves nonadjacency but changes distance
3 to distance 2. This is a size-2 minimal obstruction. Explicit enumeration
retains the general path for independent comparisons.

## Verified witness search and upper bounds

Before exhaustive Bliss search, reproducible greedy restarts try different
constraint orders. A nonextendable set is reduced by deletion, and every
one-vertex deletion is checked before recording a witness. These certificates
prove lower bounds only. Restarts are controlled by `--heuristic-trials` and
`--search-seed`; their scheduling budget is up to two seconds and at most one
quarter of the per-graph timeout, checked between complete trials.

`--bounds-only` skips exhaustive subset search. `--max-search-nodes` bounds
exhaustive search deterministically. Statuses `bounded`, `node_limit`, and
`timeout` leave rc empty unless proved lower and upper bounds already coincide.
Setting heuristic trials to zero disables restarts and is incompatible with
`--bounds-only`. The enumeration backend also supports bounds-only witness
search; its restarts use the graph's overall cooperative timeout.

For a minimal normalized obstruction, every fixed vertex strictly decreases a
point stabilizer. Each strict subgroup index is at least 2, so
`rc <= 1 + floor(log2(|Aut(G)|))`, combined with `rc <= n-1`.
For a nonempty transporter of size c, each strict nonempty intersection also
has index at least 2: at most `floor(log2(c))` such steps and one final empty
step remain. A branch with s fixed vertices therefore cannot exceed
`s + floor(log2(c)) + 2`. Pair bounds additionally use the number of eligible
vertices. If fixing all eligible vertices still permits x -> y, that pair
contains no obstruction. These are mathematical bounds, not fitted trends.

`verify_witness` provides a separate certificate check using joint colour
refinement and VF2 isomorphism, rather than Bliss stabilizer orbits. It checks graph
adjacency, nonextendability, and every deletion of a normalized obstruction of
size >= 2. Its default 30-second cooperative limit raises TimeoutError if verification
cannot finish; an unfinished check never reports that a certificate is invalid.

## Bounds, coverage, and padding

An unfinished search retains the largest proved obstruction and its proved upper
bound. The default limits are cooperative, including native isomorphism calls;
classification shortcuts precede limit checks. A limit is not a strict
operating-system deadline. Reaching equal bounds certifies the individual value.

An exact graph value is not automatically an exact extremal maximum. Certification
requires exhaustive source coverage and sufficient per-graph bounds. The complete
catalogue mode relies on the published source's completeness up to isomorphism;
the software's count/hash checks do not independently prove catalogue completeness.

For a high-complexity example, adjoining isolated vertices retains its lower bound.
Unary orbits distinguish nontrivial connected components from isolated vertices;
the original component obstructions remain. The component decomposition also
retains obstructions arising from repeated noncomplete components. The resulting
`padded_lower_bound` is a nondecreasing lower envelope as n increases. It is
separate from the observed maximum directly measured at each order.

Subset search remains exponential in the worst case. Tests independently
enumerate induced partial isomorphisms through n=6, compare both backends on all
1,253 atlas graphs through n=7, and check stabilizer orders and transporters against
explicit groups. Larger certificates are checked by VF2. Cache eviction,
complements, relabelling, bounds, and interrupted/retried experiments are covered.
These checks do not settle an asymptotic growth conjecture.
