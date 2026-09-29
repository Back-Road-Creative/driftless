"""Writes both the JSON API and the browser pages perform, owned by neither.

A page handler used to call the route function in :mod:`driftless.api.app` to file the
same row the API files — the two write paths are one, deliberately — which made
``driftless.web`` import ``driftless.api.app``, the module that imports
``driftless.web`` back to mount the pages. The shared write lives here instead, so the
guarantee survives without the cycle.
"""
