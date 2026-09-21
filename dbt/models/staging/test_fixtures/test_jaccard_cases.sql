-- Fixture for the Jaccard test (spec-03 requirement 13): the pair logic of
-- int_show_pairs applied to literal setlist sets whose answers are known.
-- Expected values live in tests/assert_jaccard_expected_outputs.sql.
-- Literal values only, no raw data. Each case has its own tour.
{{ consecutive_show_pairs("""(
    select * from (values
        -- identical sets: Jaccard 1
        ('id1', 'B', 'identical', date '2000-01-01', 'a'), ('id1', 'B', 'identical', date '2000-01-01', 'b'),
        ('id2', 'B', 'identical', date '2000-01-02', 'a'), ('id2', 'B', 'identical', date '2000-01-02', 'b'),
        -- disjoint sets: Jaccard 0
        ('dj1', 'B', 'disjoint', date '2000-02-01', 'a'), ('dj1', 'B', 'disjoint', date '2000-02-01', 'b'),
        ('dj2', 'B', 'disjoint', date '2000-02-02', 'c'), ('dj2', 'B', 'disjoint', date '2000-02-02', 'd'),
        -- {a,b,c} vs {a,b,d}: 2 of 4 = 0.5
        ('pa1', 'B', 'partial', date '2000-03-01', 'a'), ('pa1', 'B', 'partial', date '2000-03-01', 'b'),
        ('pa1', 'B', 'partial', date '2000-03-01', 'c'),
        ('pa2', 'B', 'partial', date '2000-03-02', 'a'), ('pa2', 'B', 'partial', date '2000-03-02', 'b'),
        ('pa2', 'B', 'partial', date '2000-03-02', 'd'),
        -- a chain: only ADJACENT shows are paired. {a}, {a,b}, {b,c}: 1/2 then 1/3
        ('ch1', 'B', 'chain', date '2000-04-01', 'a'),
        ('ch2', 'B', 'chain', date '2000-04-02', 'a'), ('ch2', 'B', 'chain', date '2000-04-02', 'b'),
        ('ch3', 'B', 'chain', date '2000-04-03', 'b'), ('ch3', 'B', 'chain', date '2000-04-03', 'c'),
        -- the date decides the order, not the key: the keys run against the dates
        ('k3', 'B', 'ordering', date '2000-05-01', 'x'),
        ('k1', 'B', 'ordering', date '2000-05-02', 'x'), ('k1', 'B', 'ordering', date '2000-05-02', 'y'),
        ('k2', 'B', 'ordering', date '2000-05-03', 'x'), ('k2', 'B', 'ordering', date '2000-05-03', 'y'),
        -- same date: ordered by show_key (t1 then t2), 1 of 3
        ('t2', 'B', 'tie', date '2000-06-01', 'a'), ('t2', 'B', 'tie', date '2000-06-01', 'c'),
        ('t1', 'B', 'tie', date '2000-06-01', 'a'), ('t1', 'B', 'tie', date '2000-06-01', 'b'),
        -- never paired: a single show, and the 'Unknown tour'
        ('so1', 'B', 'single', date '2000-07-01', 'a'),
        ('un1', 'B', 'Unknown tour', date '2000-08-01', 'a'), ('un2', 'B', 'Unknown tour', date '2000-08-02', 'a')
    ) as v(show_key, band, tour_name, show_date, song_key)
) as fixture""") }}
