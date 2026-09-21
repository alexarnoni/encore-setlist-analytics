-- Singular test for the parse_setlistfm_date macro (spec-02a item 7).
-- Returns every fixture row whose macro output differs from the
-- hand-written expectation; passes when it returns no rows. Building
-- the fixture model at all already proves the macro never raises on
-- bad input (a raise would fail `dbt run`/the query, not just this test).
select
    input_date,
    expected_date,
    actual_date
from {{ ref('test_parse_setlistfm_date_cases') }}
where actual_date is distinct from expected_date
