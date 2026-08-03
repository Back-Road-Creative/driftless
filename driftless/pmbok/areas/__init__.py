"""One module per knowledge area, each exporting ``PROCESSES``.

Split this way so the ten areas can be authored independently on disjoint files
and the package aggregates them (``driftless.pmbok.catalog``). Each module is pure
reference data — a tuple of ``Process`` rows — and touches no shared registry.
"""
