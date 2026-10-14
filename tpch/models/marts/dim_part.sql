select
    part_id,
    name as part_name,
    manufacturer,
    brand,
    type as part_type,
    size as part_size,
    container,
    retail_price
from {{ ref('stg_tpch__part') }}
