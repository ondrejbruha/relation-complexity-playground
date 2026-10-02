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
2. Enumerate automorphisms using NetworkX; return 1 for a rigid nonhomogeneous graph.
3. Store each transporter x -> y and each point stabilizer as an integer bitset
   of automorphisms satisfying that constraint.
4. Search one representative per ordered-pair orbit, using adjacency-compatible
   vertices as possible elements of S.
5. Intersect constraints using bitwise AND. Stop extending an inconsistent set;
   skip redundant constraints, which cannot occur in a minimal obstruction.
6. When an intersection becomes empty, check whether deleting any one fixed-point
   constraint restores an automorphism. Deleting x -> y already leaves the
   identity. Record the largest minimal obstruction and its witness.

Pair-orbit normalization is valid because conjugating by a graph automorphism
preserves adjacency, extendability, and minimality. Search pruning only skips
branches that cannot improve the largest obstruction already proved.

## Bounds, coverage, and padding

An unfinished search returns no exact rc value. It retains the largest proved
obstruction and the general upper bound. The default limits are cooperative,
including during automorphism enumeration; the classification shortcut precedes
those limit checks. A limit is not a strict operating-system deadline.

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

The current backend still enumerates the full automorphism group and searches
subsets exponentially in the worst case. Tests independently enumerate all induced
partial isomorphisms through n = 6 and check examples, witnesses, complements,
relabelling, bounds, and interrupted/retried experiments. These checks support
correctness within their scope; they do not settle an asymptotic growth conjecture.
