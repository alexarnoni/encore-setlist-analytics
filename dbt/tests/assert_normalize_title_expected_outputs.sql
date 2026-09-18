-- Singular test for the normalize_title macro (spec-02a item 6).
-- Returns every fixture row whose macro output differs from the
-- hand-written expectation; the test passes when this returns no rows.
-- `is distinct from` so the NULL -> NULL case compares as equal.
select
    input_title,
    expected_title,
    actual_title
from {{ ref('test_normalize_title_cases') }}
where actual_title is distinct from expected_title
