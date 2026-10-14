select
    customer_id,
    customer_name,
    customer_address,
    nation_id,
    nation_name,
    country_pt,
    country_iso3,
    country_latitude,
    country_longitude,
    region_id,
    region_name,
    customer_phone,
    customer_account_balance,
    customer_market_segment
from {{ ref('int_customer_enriched') }}
