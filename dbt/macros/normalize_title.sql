{#
    normalize_title(column) — canonical form of a song/recording title,
    used on BOTH sides of every title match (setlist.fm entries vs
    MusicBrainz recordings/tracks) so a match never depends on
    punctuation, accents, casing or edition suffixes.

    Steps, in order (order matters):
      1. lowercase + strip accents (needs the `unaccent` extension)
      2. remove apostrophes WITHOUT inserting a space ("don't" -> "dont")
      3. "&" -> "and"
      4. drop edition segments — a "(...)" / "[...]" group, or everything
         after a " - ", that contains one of the keywords below
      5. drop a trailing "feat. ..." / "ft. ..." / "featuring ..." clause
      6. remaining punctuation -> space
      7. collapse whitespace, trim

    Step 4 is keyword-based on purpose, not "delete every parenthesis":
    "(What's the Story) Morning Glory?" must keep its parenthetical, and
    "Song (Part 1)" must not collapse into "Song (Part 2)". The cost is
    that a mismatch like "Morning Glory" vs "(What's the Story) Morning
    Glory?" is NOT fixed here — it surfaces in mart_match_quality and is
    fixed by hand in seed_song_overrides.csv.

    Keywords match as whole words (\m...\M): "edit" hits "(Radio Edit)"
    but not "(Editor's Cut)".

    The expression is built one step per line rather than as one deeply
    nested call, so each rule is readable on its own.
#}
{% macro normalize_title(column) -%}
{%- set kw = "remaster(ed)?|live|ao vivo|demo|edit|feat|ft|featuring|single|bonus|[0-9]{4} version" -%}
{%- set s = "lower(unaccent(" ~ column ~ "))" -%}
{%- set s = "regexp_replace(" ~ s ~ ", '[''’‘`]', '', 'g')" -%}
{%- set s = "replace(" ~ s ~ ", '&', ' and ')" -%}
{%- set s = "regexp_replace(" ~ s ~ ", '\\s*[\\(\\[][^\\)\\]]*\\m(" ~ kw ~ ")\\M[^\\)\\]]*[\\)\\]]', ' ', 'g')" -%}
{%- set s = "regexp_replace(" ~ s ~ ", '\\s+[-–—]\\s+[^-–—]*\\m(" ~ kw ~ ")\\M.*$', '')" -%}
{%- set s = "regexp_replace(" ~ s ~ ", '\\s+(featuring|feat|ft)\\M\\.?(\\s.*)?$', '')" -%}
{%- set s = "regexp_replace(" ~ s ~ ", '[^[:alnum:][:space:]]', ' ', 'g')" -%}
{%- set s = "regexp_replace(" ~ s ~ ", '\\s+', ' ', 'g')" -%}
btrim({{ s }})
{%- endmacro %}
