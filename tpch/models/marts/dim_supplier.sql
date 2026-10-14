select
    supplier.supplier_id,
    supplier.name as supplier_name,
    supplier.nation_id,
    nation.name as supplier_nation_name,
    geo.country_pt as supplier_country_pt,
    geo.iso3 as supplier_country_iso3,
    geo.latitude as supplier_country_latitude,
    geo.longitude as supplier_country_longitude,
    region.name as supplier_region_name,
    supplier.account_balance as supplier_account_balance
from {{ ref('stg_tpch__supplier') }} as supplier
left join {{ ref('stg_tpch__nation') }} as nation
    on supplier.nation_id = nation.nation_id
left join {{ ref('stg_tpch__region') }} as region
    on nation.region_id = region.region_id
left join {{ ref('nation_geo') }} as geo
    on supplier.nation_id = geo.nation_id
