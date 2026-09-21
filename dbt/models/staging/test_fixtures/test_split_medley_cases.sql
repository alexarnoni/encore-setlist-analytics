{#
    Fixture for the split_medley macro. Emits ACTUAL rows only —
    (input_song, part_idx, part, part_count); the hand-written expected
    rows live in tests/assert_split_medley_expected_outputs.sql, which
    diffs the two in both directions. (Unlike the scalar macros' fixtures
    this one is a set-returning macro, so expected/actual can't sit side
    by side on one row.)

    Needed because the real Oasis data contains NO medleys at all, so the
    split logic cannot be exercised against real rows.
#}
with cases as (
    select * from (values
        ('Wonderwall'),
        ('Intro / Wonderwall'),
        ('A / B / C'),
        ('  A  /  B  '),
        ('AC/DC Tribute'),
        ('A /  / B'),
        ('Wonderwall / '),
        ('Live Forever'),
        (''),
        ('   '),
        (null::text)
    ) as t(input_song)
)

select
    cases.input_song,
    p.part_idx,
    p.part,
    p.part_count
from cases
cross join lateral {{ split_medley('cases.input_song') }} as p
