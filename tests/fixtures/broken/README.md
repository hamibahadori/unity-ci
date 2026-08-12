# broken fixture

One deliberate violation per rule. Every check must FAIL here — a check that cannot fail is not a
check. The self-test also asserts each failure mentions the right file, so a check cannot pass this
fixture by failing for an unrelated reason.
