{% macro n(v) %}{% if v is none %}n/a{% else %}{{ "%.2f"|format(v) }}{% endif %}{% endmacro %}
# {{ title }} — {{ project }}

_As of {{ as_of }}_

| Metric | Value |
| --- | --- |
| Budget at completion (BAC) | {{ n(s.bac) }} |
| Planned value (PV) | {{ n(s.pv) }} |
| Earned value (EV) | {{ n(s.ev) }} |
| Actual cost (AC) | {{ n(s.ac) }} |
| Cost performance index (CPI) | {{ n(s.cpi) }} |
| Schedule performance index (SPI) | {{ n(s.spi) }} |
| Estimate at completion (EAC) | {{ n(s.eac) }} |
| Estimate to complete (ETC) | {{ n(s.etc) }} |
| Variance at completion (VAC) | {{ n(s.vac) }} |
