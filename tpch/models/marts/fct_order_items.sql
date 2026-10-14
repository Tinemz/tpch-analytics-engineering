select
    order_id,
    line_number,
    part_id,
    supplier_id,
    ship_date,
    ship_mode,
    return_flag,
    line_status,
    quantity,
    extended_price,
    discount,
    concat(
        cast(order_id as string), '-', cast(line_number as string)
    ) as order_item_id,
    extended_price * discount as discount_amount,
    extended_price * (1 - discount) as net_revenue
from {{ ref('stg_tpch__lineitem') }}
