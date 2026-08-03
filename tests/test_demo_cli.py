"""The ``demo seed`` subcommand is wired onto the top-level ``driftless`` CLI."""

from driftless import cli
from driftless.demo.cli import _run_seed


def test_demo_seed_parses_and_dispatches_at_top_level() -> None:
    args = cli._build_parser().parse_args(["demo", "seed", "--base-url", "http://example.test"])
    assert args.handler is _run_seed
