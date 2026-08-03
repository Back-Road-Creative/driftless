{% macro n(v) %}{% if v is none %}n/a{% else %}{{ "%.2f"|format(v) }}{% endif %}{% endmacro %}
{% macro cell(v) %}{% if v is none %}—{% else %}{{ v }}{% endif %}{% endmacro %}
# {{ title }} — {{ project }}

_As of {{ as_of }}_

## Risks
{% if risks %}
| Exposure | Description | Probability | Impact | Response | Owner | Status |
| --- | --- | --- | --- | --- | --- | --- |
{% for r in risks %}
| {{ n(r.exposure) }} | {{ r.description }} | {{ n(r.probability) }} | {{ n(r.impact) }} | {{ r.response }} | {{ cell(r.owner) }} | {{ r.status }} |
{% endfor %}
{% else %}
None recorded.
{% endif %}

## Issues
{% if issues %}
| Description | Raised | Resolved | Status | Risk |
| --- | --- | --- | --- | --- |
{% for i in issues %}
| {{ i.description }} | {{ i.raised_on }} | {{ cell(i.resolved_on) }} | {{ i.status }} | {{ cell(i.risk_id) }} |
{% endfor %}
{% else %}
None recorded.
{% endif %}

## Change requests
{% if changes %}
| Description | Raised | Status | Baseline |
| --- | --- | --- | --- |
{% for c in changes %}
| {{ c.description }} | {{ c.raised_on }} | {{ c.status }} | {{ cell(c.resulting_baseline_id) }} |
{% endfor %}
{% else %}
None recorded.
{% endif %}
