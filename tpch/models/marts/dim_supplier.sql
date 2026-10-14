select
    supplier.supplier_id,
    supplier.name as supplier_name,
    supplier.nation_id,
    nation.name as supplier_nation_name,
    region.name as supplier_region_name,
    supplier.account_balance as supplier_account_balance
from {{ ref('stg_tpch__supplier') }} as supplier
left join {{ ref('stg_tpch__nation') }} as nation
    on supplier.nation_id = nation.nation_id
left join {{ ref('stg_tpch__region') }} as region
    on nation.region_id = region.region_id
