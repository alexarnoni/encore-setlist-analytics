{#
    parse_setlistfm_date(column) — setlist.fm's "DD-MM-YYYY" text to a
    date, returning NULL (never an error) for anything malformed or
    impossible: NULL, garbage, "31-02-2001", "00-00-0000", month 13...

    Why not just to_date(): in Postgres to_date()/make_date() RAISE on an
    out-of-range value instead of returning NULL. staging models are
    views, so that error would only surface when a downstream mart is
    built — one bad date in one band would fail the whole pipeline run.
    Phase 0 treated an invalid date as NaT and moved on; this keeps that
    behaviour.

    Nested CASEs, not `and`: Postgres does not guarantee left-to-right
    short-circuiting of AND, but it does evaluate a CASE branch's THEN
    only when its WHEN matched. So make_date() below is only ever reached
    with an in-range year and month.
#}
{% macro parse_setlistfm_date(column) -%}
{%- set d = "split_part(" ~ column ~ ", '-', 1)::int" -%}
{%- set m = "split_part(" ~ column ~ ", '-', 2)::int" -%}
{%- set y = "split_part(" ~ column ~ ", '-', 3)::int" -%}
case
    when {{ column }} ~ '^[0-9]{2}-[0-9]{2}-[0-9]{4}$' then
        case
            when {{ m }} between 1 and 12 and {{ y }} >= 1 then
                case
                    when {{ d }} between 1 and extract(
                        day from (make_date({{ y }}, {{ m }}, 1) + interval '1 month' - interval '1 day')
                    )::int
                    then make_date({{ y }}, {{ m }}, {{ d }})
                end
        end
end
{%- endmacro %}
