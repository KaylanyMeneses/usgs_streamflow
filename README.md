# USGS Streamflow

Este repositório reúne um fluxo local de coleta, validação e análise de séries temporais de vazão de rios a partir de dados públicos do U.S. Geological Survey (USGS). A ideia principal é preparar um conjunto de dados de vazão diária em formato tabular, selecionar estações relevantes e resumir sua cobertura para apoiar análise posterior.

## Status atual

O projeto está em fase de preparação e análise exploratória de dados. Ele já inclui:

- catálogo e seleção de estações pelo USGS;
- downloads locais em Parquet para dados diários;
- validação de arquivos CSV/Parquet em `data/`;
- construção de tabelas de observações por estação;
- resumos de cobertura por local monitorado;
- visualização de séries temporais.

Ainda não há modelo preditivo, PINN, pipeline de machine learning ou rotina de previsão implementada. O foco atual é a preparação dos dados e a análise da qualidade da série observada.

## Estrutura do repositório

```text
usgs_streamflow/
├── .env
├── .gitignore
├── README.md
├── requirements.txt
├── data/
│   ├── desktop.ini
│   ├── intermediate/
│   ├── raw/
│   └── usgs/
│       ├── desktop.ini
│       ├── processed/
│       │   ├── catalog_stations.csv
│       │   ├── continuous_series_catalog.csv
│       │   ├── pares_nldi_UM_150km.csv
│       │   ├── pares_nldi_UT_150km.csv
│       │   ├── stations_full.parquet
│       │   └── stations_no_zero_continuous_candidates.csv
│       └── raw/
│           ├── catalog_timeseries.parquet
│           ├── daily_...*.parquet
│           └── continuous/
├── notebooks/
│   ├── análise_seleção.ipynb
│   ├── desktop.ini
│   └── usgs_streamflow.ipynb
├── reports/
│   └── figures/
├── src/
│   ├── __init__.py
│   ├── api.py
│   ├── catalog.py
│   ├── config.py
│   ├── main.py
│   ├── plots.py
│   └── processing.py
└── .venv/  (ambiente local, não versionado)
```

## Organização dos principais arquivos

### Dados

Os dados locais e procesados ficam em `data/` e incluem:

- `data/usgs/raw/`: catálogo e arquivos Parquet de séries diárias, com dados brutos do USGS e caches locais para reutilização;
- `data/usgs/processed/`: tabelas e arquivos processados, como `stations_full.parquet`, `catalog_stations.csv` e os pares NLDI;
- `data/intermediate/`: diretório reservado para intermediários e arquivos de apoio;
- `reports/figures/`: pasta para figuras produzidas durante a análise.

### Notebooks

- `notebooks/usgs_streamflow.ipynb`: notebook principal para consulta à API e preparação do catálogo, com seleção e download de dados diários;
- `notebooks/análise_seleção.ipynb`: notebook de análise local com base nos arquivos já presentes em `data/`, sem depender de nova chamada à API.

### Módulos Python

- `src/config.py`: define as rotas do projeto e as configurações padrão da API, além de ler variáveis do arquivo `.env` no diretório raiz;
- `src/api.py`: cliente opcional para a API OGC da USGS, com paginação e tratamento de erros temporários;
- `src/catalog.py`: carrega, valida e indexa CSV e Parquet, além de ler os caches diários;
- `src/processing.py`: transforma observações em tabela analítica por estação e calcula sumários de cobertura;
- `src/plots.py`: gera gráficos de série temporal por estação;
- `src/main.py`: orquestra a criação da tabela analítica e do resumo por estação.

## Fluxo atual do projeto

A pipeline atual combina dados do USGS com dados locais já coletados. O fluxo típico é:

1. consultar metadados da API e definir a seleção de séries;
2. armazenar arquivos em Parquet em `data/usgs/raw/`;
3. validar e carregar vetores de estações em `data/usgs/processed/`;
4. montar uma tabela de observações por data e estação;
5. resumir registros, vazões ausentes e vazões zero;
6. produzir gráficos de série temporal.

A estrutura de dados usada no código prefere preservar observações existentes e manter ausências como `NaN`, em vez de preencher ou interpolar dias faltantes. Isso permite distinguir:

- vazão zero válida;
- data sem linha retornada pela API;
- linha retornada sem valor numérico utilizável.

## Configuração do ambiente

O projeto usa Python com dependências listadas em `requirements.txt`.

### Instalação

No Windows, a partir da raiz do repositório:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### Variáveis de ambiente

O arquivo `src/config.py` carrega um `.env` na raiz do projeto quando ele existe. As variáveis usadas no código incluem, por exemplo:

- `USGS_API_VERSION` (padrão: `v0`)
- `USGS_DATE_START` (padrão: `2010-01-01`)
- `USGS_DATE_END` (padrão: `2024-12-31`)
- `USGS_PARAMETER_CODE` (padrão: `00060`)
- `USGS_STATISTIC_ID` (padrão: `00003`)
- `USGS_API_KEY` (opcional)

## Como usar

### 1. Executar a análise local

```python
from src.main import build_analysis_dataset

observations, summary = build_analysis_dataset()
print(observations.head())
print(summary.head())
```

### 2. Carregar um conjunto de dados específico

```python
from src.catalog import load_dataset

df = load_dataset("data/usgs/processed/stations_full.parquet")
print(df.head())
```

### 3. Visualizar uma estação

```python
from src.catalog import load_station_selection
from src.main import build_observation_table
from src.plots import plot_station_series

stations = load_station_selection()
observations = build_observation_table()
fig, ax = plot_station_series(observations, stations["monitoring_location_id"].iloc[0])
```

## Dados de referência e semântica

Os dados atuais refletem a configuração padrão do projeto:

- parâmetro: `00060` (discharge)
- estatística: `00003` (média diária)
- janela temporal: `2010-01-01` a `2024-12-31`
- unidade de vazão nos dados crus: ft³/s, com conversão local para m³/s em alguns fluxos analíticos

Há também arquivos e metadados relativos a séries contínuas e pares de estações, o que sugere uma comparação em andamento entre dados diários e observações de maior frequência. O projeto não assume automaticamente que toda série contínua tenha intervalo de 15 minutos; por isso, a frequência efetiva deve ser validada conforme a estação e o conjunto de dados.

## Dependências

O arquivo `requirements.txt` inclui:

- requests
- pandas
- pyarrow
- numpy
- matplotlib
- scipy
- statsmodels
- python-dotenv
- ipykernel

## Validação e qualidade

Até o momento, o repositório não inclui uma suíte de testes automatizados formalizada com `pytest` ou outra ferramenta de CI. A validação do projeto é majoritariamente manual e baseada em:

- inspeção de arquivos Parquet/CSV;
- execução dos notebooks;
- checagem de integridade das colunas e tipos;
- visualização de séries temporais e resumos de cobertura.

## Observações finais

Este projeto é um ambiente de preparação e análise hidrológica local, com foco em dados de vazão e seleção de estações monitoradas pela USGS. A estrutura atual reflete um trabalho ativo em exploração e processamento, sem um modelo de previsão implementado como etapa final.

Para acompanhar o desenvolvimento, o ponto de entrada mais útil continua sendo a combinação entre os notebooks e os módulos em `src/`, especialmente quando novos arquivos de dados forem adicionados em `data/usgs/`.

## Referências da USGS

- [API OGC Water Data](https://api.waterdata.usgs.gov/ogcapi/v1?f=html)
- [Coleções disponíveis](https://api.waterdata.usgs.gov/ogcapi/v1/collections?f=json)
- [Schema de monitoring-locations](https://api.waterdata.usgs.gov/ogcapi/v1/collections/monitoring-locations/schema?f=json)
- [Schema de time-series-metadata](https://api.waterdata.usgs.gov/ogcapi/v1/collections/time-series-metadata/schema?f=json)
- [Schema de daily](https://api.waterdata.usgs.gov/ogcapi/v1/collections/daily/schema?f=json)
- [Schema de continuous](https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/schema?f=json)
