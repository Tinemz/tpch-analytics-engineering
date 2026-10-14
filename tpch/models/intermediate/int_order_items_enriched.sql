-- Item de pedido com o custo do fornecedor, os prazos de entrega e o país de quem
-- compra e de quem vende. Base das métricas de lucro, entrega e comércio
-- internacional em fct_order_items.
select
    lineitem.order_id,
    lineitem.line_number,
    lineitem.part_id,
    lineitem.supplier_id,
    orders.customer_id,
    customer.nation_id as customer_nation_id,
    supplier.nation_id as supplier_nation_id,
    case
        when customer.nation_id = supplier.nation_id then 'nacional'
        else 'internacional'
    end as trade_type,
    lineitem.ship_date,
    lineitem.commit_date,
    lineitem.receipt_date,
    date_diff(lineitem.receipt_date, lineitem.ship_date, day) as delivery_days,
    lineitem.receipt_date > lineitem.commit_date as is_late,
    lineitem.ship_mode,
    lineitem.return_flag,
    lineitem.line_status,
    lineitem.quantity,
    lineitem.extended_price,
    lineitem.discount,
    partsupp.supply_cost,
    partsupp.supply_cost * lineitem.quantity as cost_amount
from {{ ref('stg_tpch__lineitem') }} as lineitem
left join {{ ref('stg_tpch__orders') }} as orders
    on lineitem.order_id = orders.order_id
left join {{ ref('stg_tpch__customer') }} as customer
    on orders.customer_id = customer.customer_id
left join {{ ref('stg_tpch__supplier') }} as supplier
    on lineitem.supplier_id = supplier.supplier_id
left join {{ ref('stg_tpch__partsupp') }} as partsupp
    on lineitem.part_id = partsupp.part_id
    and lineitem.supplier_id = partsupp.supplier_id
