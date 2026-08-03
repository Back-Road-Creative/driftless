"""Pure calculation core — no I/O, no ORM, no templates.

Modules here (evm, rollup, forecast) take plain value objects and return
numbers. Both the dashboard and the report engine import these same
functions, which is what makes a figure on a screen and the same figure in a
document impossible to disagree.

Deliberately empty: submodules are imported by their full path
(`from driftless.calc.evm import ...`) rather than re-exported here, so modules
can be added in independent parallel changes without contending over a
shared registry file.
"""
