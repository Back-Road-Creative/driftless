# {{ title }} — {{ project.name }}

_As of {{ as_of }}_

## Top threats

{% if not threats %}
_No live threats._
{% else %}
| Severity | Area | Threat |
| --- | --- | --- |
{% for t in threats %}
| {{ t.severity }} | {{ t.kind }} | {{ t.description }} |
{% endfor %}
{% endif %}

## Knowledge areas

{% for a in assessments %}
### {{ a.kind }} — {{ a.status }} (risk {{ a.score }})

{% for th in a.threats %}
- ⚠ {{ th }}
{% endfor %}
{% for ac in a.actions %}
- → {{ ac.label }} [{{ ac.tt }}]
{% endfor %}
{% if not a.threats %}
- Healthy — no action required.
{% endif %}

{% endfor %}
