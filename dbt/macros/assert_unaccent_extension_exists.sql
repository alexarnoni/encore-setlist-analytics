{#
    CREATE EXTENSION needs superuser, which the app's runtime role
    (dbt's own connection) doesn't have — the extension is created by
    infra/postgres/init/03_create_unaccent_extension.sh instead
    (adjustment 3). This macro only checks it's there, so a missing
    extension fails clearly and immediately (on-run-start, in
    dbt_project.yml) instead of mid-way through the first model that
    calls normalize_title().
#}
{% macro assert_unaccent_extension_exists() %}
    {% if execute %}
        {% set results = run_query("SELECT 1 FROM pg_extension WHERE extname = 'unaccent'") %}
        {% if results.rows | length == 0 %}
            {{ exceptions.raise_compiler_error(
                "The 'unaccent' Postgres extension is not installed in the "
                "`encore` database. It must be created by a superuser — run "
                "infra/postgres/init/03_create_unaccent_extension.sh's SQL "
                "manually (`CREATE EXTENSION unaccent;`) against `encore`."
            ) }}
        {% endif %}
    {% endif %}
{% endmacro %}
