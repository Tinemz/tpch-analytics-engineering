-- Calendário diário exigido pelo MetricFlow. O TPC-H não traz tabela de datas,
-- então o intervalo vem de orders: 1992-01-01 a 1998-08-02 no dado cru, deslocado
-- pela mesma macro do staging (2020-01-01 a 2026-08-02) e estendido até o fim do
-- último ano, para que a agregação por ano cubra o ano inteiro. Envios e entregas
-- vão até 31/12 desse ano, então o calendário também os cobre.
select date_day
from unnest(
    generate_date_array(
        {{ shift_tpch_date("date '1992-01-01'") }},
        {{ shift_tpch_date("date '1998-12-31'") }},
        interval 1 day
    )
) as date_day
