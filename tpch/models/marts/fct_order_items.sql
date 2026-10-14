select
    order_id,
    line_number,
    part_id,
    supplier_id,
    customer_id,
    customer_nation_id,
    supplier_nation_id,
    trade_type,
    ship_date,
    commit_date,
    receipt_date,
    delivery_days,
    -- Inteiro para poder somar: a taxa de atraso é a soma disto sobre o número de itens.
    cast(is_late as int64) as late_flag,
    ship_mode,
    return_flag,
    line_status,
    quantity,
    extended_price,
    discount,
    supply_cost,
    cost_amount,
    concat(
        cast(order_id as string), '-', cast(line_number as string)
    ) as order_item_id,
    extended_price * discount as discount_amount,
    extended_price * (1 - discount) as net_revenue,
    extended_price * (1 - discount) - cost_amount as profit
from {{ ref('int_order_items_enriched') }}
