{#
    release_year(column) — the year of a MusicBrainz release date.

    MusicBrainz dates are text of VARIABLE precision: "YYYY", "YYYY-MM"
    or "YYYY-MM-DD" (or NULL / empty when unknown). Only the year is used
    downstream (repertoire age is show_year - release_year), so take the
    first four digits when the value starts with a plausible year and
    return NULL otherwise. Never raises.

    [1-9][0-9]{3} rather than [0-9]{4}: rejects "0000" and other
    placeholder years.
#}
{% macro release_year(column) -%}
case
    when {{ column }} ~ '^[1-9][0-9]{3}([^0-9]|$)' then left({{ column }}, 4)::int
end
{%- endmacro %}
