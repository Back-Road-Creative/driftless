{% macro n(v) %}{% if v is none %}n/a{% else %}{{ "%.2f"|format(v) }}{% endif %}{% endmacro %}
# {{ title }} — {{ project.name }}

_As of {{ as_of }} — {{ mode }} delivery_
{% if predictive %}

## Completion forecast (EVM)

| Metric | Value |
| --- | --- |
| Estimate at completion (EAC) | {{ n(s.eac) }} |
| Estimate to complete (ETC) | {{ n(s.etc) }} |
| Variance at completion (VAC) | {{ n(s.vac) }} |
{% if milestones %}

### Milestone slip vs baseline

| Milestone | Target | Baseline | Slip (days) | Status |
| --- | --- | --- | --- | --- |
{% for m in milestones %}
| {{ m.name }} | {{ m.target }} | {{ m.baseline if m.baseline else "—" }} | {{ m.slip_days if m.slip_days is not none else "n/a" }} | {{ m.status }} |
{% endfor %}
{% endif %}
{% endif %}
{% if band %}

## Completion forecast (velocity)

{{ n(band.remaining_points) }} points remaining, from {{ band.sprints_used }} sprint(s) of history.

| Case | Velocity (pts/sprint) | Completes |
| --- | --- | --- |
| Best | {{ n(band.velocity_best) }} | {{ band.best if band.best else "never at this velocity" }} |
| Likely | {{ n(band.velocity_likely) }} | {{ band.likely if band.likely else "never at this velocity" }} |
| Worst | {{ n(band.velocity_worst) }} | {{ band.worst if band.worst else "never at this velocity" }} |

### Sprint history

| Sprint | Ended | Completed (pts) |
| --- | --- | --- |
{% for sp in sprints|sort(attribute="ended_on") %}
| {{ sp.name }} | {{ sp.ended_on }} | {{ n(sp.completed_points) }} |
{% endfor %}
{% if simulation %}

### Simulated completion

Monte Carlo over sprint velocity — schedule forecasting, not risk analysis ({{ simulation.trials }} trials, seed {{ simulation.seed }}).

| Percentile | Completes |
| --- | --- |
| p50 | {{ simulation.p50 if simulation.p50 else "never at this velocity" }} |
| p80 | {{ simulation.p80 if simulation.p80 else "never at this velocity" }} |
| p90 | {{ simulation.p90 if simulation.p90 else "never at this velocity" }} |
{% endif %}
{% endif %}

## Contingency

| Figure | Value |
| --- | --- |
| Risk exposure | {{ n(c.exposure) }} |
| Contingency held | {{ n(c.contingency) }} |
| Remaining budget | {{ n(c.remaining_budget) }} |
| Shortfall | {{ n(c.shortfall) }} |
{% if c.top_risk %}

Top risk: {{ c.top_risk }}.
{% endif %}
