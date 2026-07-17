# TPC-H Analytics Engineering

Projeto de estudo de engenharia analítica de ponta a ponta usando o dataset
[TPC-H](https://www.tpc.org/tpch/): geração dos dados, ingestão em nuvem
(Google Cloud Storage + BigQuery) e modelagem com [dbt](https://www.getdbt.com/).

## Status atual

- [x] Geração do dataset TPC-H local via [`tpchgen-cli`](https://pypi.org/project/tpchgen-cli/), exportado em Parquet (`tpch_dataset/`)
- [x] Leitura exploratória dos arquivos gerados (`create_tpch.ipynb`)
- [ ] Upload dos arquivos Parquet para o Google Cloud Storage
- [ ] Carga dos dados do GCS para o BigQuery
- [ ] Início do projeto dbt (modelagem em cima das tabelas no BigQuery)

## Dataset

Os dados são gerados localmente com o `tpchgen-cli` e salvos como Parquet em
`tpch_dataset/` (ignorado no git — veja [Reproduzindo o dataset](#reproduzindo-o-dataset)):

- `customer.parquet`
- `lineitem.parquet`
- `nation.parquet`
- `orders.parquet`
- `part.parquet`
- `partsupp.parquet`
- `region.parquet`
- `supplier.parquet`

O notebook `create_tpch.ipynb` traz um exemplo de leitura dos arquivos com pandas.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Reproduzindo o dataset

Os arquivos Parquet não são versionados no git (dataset grande, gerado
localmente). Para recriá-los:

```bash
source venv/bin/activate
tpchgen-cli parquet -s 1 --output-dir tpch_dataset
```

(`-s 1` = scale factor 1, ~1GB de dados brutos. Ajuste conforme necessário.)

## Próximos passos

1. Subir os arquivos Parquet para um bucket no Google Cloud Storage
2. Criar as tabelas no BigQuery a partir dos arquivos no GCS (external tables ou load job)
3. Iniciar o projeto dbt apontando para o BigQuery como source
