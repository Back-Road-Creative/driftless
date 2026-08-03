{% macro tasktable(bl) %}
| Task | Start | Finish | Planned cost |
| --- | --- | --- | --- |
{% for r in bl.rows %}
| {{ r.task }} | {{ r.start }} | {{ r.finish }} | {{ "%.2f"|format(r.cost) }} |
{% endfor %}
{% endmacro %}
# {{ title }} — {{ project }}

_As of {{ as_of }}_

{% if not versions %}
No approved baseline recorded.
{% else %}
## Baseline versions

| Version | Status | Approved |
| --- | --- | --- |
{% for v in versions %}
| v{{ v.version }} | {{ v.status }} | {{ v.approved_at if v.approved_at is not none else "—" }} |
{% endfor %}

{% if changed %}
## Original (v{{ original.version }}) — planned cost {{ "%.2f"|format(original.total) }}

{{ tasktable(original) }}
## Current (v{{ current.version }}) — planned cost {{ "%.2f"|format(current.total) }}

{{ tasktable(current) }}
Planned-cost growth: {{ "%.2f"|format(cost_delta) }}

## Change requests

| Raised | Change | Status | Produced |
| --- | --- | --- | --- |
{% for c in changes %}
| {{ c.raised_on }} | {{ c.description }} | {{ c.status }} | {{ ("v" ~ c.version) if c.version is not none else "—" }} |
{% endfor %}
{% else %}
Scope is unchanged since v{{ current.version }}.
{% endif %}
{% endif %}
