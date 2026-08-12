# clean fixture

A minimal Unity project layout that every check must pass. Deliberately includes the constructs
that have tripped the naming check before — operator overloads, auto-properties, expression-bodied
members, `static readonly` and `const` — so a regex change that breaks them fails here first.
