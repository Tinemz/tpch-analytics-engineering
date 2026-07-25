select
    r_regionkey as id,
    r_name as name,
    r_comment as comment
from {{ source('tpch', 'region') }}
