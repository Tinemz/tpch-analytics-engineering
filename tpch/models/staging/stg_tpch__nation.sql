select
    n_nationkey as id,
    n_name as name,
    n_regionkey as region_id,
    n_comment as comment
from {{ source('tpch', 'nation') }}
