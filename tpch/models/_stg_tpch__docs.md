{% docs tpch_customer_id %}
Identificador único do cliente no TPC-H (`c_custkey`).
Chave primária em `stg_tpch__customer` e `int_customer_enriched`; chave estrangeira nos demais modelos.
{% enddocs %}

{% docs tpch_nation_id %}
Identificador único do país no TPC-H (`n_nationkey`). São 25 países, cada um
pertencente a uma região.
Chave primária em `stg_tpch__nation`; chave estrangeira nos demais modelos.
{% enddocs %}

{% docs tpch_region_id %}
Identificador único da região geográfica no TPC-H (`r_regionkey`). São 5 regiões,
no topo da hierarquia `region -> nation`.
Chave primária em `stg_tpch__region`; chave estrangeira nos demais modelos.
{% enddocs %}

{% docs tpch_part_id %}
Identificador único da peça no TPC-H (`p_partkey`).
Chave primária em `stg_tpch__part`; chave estrangeira nos demais modelos.
{% enddocs %}

{% docs tpch_supplier_id %}
Identificador único do fornecedor no TPC-H (`s_suppkey`).
Chave primária em `stg_tpch__supplier`; chave estrangeira nos demais modelos.
{% enddocs %}

{% docs tpch_order_id %}
Identificador único do pedido no TPC-H (`o_orderkey`).
Chave primária em `stg_tpch__orders`; chave estrangeira nos demais modelos.
{% enddocs %}

{% docs tpch_comment %}
Texto livre gerado pelo TPC-H, sem valor analítico.
{% enddocs %}

{% docs tpch_phone %}
Telefone, com prefixo derivado do país.
{% enddocs %}

{% docs tpch_address %}
Endereço, gerado aleatoriamente pelo TPC-H.
{% enddocs %}

{% docs tpch_account_balance %}
Saldo em conta. Pode ser negativo.
{% enddocs %}
