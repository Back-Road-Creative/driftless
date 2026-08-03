# {{ title }}

_As of {{ as_of }}_

## Business totals

| Metric | Value |
| --- | --- |
| Budget | {{ total.budget }} |
| Actual cost | {{ total.actual }} |
| Percent complete | {{ total.complete }} |
| RAG | {{ total.rag }} |
| Open high risks | {{ total.risks }} |
| On-track share | {{ on_track }} |

## Portfolios
{% if rows %}

| Item | Budget | Actual | Complete | Risks | RAG |
| --- | --- | --- | --- | --- | --- |
{% for r in rows %}
| {% if r.kind == "project" %}{{ r.name }}{% else %}**{{ r.name }}** ({{ r.kind }}){% endif %} | {{ r.budget }} | {{ r.actual }} | {{ r.complete }} | {{ r.risks }} | {{ r.rag }} |
{% endfor %}
{% else %}

No portfolios recorded.
{% endif %}
