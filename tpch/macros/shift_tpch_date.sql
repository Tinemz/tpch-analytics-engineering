{#
    Desloca uma data do TPC-H em `tpch_years_offset` anos (dbt_project.yml).

    O gerador produz pedidos de 1992 a 1998. Com 28 anos eles caem em 2020 a 2026, e o
    calendário gregoriano se repete a cada 28 anos dentro de 1901-2099: o dia da semana e os
    anos bissextos ficam iguais, então nenhuma sazonalidade semanal se perde. A tpch_raw fica
    como o gerador produziu; o deslocamento acontece só no staging.
#}
{% macro shift_tpch_date(column) -%}
    date_add({{ column }}, interval {{ var('tpch_years_offset') }} year)
{%- endmacro %}
