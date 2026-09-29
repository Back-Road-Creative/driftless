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
{% if ac.launch_href %}
- → {{ ac.label }} — apply **{{ ac.technique }}** at {{ ac.launch_href }}
{% else %}
- → {{ ac.label }} — [{{ ac.technique }}]({{ ac.reference_href }}) (reference only — no assistant yet)
{% endif %}
{% endfor %}
{% if not a.threats %}
- Healthy — no action required.
{% endif %}

{% endfor %}
