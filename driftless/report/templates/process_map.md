# {{ title }} — {{ project.name }}

_As of {{ as_of }}_

**Completeness:** {{ completeness }}

| Process | Name | Group | Area | State |
| --- | --- | --- | --- | --- |
{% for r in rows %}
| {{ r.id }} | {{ r.name }} | {{ r.group }} | {{ r.area }} | {{ r.state }} |
{% endfor %}
