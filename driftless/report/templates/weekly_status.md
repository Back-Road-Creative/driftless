{% macro n(v) %}{% if v is none %}n/a{% else %}{{ "%.2f"|format(v) }}{% endif %}{% endmacro %}
# {{ title }} — {{ project }}

_As of {{ as_of }}_

## Status
{% if snapshot %}
RAG **{{ snapshot.rag_status }}** — {{ snapshot.percent_complete }}% complete (taken {{ snapshot.taken_on }})
{% if snapshot.note %}

> {{ snapshot.note }}
{% endif %}
{% else %}
No status snapshot on or before {{ as_of }}.
{% endif %}

## Earned value
| Metric | Value |
| --- | --- |
| Cost performance index (CPI) | {{ n(s.cpi) }} |
| Schedule performance index (SPI) | {{ n(s.spi) }} |
| Cost variance (CV) | {{ n(cv) }} |
| Schedule variance (SV) | {{ n(sv) }} |

## Top open risks
{% if risks %}
| Exposure | Description | Status | Owner |
| --- | --- | --- | --- |
{% for r in risks %}
| {{ n(r.exposure) }} | {{ r.description }} | {{ r.status }} | {{ r.owner or "—" }} |
{% endfor %}
{% else %}
No open risks.
{% endif %}
