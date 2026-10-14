select
    customer.customer_id,
    customer.name as customer_name,
    customer.address as customer_address,
    customer.nation_id,
    nation.name as nation_name,
    geo.country_pt,
    geo.iso3 as country_iso3,
    geo.latitude as country_latitude,
    geo.longitude as country_longitude,
    region.region_id,
    region.name as region_name,
    customer.phone as customer_phone,
    customer.account_balance as customer_account_balance,
    customer.account_balance < 0 as customer_has_negative_balance,
    customer.market_segment as customer_market_segment
from {{ ref('stg_tpch__customer') }} as customer
left join {{ ref('stg_tpch__nation') }} as nation
    on customer.nation_id = nation.nation_id
left join {{ ref('stg_tpch__region') }} as region
    on nation.region_id = region.region_id
left join {{ ref('nation_geo') }} as geo
    on customer.nation_id = geo.nation_id
