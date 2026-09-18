{#
    Test fixture for the parse_setlistfm_date macro — same pattern as
    test_normalize_title_cases: literal inputs, hand-written expected
    outputs, the macro's result alongside. Checked by
    tests/assert_parse_setlistfm_date_expected_outputs.sql.
#}
with cases as (
    select * from (values
        -- valid
        ('14-08-1991', date '1991-08-14'),
        ('23-11-2025', date '2025-11-23'),
        ('29-02-2024', date '2024-02-29'),   -- leap day
        ('31-12-1999', date '1999-12-31'),   -- last day of a 31-day month
        -- impossible calendar dates -> NULL, not an error
        ('29-02-2023', null::date),          -- not a leap year
        ('31-04-2001', null::date),          -- April has 30 days
        ('31-02-2001', null::date),
        ('00-05-2001', null::date),          -- day 0
        ('15-00-2001', null::date),          -- month 0
        ('15-13-2001', null::date),          -- month 13
        ('15-05-0000', null::date),          -- year 0
        -- not the DD-MM-YYYY shape at all -> NULL
        ('2001-05-15', null::date),
        ('15/05/2001', null::date),
        ('5-5-2001',   null::date),
        ('garbage',    null::date),
        ('',           null::date),
        (null::text,   null::date)
    ) as t(input_date, expected_date)
)

select
    input_date,
    expected_date,
    {{ parse_setlistfm_date('input_date') }} as actual_date
from cases
