{#
    Override dbt's default: normally a model's custom +schema config
    gets concatenated onto the profile's target schema
    ("<target_schema>_<custom_schema>"). We want the layer schemas
    (staging/intermediate/analytics, set in dbt_project.yml) to be
    exactly those names, matching docs/context/structure.md.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
