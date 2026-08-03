# {{ title }}

_As of {{ as_of }}_

{% if not departments %}
_No departments defined._
{% endif %}
{% for d in departments %}
## {{ d.name }}

- **Business:** {{ d.business }}
- **Headcount:** {{ d.headcount }}
- **Weekly capacity (hours):** {{ d.capacity_hours }}
- **Blended labour rate:** {{ d.blended_rate }}

| Project | Budget | Actual | CPI |
| --- | --- | --- | --- |
{% for p in d.projects %}
| {{ p.name }} | {{ p.budget }} | {{ p.actual }} | {{ p.cpi }} |
{% endfor %}
{% if not d.projects %}
_No projects assigned to this department._
{% endif %}

{% endfor %}
