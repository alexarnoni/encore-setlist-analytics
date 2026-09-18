-- int_performances must contain exactly the non-tape, non-cover entries of
-- stg_setlist_entries — no more (join fan-out), no fewer (a stray filter or
-- an inner join dropping unmatched songs). Unmatched songs MUST stay in;
-- they are how the match rate is measured (spec-02a item 13).
-- Returns one row describing the mismatch; passes when it returns none.
with expected as (

    select count(*) as n
    from {{ ref('stg_setlist_entries') }}
    where not is_tape and not is_cover

),

actual as (

    select count(*) as n from {{ ref('int_performances') }}

)

select expected.n as expected_rows, actual.n as actual_rows
from expected, actual
where expected.n <> actual.n
