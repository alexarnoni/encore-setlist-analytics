{#
    Test fixture for the normalize_title macro (spec-02a item 6,
    adjustment 4): dbt unit tests apply to models, not macros, so the
    macro is exercised through this small model instead. Fixed inputs
    and their hand-written expected outputs; `actual_title` is the macro
    applied to `input_title`. tests/assert_normalize_title_expected_outputs.sql
    fails on any row where the two differ.

    Reads no raw data — just literal values — so it is safe to build at
    any time. It lands as a view in the staging schema like every model
    in this folder.
#}
with cases as (
    select * from (values
        -- baseline / casing
        ('Wonderwall',                                   'wonderwall'),
        ('ROLL WITH IT',                                 'roll with it'),
        -- accents
        ('Café del Mar',                                 'cafe del mar'),
        -- apostrophes vanish WITHOUT leaving a space (straight and curly)
        ('Don''t Look Back in Anger',                    'dont look back in anger'),
        ('Don’t Look Back in Anger',                     'dont look back in anger'),
        ('Rock ''n'' Roll Star',                         'rock n roll star'),
        -- ampersand
        ('Rock & Roll Star',                             'rock and roll star'),
        -- punctuation becomes a space, whitespace collapses
        ('Mr. Brightside',                               'mr brightside'),
        ('Half-Life',                                    'half life'),
        ('  Multiple   Spaces  ',                        'multiple spaces'),
        -- edition segments: parentheses, brackets, and after " - "
        ('Live Forever (Remastered 2014)',               'live forever'),
        ('Song [Remastered]',                            'song'),
        ('Champagne Supernova - Remastered',             'champagne supernova'),
        ('Wonderwall (Live)',                            'wonderwall'),
        ('Some Might Say - Live at Knebworth 1996',      'some might say'),
        ('Stand By Me (Demo)',                           'stand by me'),
        ('Whatever - Radio Edit',                        'whatever'),
        ('Rock ''n'' Roll Star - 2014 Version',          'rock n roll star'),
        -- feat. clauses, with and without parentheses
        ('Get Lucky (feat. Pharrell Williams)',          'get lucky'),
        ('Get Lucky feat. Pharrell Williams',            'get lucky'),
        -- must NOT be stripped: keywords as ordinary title words...
        ('Live Forever',                                 'live forever'),
        -- ...whole-word matching ("edit" is not "editors")...
        ('Song (Editor''s Cut)',                         'song editors cut'),
        -- ...a parenthetical / dash segment without any keyword...
        ('(What''s the Story) Morning Glory?',           'whats the story morning glory'),
        ('Ain’t Got No - I Got Life',                    'aint got no i got life'),
        -- NULL in, NULL out
        (null::text,                                     null::text)
    ) as t(input_title, expected_title)
)

select
    input_title,
    expected_title,
    {{ normalize_title('input_title') }} as actual_title
from cases
