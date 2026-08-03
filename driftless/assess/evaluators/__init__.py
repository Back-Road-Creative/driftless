"""One evaluator per knowledge area, each exporting ``KIND`` and ``evaluate``.

Split so the nine area evaluators stay on disjoint files; the engine aggregates
them and adds the Integration roll-up.
"""
