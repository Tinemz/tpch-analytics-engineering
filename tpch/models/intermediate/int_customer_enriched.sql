select
    customer.customer_id,
    customer.name as customer_name,
    customer.address as customer_address,
    customer.nation_id,
    nation.name as nation_name,
    region.region_id,
    region.name as region_name,
    customer.phone as customer_phone,
    customer.account_balance as customer_account_balance,
    customer.market_segment as customer_market_segment
from {{ ref('stg_tpch__customer') }} as customer
left join {{ ref('stg_tpch__nation') }} as nation
    on customer.nation_id = nation.nation_id
left join {{ ref('stg_tpch__region') }} as region
    on nation.region_id = region.region_id
