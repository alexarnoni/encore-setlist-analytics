{#
    split_medley(column) — a lateral subquery splitting a setlist.fm
    song name on " / " (product.md: "Medleys — names joined by ' / ' —
    are split into separate entries").

    Use as:   cross join lateral {{ split_medley('e.song_name') }} as p
    Returns:  part        trimmed text of one piece
              part_idx    1, 2, 3... among the NON-EMPTY pieces
              part_count  how many non-empty pieces the entry had, so the
                          caller can flag is_medley as part_count > 1

    Empty pieces ("A /  / B", or a trailing " / ") are dropped BEFORE
    numbering, so part_idx has no gaps and a stray separator never makes
    a one-song entry look like a medley. An entry that is empty, blank or
    NULL yields no rows at all (there is no song to count).

    Only the spaced " / " splits: a bare slash inside a name ("AC/DC")
    is left alone.

    WHERE runs before window functions, so part_idx/part_count are
    computed over the surviving pieces only.
#}
{% macro split_medley(column) -%}
(
    select
        part,
        row_number() over (order by ord) as part_idx,
        count(*) over () as part_count
    from (
        select btrim(u.part) as part, u.ord
        from unnest(string_to_array({{ column }}, ' / ')) with ordinality as u(part, ord)
    ) as pieces
    where part <> ''
)
{%- endmacro %}
