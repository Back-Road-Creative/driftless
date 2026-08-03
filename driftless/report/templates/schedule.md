# {{ title }} — {{ project }}

_As of {{ as_of }}_

| Milestone | Target | Baseline | Status | Slip (days) |
| --- | --- | --- | --- | --- |
{% for r in rows %}
| {{ r.name }} | {{ r.target }} | {{ r.baseline if r.baseline is not none else "—" }} | {{ r.status }} | {{ r.slip if r.slip is not none else "no baseline" }} |
{% endfor %}

Met {{ summary.met }} · At risk {{ summary.at_risk }} · Missed {{ summary.missed }} · Pending {{ summary.pending }}
