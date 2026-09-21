-- Singular test for the split_medley macro (spec-02a item 8).
-- Diffs the fixture's actual rows against the hand-written expectation
-- in BOTH directions, so a missing row and an extra row both fail.
-- Passes when it returns no rows.
--
-- Note what is deliberately ABSENT from the expected set: the '', '   '
-- and NULL inputs produce no rows at all (there is no song to count).
with expected (input_song, part_idx, part, part_count) as (
    values
        ('Wonderwall',            1, 'Wonderwall',  1),
        ('Intro / Wonderwall',    1, 'Intro',       2),
        ('Intro / Wonderwall',    2, 'Wonderwall',  2),
        ('A / B / C',             1, 'A',           3),
        ('A / B / C',             2, 'B',           3),
        ('A / B / C',             3, 'C',           3),
        -- whitespace around the pieces is trimmed
        ('  A  /  B  ',           1, 'A',           2),
        ('  A  /  B  ',           2, 'B',           2),
        -- a bare slash (no surrounding spaces) is not a separator
        ('AC/DC Tribute',         1, 'AC/DC Tribute', 1),
        -- empty piece dropped BEFORE numbering: no gap, count is 2
        ('A /  / B',              1, 'A',           2),
        ('A /  / B',              2, 'B',           2),
        -- trailing separator: one real piece, so NOT a medley (count 1)
        ('Wonderwall / ',         1, 'Wonderwall',  1),
        -- a keyword-looking title with no separator is untouched
        ('Live Forever',          1, 'Live Forever', 1)
),

actual as (
    select input_song, part_idx::int, part, part_count::int
    from {{ ref('test_split_medley_cases') }}
)

select 'missing from actual' as problem, * from (
    select * from expected except select * from actual
) as m
union all
select 'unexpected in actual' as problem, * from (
    select * from actual except select * from expected
) as x
