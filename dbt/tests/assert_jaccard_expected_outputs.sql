-- Jaccard and pairing on known sets (spec-03 requirement 13): the fixture
-- model test_jaccard_cases must produce exactly these pairs, with these
-- intersection and union sizes. A full outer join, so a missing or an extra
-- pair fails too. Passes when it returns no rows.
with expected (tour_name, first_show_key, second_show_key, intersection_size, union_size) as (

    values
        ('identical', 'id1', 'id2', 2, 2),
        ('disjoint', 'dj1', 'dj2', 0, 4),
        ('partial', 'pa1', 'pa2', 2, 4),
        ('chain', 'ch1', 'ch2', 1, 2),
        ('chain', 'ch2', 'ch3', 1, 3),
        ('ordering', 'k3', 'k1', 1, 2),
        ('ordering', 'k1', 'k2', 2, 2),
        ('tie', 't1', 't2', 1, 3)

)

select
    coalesce(e.tour_name, a.tour_name) as tour_name,
    coalesce(e.first_show_key, a.first_show_key) as first_show_key,
    coalesce(e.second_show_key, a.second_show_key) as second_show_key,
    e.intersection_size as expected_intersection,
    a.intersection_size as actual_intersection,
    e.union_size as expected_union,
    a.union_size as actual_union
from expected as e
full outer join {{ ref('test_jaccard_cases') }} as a
    on a.tour_name = e.tour_name
   and a.first_show_key = e.first_show_key
   and a.second_show_key = e.second_show_key
where e.tour_name is null
   or a.tour_name is null
   or a.intersection_size <> e.intersection_size
   or a.union_size <> e.union_size
   or abs(a.jaccard - e.intersection_size::numeric / e.union_size) > 0.000001
