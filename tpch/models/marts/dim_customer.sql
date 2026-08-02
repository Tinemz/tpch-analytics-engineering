select
    customer_id,
    customer_name,
    customer_address,
    nation_id,
    nation_name,
    region_id,
    region_name,
    customer_phone,
    customer_account_balance,
    customer_market_segment
from {{ ref('int_customer_enriched') }}
