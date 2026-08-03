-- Calendário diário exigido pelo MetricFlow. O TPC-H não traz tabela de datas,
-- então o intervalo é derivado de orders (1992-01-01 a 1998-08-02), estendido
-- até o fim de 1998 para que a agregação por ano cubra o último ano inteiro.
select date_day
from unnest(
    generate_date_array('1992-01-01', '1998-12-31', interval 1 day)
) as date_day
