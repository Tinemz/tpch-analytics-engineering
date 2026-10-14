select
    o_orderkey as order_id,
    o_custkey as customer_id,
    o_orderstatus as status,
    o_totalprice as total_price,
    {{ shift_tpch_date('o_orderdate') }} as order_date,
    o_orderpriority as priority,
    o_clerk as clerk,
    o_shippriority as ship_priority
from {{ source('tpch', 'orders') }}
