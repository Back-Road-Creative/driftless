"""Mount the dashboard (:mod:`driftless.web`) onto the API app.

Wired the same way :mod:`driftless.api.logging` and :mod:`driftless.api.metrics`
already are -- calls from ``app.py`` -- and this module imports nothing from
:mod:`driftless.api.app` itself, so those calls are never circular.

They used to be circular in the other direction: every ``driftless.web`` submodule
imported ``get_session`` or another write helper from ``driftless.api.app``, so a
process that reached a page module first re-entered ``api.app``, which asked the
half-executed web module for a router it had not defined yet. That is why the mount
carried a ``_web_mounted`` flag, a ``web_mid_import()`` probe reading
``__spec__._initializing`` off every loaded module, and a second call from the lifespan
as a backstop. Those helpers now live in leaf modules -- :mod:`driftless.api.deps`,
:mod:`driftless.assess.percent`, :mod:`driftless.services` -- nothing under
``driftless/web`` imports ``driftless.api.app``, and the mount is one unconditional call
at import, with the page modules imported at module scope like any other dependency.
``tests/test_api_import_order.py`` holds both halves of that: the web-first subprocess
probes, and structural checks that the flag, the probe and the deferred imports stay gone.
"""

from __future__ import annotations

from datetime import date

from fastapi import FastAPI

from fastapi.staticfiles import StaticFiles
from driftless.web import create_router, static_dir
from driftless.web import create_configuration_router, create_departments_router
from driftless.web import create_scorecard_router
from driftless.web.assist_closeout import create_assist_closeout_router
from driftless.web.assist_department import create_assist_department_router
from driftless.web.assist_decisions import create_assist_decisions_router
from driftless.web.assist_cost import create_assist_cost_router
from driftless.web.assist_evm import create_assist_evm_router
from driftless.web.assist_requirements import create_assist_requirements_router
from driftless.web.assist_decision_tree import create_assist_decision_tree_router
from driftless.web.assist_risk import create_assist_risk_router
from driftless.web.assist_risk_pi import create_assist_risk_pi_router
from driftless.web.assist_team import create_assist_team_router
from driftless.web.assist_scope import create_assist_scope_router
from driftless.web.assist_procurement import create_assist_procurement_router
from driftless.web.assist_quality import create_assist_quality_router
from driftless.web.assist_schedule import create_assist_schedule_router
from driftless.web.baseline_diff import create_baseline_diff_router
from driftless.web.board import create_board_router
from driftless.web.business_detail import create_business_detail_router
from driftless.web.business_map import create_business_map_router
from driftless.web.drills import create_drills_router
from driftless.web.flow import create_flow_router
from driftless.web.gantt import create_gantt_router
from driftless.web.gates import create_gates_router
from driftless.web.schedule_health import create_schedule_health_router
from driftless.web.heatmap import create_heatmap_router
from driftless.auth.oidc import install_oidc
from driftless.web.login import create_login_router
from driftless.web.method_hub import create_method_hub_router
from driftless.web.method_map import create_method_map_router
from driftless.web.method_map_json import install_method_map_json
from driftless.web.methods import create_methods_router
from driftless.web.pmbok_reference import create_pmbok_reference_router
from driftless.web.proof import create_pmbok_proof_router
from driftless.web.process_map import create_process_map_router
from driftless.web.assist_stakeholders import create_assist_stakeholders_router
from driftless.web.project_hub import create_project_hub_router
from driftless.web.raid_log import create_raid_log_router
from driftless.web.sign_off import create_sign_off_router
from driftless.web.status import create_status_router
from driftless.web.threat_board import create_threat_board_router
from driftless.web.wizard_pages import create_wizard_router
from driftless.web.search import create_search_router
from driftless.web.techniques import create_techniques_router
from driftless.web.artifacts import create_artifacts_router
from driftless.web.glossary import create_glossary_router
from driftless.web.errors import install_page_errors as _install_page_errors


def mount_web(app: FastAPI) -> None:
    """Serve the dashboard at ``/`` on ``app``.

    Called exactly once, from the bottom of :mod:`driftless.api.app`; a router included
    twice would duplicate every page route, which ``tests/test_web_mount_once.py``
    counts for.

    ``date.today`` is passed uncalled: the default as-of is resolved per
    request, never at import. An import-time date would freeze at process
    start, and reading the clock inside calc would break the byte-identical
    regeneration every report depends on — the date stays an explicit input.
    """
    app.include_router(create_project_hub_router(date.today))
    app.include_router(create_assist_stakeholders_router(date.today))
    app.include_router(create_assist_evm_router(date.today))
    app.include_router(create_assist_risk_router(date.today))
    app.include_router(create_assist_decision_tree_router(date.today))
    app.include_router(create_assist_risk_pi_router(date.today))
    app.include_router(create_assist_requirements_router(date.today))
    app.include_router(create_assist_team_router(date.today))
    app.include_router(create_assist_scope_router(date.today))
    app.include_router(create_assist_procurement_router(date.today))
    app.include_router(create_assist_quality_router(date.today))
    app.include_router(create_assist_closeout_router(date.today))
    app.include_router(create_assist_decisions_router(date.today))
    app.include_router(create_assist_cost_router(date.today))
    app.include_router(create_assist_schedule_router(date.today))
    app.include_router(create_gantt_router(date.today))
    app.include_router(create_schedule_health_router(date.today))
    app.include_router(create_baseline_diff_router())  # no as-of: two explicit approved versions
    app.include_router(create_gates_router(date.today))
    app.include_router(create_flow_router(date.today))
    app.include_router(create_board_router())  # no as-of either: a task carries no date
    app.include_router(create_search_router())  # no as-of: nothing it renders is dated
    app.include_router(create_router(date.today))
    # Mounted before the reference router: /pmbok/proof would otherwise match
    # /pmbok/{process_id} first (routes are tried in the order they were added), and
    # catalog.get("proof") 404s.
    app.include_router(create_pmbok_proof_router())  # no as-of: the registry walk is frozen
    app.include_router(create_pmbok_reference_router(date.today))
    app.include_router(create_techniques_router(date.today))
    app.include_router(create_methods_router())  # no as-of: the registry is frozen
    app.include_router(create_artifacts_router(date.today))
    app.include_router(create_glossary_router())  # no as-of: the registry is frozen
    app.include_router(create_method_hub_router())  # no as-of: it only counts frozen registries
    # A direct add_api_route, not include_router: it answers JSON, not a page, and
    # driftless.web.method_map_json's own docstring says why it is registered this way.
    install_method_map_json(app)  # no as-of: GRAPH is frozen
    app.include_router(create_threat_board_router(date.today))
    app.include_router(create_process_map_router(date.today))
    app.include_router(create_raid_log_router(date.today))
    app.include_router(create_business_detail_router(date.today))
    app.include_router(create_wizard_router(date.today))
    app.include_router(create_sign_off_router(date.today))
    app.include_router(create_status_router(date.today))
    app.include_router(create_configuration_router())
    app.include_router(create_scorecard_router(date.today))
    app.include_router(create_departments_router(date.today))
    app.include_router(create_assist_department_router(date.today))
    app.include_router(create_heatmap_router(date.today))
    app.include_router(create_drills_router(date.today))
    app.include_router(create_business_map_router(date.today))
    app.include_router(create_method_map_router(date.today))
    app.include_router(create_login_router())  # sign-in only: it protects nothing
    # A direct add_api_route, not include_router: neither OIDC route renders a page
    # (only a redirect or an HTTPException), and driftless.auth.oidc's install_oidc
    # docstring says why it is registered this way. 404s until OIDC is configured.
    install_oidc(app)
    app.mount("/static", StaticFiles(directory=static_dir()), name="static")


def install_page_errors(app: FastAPI) -> None:
    """Designed HTML 404/500 pages, keyed on the page routes themselves, so every JSON
    API error body stays as it was. Called from module import unconditionally rather
    than from :func:`mount_web`, because Starlette snapshots the handler table into the
    middleware stack the first time the app is called — BEFORE lifespan startup, so a
    handler added there is never reached and a mistyped page URL would answer JSON."""
    _install_page_errors(app)
