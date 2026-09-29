"""The ``driftless mcp`` command: one subcommand, ``serve``.

Kept a leaf: it imports :mod:`driftless.mcp.server` only inside the handler, so
``driftless --help`` and every other subcommand pay nothing for the FastAPI
``TestClient`` :func:`driftless.mcp.server.build_server` constructs -- there is no
third-party MCP dependency left to guard against.
"""

from __future__ import annotations

import argparse


def _run_serve(_args: argparse.Namespace) -> int:
    from driftless.mcp.server import serve_stdio

    serve_stdio()
    return 0


def add_mcp_subparser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``mcp`` command onto a parent's subparsers."""
    mcp = commands.add_parser("mcp", help="run the MCP server over the /api/v1 handlers")
    sub = mcp.add_subparsers(dest="mcp_command", required=True)
    serve = sub.add_parser("serve", help="serve over stdio")
    serve.set_defaults(handler=_run_serve)
