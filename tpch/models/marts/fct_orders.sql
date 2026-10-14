with line_items as (
    select
        order_id,
        count(*) as item_count,
        sum(quantity) as total_quantity,
        sum(extended_price) as gross_revenue,
        sum(extended_price * (1 - discount)) as net_revenue
    from {{ ref('stg_tpch__lineitem') }}
    group by order_id
)

select
    orders.order_id,
    orders.customer_id,
    orders.order_date,
    orders.status as order_status,
    orders.priority as order_priority,
    orders.total_price,
    line_items.item_count,
    line_items.total_quantity,
    line_items.gross_revenue,
    line_items.net_revenue,
    left(cast(orders.order_id as string), 1) as order_id_first_digit
from {{ ref('stg_tpch__orders') }} as orders
left join line_items
    on orders.order_id = line_items.order_id
