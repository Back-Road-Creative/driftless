# {{ title }} — {{ project.name }}

_As of {{ as_of }}_

- **Delivery mode:** {{ project.delivery_mode }}
- **Portfolio:** {{ project.portfolio.name }}
{% if project.program %}
- **Program:** {{ project.program.name }}
{% endif %}
{% if project.status_note %}
- **Status:** {{ project.status_note }}
{% endif %}

## Stakeholders

| Name | Interest | Influence | Cadence |
| --- | --- | --- | --- |
{% for s in stakeholders %}
| {{ s.name }} | {{ s.interest }} | {{ s.influence }} | {{ s.comms_cadence }} |
{% endfor %}

## Key milestones

| Milestone | Target | Status |
| --- | --- | --- |
{% for m in milestones %}
| {{ m.name }} | {{ m.target_date }} | {{ m.status }} |
{% endfor %}
