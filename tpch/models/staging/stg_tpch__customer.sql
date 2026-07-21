select
    c_custkey    as id,
    c_name       as name,
    c_address    as address,
    c_nationkey  as nation_id,
    c_phone      as phone,
    c_acctbal    as account_balance,
    c_mktsegment as market_segment,
    c_comment    as comment
from {{ source('tpch', 'customer') }}
