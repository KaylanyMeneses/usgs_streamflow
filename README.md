# USGS Streamflow

Este repositório reúne um fluxo local de coleta, validação e análise de séries temporais de vazão de rios a partir de dados públicos do U.S. Geological Survey (USGS). A ideia principal é preparar um conjunto de dados de vazão diária em formato tabular, selecionar estações relevantes e resumir sua cobertura para apoiar análise posterior.

## Status atual

O projeto está em fase de preparação e análise exploratória de dados. Ele já inclui:

- catálogo e seleção de estações pelo USGS;
- pipeline de download (`src/download.py`) que salva um Parquet por série e retoma de onde parou se a execução cair;
- validação de arquivos CSV/Parquet em `data/`;
- construção de tabelas de observações por estação;
- resumos de cobertura por local monitorado;
- visualização de séries temporais;
- tabela de modelagem compartilhada (`src/model_data.py`) para o trabalho de modelos probabilísticos: rótulos de anomalia a partir dos códigos de qualidade da USGS, splits cronológicos, pontos escondidos para avaliação e normalização sem vazamento.

Os dados atuais cobrem **2010-01-01 a 2025-12-31** em três estados (California, Montana e Minnesota). A ordem dos notebooks está em [Ordem dos notebooks](#ordem-dos-notebooks), e o passo a passo para baixar os dados e montar a base está em [Do download à base dos modelos](#do-download-à-base-dos-modelos).

Os notebooks de entrada `04`–`06` preparam os dados, mas não ajustam os modelos. O Modelo 3 tem uma implementação de referência em `notebooks/modelo3_bayesian_gplvm.ipynb` e `src/gplvm_anomaly.py`; os Modelos 1 e 2 ainda estão pendentes.

## Estrutura do repositório

```text
usgs_streamflow/
├── .env
├── .gitignore
├── README.md
├── requirements.txt
├── data/
│   ├── intermediate/
│   ├── raw/
│   ├── exports/
│   │   ├── serie_2010_2025_200est.parquet         (a serie usada por todos os modelos; 02)
│   │   ├── serie_2010_2025_200est_stats.csv       (média e desvio por estação; 02)
│   │   ├── serie_2010_2025_200est_config.json     (configurações que geraram a serie; 02)
│   │   └── serie_2010_2025_200est/                (entradas geradas a partir desta serie)
│   │       ├── modelo1_gp/
│   │       │   ├── entradas.parquet               (uma linha por estação e dia; 04)
│   │       │   └── config.json
│   │       ├── modelo2_rgp/
│   │       │   ├── entradas.parquet               (uma linha por estação e dia; 05)
│   │       │   └── config.json
│   │       └── modelo3_gplvm/
│   │           ├── janelas.parquet                (uma linha por janela; 06)
│   │           └── config.json
│   └── usgs/
│       ├── processed/
│       │   ├── catalog_stations.csv
│       │   ├── continuous_series_catalog.csv
│       │   ├── pares_nldi_UM_150km.csv
│       │   ├── pares_nldi_UT_150km.csv
│       │   ├── stations_full.parquet
│       │   └── stations_no_zero_continuous_candidates.csv
│       └── raw/
│           ├── parquets/                                   (gerado por src/download.py)
│           │   ├── catalog_timeseries.parquet              (catálogo de séries, cache)
│           │   ├── sites_ST_<estado>_all.parquet           (locais Stream por estado, cache)
│           │   ├── daily_00060_00003_2010-01-01_2025-12-31/
│           │   │   └── <time_series_id>.parquet            (uma série por arquivo)
│           │   ├── daily_00060_00003_2010-01-01_2025-12-31_selected.csv
│           │   └── df_full_2010-01-01_2025-12-31.parquet   (tabela série × dia, opcional)
│           ├── backup/                                     (downloads antigos, 2010–2024, por lote)
│           └── continuous/
├── notebooks/
│   ├── 01_download.ipynb                  (baixa as séries da API)
│   ├── 02_serie_modelos.ipynb             (monta, confere e salva a serie)
│   ├── 03_guia_bases_modelos.ipynb        (guia: entradas, saídas e métricas dos modelos)
│   ├── 04_entradas_modelo1_gp.ipynb       (gera e salva a entrada do Modelo 1)
│   ├── 05_entradas_modelo2_rgp.ipynb      (gera e salva a entrada do Modelo 2)
│   ├── 06_entradas_modelo3_gplvm.ipynb    (gera e salva a entrada do Modelo 3)
│   ├── modelo3_bayesian_gplvm.ipynb      (treina, prevê e avalia o Modelo 3)
│   ├── análise_seleção.ipynb              (exploração, fora da sequência)
│   └── usgs_streamflow.ipynb              (exploração da API, fora da sequência)
├── references/
│   ├── Consideracoes_anomalias.md
│   ├── Formato dos dados caso univariado e multivariado.md
│   └── Relatório técnico GPs para séries com faltantes e anomalias.md
├── reports/
│   └── figures/
├── src/
│   ├── __init__.py
│   ├── api.py
│   ├── catalog.py
│   ├── config.py
│   ├── download.py
│   ├── main.py
│   ├── evaluation.py
│   ├── gplvm_anomaly.py
│   ├── model_data.py
│   ├── model_inputs.py
│   ├── plots.py
│   └── processing.py
└── .venv/  (ambiente local, não versionado)
```

## Organização dos principais arquivos

### Dados

Os dados locais e procesados ficam em `data/` e incluem:

- `data/usgs/raw/parquets/`: tudo o que o download gera. O catálogo e os locais Stream ficam em cache; cada série diária fica em `daily_<parâmetro>_<estatística>_<início>_<fim>/<time_series_id>.parquet`, e as séries escolhidas ficam listadas em `..._selected.csv`;
- `data/usgs/raw/backup/`: arquivos do download antigo (período 2010–2024, um arquivo por lote com hash no nome, como `daily_00060_00003_2010-01-01_2024-12-31_0d85f2e0eb25.parquet`). Não são usados pelo fluxo atual;
- `data/usgs/processed/`: tabelas e arquivos processados, como `stations_full.parquet`, `catalog_stations.csv` e os pares NLDI;
- `data/intermediate/`: diretório reservado para intermediários e arquivos de apoio;
- `reports/figures/`: pasta para figuras produzidas durante a análise.

### Notebooks

Os notebooks numerados formam a sequência do trabalho (veja [Ordem dos notebooks](#ordem-dos-notebooks)); os sem número são de exploração.

- `notebooks/01_download.ipynb`: baixa os dados da API com `src/download.py` (catálogo, locais Stream, seleção e séries diárias) e monta a tabela série × dia (`df_full`). É o ponto de partida do fluxo;
- `notebooks/02_serie_modelos.ipynb`: monta a tabela compartilhada (`serie`) a partir dos arquivos do `01_download.ipynb`, **salva uma única vez** em `data/exports/` (com as configurações usadas) e faz as conferências da base: rótulos, anomalias por estado e bloco, cobertura e estações candidatas para o caso local;
- `notebooks/03_guia_bases_modelos.ipynb`: lê a `serie` salva e mostra a entrada de cada modelo por bloco (`X_train`, `Y_train`, `X_val`…), o formato da saída e o cálculo das métricas, com um modelo de referência simples. É o guia para quem implementa um modelo;
- `notebooks/04_entradas_modelo1_gp.ipynb`: lê a `serie` salva, escolhe a estação do caso local e gera e salva a entrada do Modelo 1 (GP Student‑t) em `data/exports/<NOME>/modelo1_gp/`. Não ajusta o modelo;
- `notebooks/05_entradas_modelo2_rgp.ipynb`: o mesmo para o Modelo 2 (RGP‑t), em `.../modelo2_rgp/`;
- `notebooks/06_entradas_modelo3_gplvm.ipynb`: o mesmo para o Modelo 3 (Bayesian GPLVM), com as janelas, em `.../modelo3_gplvm/`;
- `notebooks/modelo3_bayesian_gplvm.ipynb`: seleciona hiperparâmetros com Optuna na validação, treina o Bayesian GPLVM usando a `serie` do `02` e as janelas exportadas pelo `06`, e avalia reconstrução, baseline climatológico, conformal e escores ELBO/LOO sem consultar a API;
- `notebooks/usgs_streamflow.ipynb`: notebook original de consulta à API, com a exploração do esquema e do catálogo. A lógica de download dele foi levada para `src/download.py`; continua útil para explorar a API;
- `notebooks/análise_seleção.ipynb`: notebook de análise local com base nos arquivos já presentes em `data/`, sem depender de nova chamada à API.

Nenhum notebook a partir do `02` consulta a API.

### Referências

A pasta `references/` guarda os documentos de planejamento do trabalho de modelagem. Eles não são lidos pelo código: servem como especificação de onde vieram as decisões implementadas em `src/model_data.py`, `src/model_inputs.py` e `src/evaluation.py`, e como guia comum para quem implementa cada modelo.

- `Relatório técnico GPs para séries com faltantes e anomalias.md`: descreve o problema (faltantes, sazonalidade, picos anômalos e dependência temporal), os três modelos (GP Student‑t, RGP‑t e Bayesian GPLVM), a divisão do trabalho e diferencia o plano original com BoTorch da implementação atual do GPLVM com Optuna e janela semanal fixa;
- `Formato dos dados caso univariado e multivariado.md`: define o formato da base comum e da saída dos modelos nos casos univariado e multivariado, como cada modelo lê os dados, os rótulos de anomalia a partir dos códigos de qualidade e o que entra no treino e na avaliação;
- `Consideracoes_anomalias.md`: análise de por que poucas estações têm anomalias rotuladas fora do treino, as opções para contornar isso (mais estações, `candidates`, teste maior) com os riscos de vazamento de cada uma, e onde mudar estados e filtros.

Os exemplos desses documentos são ilustrativos (por exemplo, séries horárias com `serie.csv`); quando houver diferença, vale o que está descrito neste README e no código (dados diários, `serie.parquet`).

### Módulos Python

- `src/config.py`: define as rotas do projeto e as configurações padrão da API, além de ler variáveis do arquivo `.env` no diretório raiz;
- `src/api.py`: cliente para a API OGC da USGS, com paginação, envio da chave (`X-Api-Key`) e nova tentativa em erros temporários (429, 5xx);
- `src/download.py`: pipeline de download (`DownloadConfig`, `run_pipeline`, `load_daily`). Repete as etapas do `usgs_streamflow.ipynb`, mas grava cada série assim que o lote dela termina, pula o que já está em disco e registra os lotes que falharam;
- `src/catalog.py`: carrega, valida e indexa CSV e Parquet (`load_dataset`, `build_dataset_index`, `export_dataset`). Também guarda os leitores do formato antigo (`stations_full.parquet` e um arquivo por lote em `data/usgs/raw/`), que o fluxo atual não usa;
- `src/processing.py`: transforma observações em tabela analítica por estação, calcula sumários de cobertura e completa o calendário diário sem imputar valores;
- `src/model_data.py`: monta a tabela de modelagem (rótulos, splits, seleção de estações, pontos escondidos e normalização);
- `src/model_inputs.py`: converte a tabela na entrada de cada modelo (`gp_inputs`, `rgp_inputs`, `gplvm_inputs`), sem NaN;
- `src/model_exports.py`: salva e lê a entrada de cada modelo em Parquet, em `data/exports/<NOME>/<modelo>/` (`gp_table`, `rgp_table`, `gplvm_table`, `save_inputs`, `load_inputs`), e a converte de volta nos arrays (`gp_arrays`, `rgp_arrays`, `gplvm_arrays`, que devolvem o mesmo que as funções de `src/model_inputs.py`). `gp_global_arrays` monta a entrada do GP com várias estações juntas (`X = [t, índice da estação]`), para um GP global;
- `src/evaluation.py`: confere o formato da saída dos modelos e calcula as métricas de reconstrução, conformal e detecção de anomalias;
- `src/gplvm_anomaly.py`: treino e inferência do Bayesian GPLVM, previsão Student-t e escore pontual leave-one-day-out;
- `src/plots.py`: gera gráficos de série temporal por estação;
- `src/main.py`: a partir dos arquivos gerados pelo download, monta a tabela de observações (`build_observation_table`), o resumo por estação (`build_analysis_dataset`) e a tabela de modelagem (`build_model_dataset`). Por padrão, usa o período, o parâmetro e a estatística de `src/config.py` (`.env`); para outros valores, passe `config=DownloadConfig(...)`.

## Ordem dos notebooks

```text
01_download  →  02_serie_modelos  →  03_guia_bases_modelos
                                  →  04_entradas_modelo1_gp     →  07_modelo1_gp     (futuro)
                                  →  05_entradas_modelo2_rgp    →  08_modelo2_rgp    (futuro)
                                  →  06_entradas_modelo3_gplvm  →  modelo3_bayesian_gplvm
```

| Ordem | Notebook | Entrada | Saída | Quando rodar |
|---|---|---|---|---|
| 1 | `01_download.ipynb` | API da USGS (chave no `.env`) | um Parquet por série em `data/usgs/raw/parquets/` e a lista `..._selected.csv` | uma vez, ou ao mudar período ou estados; se cair, rode de novo e ele continua |
| 2 | `02_serie_modelos.ipynb` | arquivos do `01` | `serie`, `stats` e `config` em `data/exports/` | uma vez por configuração da base; ao mudar `SelectionConfig` ou `SplitConfig`, troque `NOME` |
| 3 | `03_guia_bases_modelos.ipynb` | `serie` salva pelo `02` | nada (guia) | para consultar como montar entradas, saídas e métricas |
| 4–6 | `04_entradas_modelo1_gp.ipynb`, `05_entradas_modelo2_rgp.ipynb`, `06_entradas_modelo3_gplvm.ipynb` | `serie` salva pelo `02` | entrada de cada modelo em `data/exports/<NOME>/<modelo>/` (Parquet + `config.json`) | uma vez por base, depois do `02`; independentes entre si |
| Modelo 3 | `modelo3_bayesian_gplvm.ipynb` | `serie` do `02` e janelas do `06` | previsões, escores LOO, métricas e intervalos conformais | ao treinar/avaliar o GPLVM |
| Modelos 1–2 | notebooks dos modelos (futuros) | entrada salva pelo `04` ou `05` | previsões, escores e métricas | quando implementados |

Os notebooks `04`–`06` **só preparam os dados**: não ajustam nenhum modelo. O notebook do Modelo 3 lê a base e a entrada exportadas, sem baixar dados ou remontar janelas.

**Por que a `serie` tem um notebook só para ela:** os três modelos precisam ser avaliados nas mesmas estações, nos mesmos dias escondidos e com a mesma normalização. Os dias escondidos mudam se a `serie` for montada de novo com outra seleção de estações (veja [Uma `serie` para todos os modelos](#uma-serie-para-todos-os-modelos)). Por isso ela é montada e salva uma única vez no `02`, e todos os outros notebooks só leem o arquivo, com o mesmo `NOME`. O `02` guarda as configurações num `_config.json` ao lado da tabela e para com erro se alguém tentar gravar outra configuração com o mesmo `NOME`.

Pelo mesmo motivo, a entrada de cada modelo é gerada uma vez (`04`–`06`) e salva numa pasta com o nome da `serie` que a originou. Uma entrada nunca se mistura com outra base, e cada pasta tem um `config.json` com as escolhas usadas (estações, estação local, janela…). Se alguém tentar salvar outras escolhas por cima, o notebook para com erro.

## Fluxo atual do projeto

1. **Download** (`notebooks/01_download.ipynb` → `src/download.py`): consulta o catálogo de séries e os locais do tipo Stream, seleciona uma série por estação conforme `DownloadConfig.states` e baixa as séries diárias. A seleção fica em `..._selected.csv` e cada série em um Parquet em `data/usgs/raw/parquets/`. A configuração documentada baixa California, Montana e Minnesota; se os estados ou arquivos locais forem outros, o escopo também muda.
2. **Análise das observações** (`notebooks/análise_seleção.ipynb` → `build_analysis_dataset`): lê a seleção e os Parquets locais, associa cada série à sua estação e resume a cobertura. `df_analysis` contém as observações existentes; não cria linhas para dias sem registro.
3. **Calendário diário completo** (`complete_daily_calendar`, em `src/processing.py`): quando aplicado a `df_analysis`, cria uma linha para cada dia do período configurado para cada estação que já está nesse DataFrame. Dias sem observação recebem `NaN`. A função não consulta a API, não escolhe estações e não restringe os dados à Califórnia: o conjunto de estações vem da seleção carregada antes dela. Também é chamada por `build_model_dataset`, no `notebooks/02_serie_modelos.ipynb`.
4. **Tabela de modelagem** (`notebooks/02_serie_modelos.ipynb` → `src/model_data.py`): cria rótulos, splits cronológicos, seleção de estações pelo treino, pontos escondidos e normalização, e salva a `serie` em `data/exports/`.
5. **Entrada de cada modelo** (`src/model_inputs.py`, `src/model_exports.py`): guia no `notebooks/03_guia_bases_modelos.ipynb`; geradas e salvas nos `notebooks/04_entradas_modelo1_gp.ipynb`, `05_entradas_modelo2_rgp.ipynb` e `06_entradas_modelo3_gplvm.ipynb`.
6. **Modelos e métricas** (`src/evaluation.py`): nos notebooks dos modelos (`07`–`09`, futuros), que leem as entradas salvas.

**Sobre as saídas salvas nos notebooks:** os resultados já exibidos em `análise_seleção.ipynb` podem ser de uma execução anterior, com período e seleção de estações diferentes. Para saber quais dados estão sendo usados agora, confira `USGS.date_start`/`USGS.date_end` e a coluna de estado do arquivo `..._selected.csv`; ao alterar os arquivos ou a configuração, reexecute as células do notebook.

A estrutura de dados usada no código prefere preservar observações existentes e manter ausências como `NaN`, em vez de preencher ou interpolar dias faltantes. Isso permite distinguir:

- vazão zero válida;
- data sem linha retornada pela API;
- linha retornada sem valor numérico utilizável.

Na tabela de modelagem, "mascarar" um valor significa escondê-lo dos modelos (`visivel = 0`) sem apagá-lo: o valor verdadeiro continua em `y_bruto` para a avaliação. É diferente de um faltante real (`observado = 0`), em que não existe valor.

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

- `USGS_API_KEY` (recomendada: sem chave, o limite de requisições por hora é baixo e o erro 429 é frequente)
- `USGS_API_VERSION` (padrão: `v0`)
- `USGS_DATE_START` (padrão: `2010-01-01`)
- `USGS_DATE_END` (padrão: `2025-12-31`)
- `USGS_PARAMETER_CODE` (padrão: `00060`)
- `USGS_STATISTIC_ID` (padrão: `00003`)

O `.env` fica na raiz do projeto, não é versionado (está no `.gitignore`) e tem uma variável por linha, sem aspas:

```
USGS_API_KEY=sua_chave_de_40_caracteres
```

A chave é gratuita: https://api.waterdata.usgs.gov/signup/. O `.env` é lido quando o pacote `src` é importado; depois de alterá-lo, **reinicie o kernel** do notebook. Nunca escreva a chave dentro de um notebook, porque os `.ipynb` são versionados.

As datas do `.env` (ou os padrões de `src/config.py`) definem quais arquivos `build_model_dataset` e `build_analysis_dataset` leem. O download usa as datas passadas em `DownloadConfig`, no `01_download.ipynb`. Se mudar o período, mude nos dois lugares.

## Do download à base dos modelos

Passo a passo para baixar os dados da API e gerar a `serie` usada pelos três modelos. Antes, configure o ambiente e a chave (seção anterior).

### Passo 1: baixar os dados (`notebooks/01_download.ipynb`)

**Célula 1, caminho do projeto** (rode sempre que reiniciar o kernel):

```python
import sys
from pathlib import Path

PROJECT_ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(PROJECT_ROOT))
```

**Célula 2, parâmetros e download:**

```python
from src.download import DownloadConfig, run_pipeline, load_daily

cfg = DownloadConfig(
    date_start="2010-01-01",
    date_end="2025-12-31",
    parameter_code="00060",        # vazão (discharge), ft3/s
    statistic_id="00003",          # média diária
    states=("California", "Montana", "Minnesota"),  # None = todos os estados
    use_top_state=False,           # True = só o estado com mais estações (ignora a lista acima)
    require_full_coverage=False,   # True = só séries cujo registro cobre o período inteiro
    all_columns=True,              # True = todas as colunas que a API oferece
    max_sites=None,                # None = todas as estações dos estados
    seed=42,                       # semente do sorteio, usada quando há max_sites
    batch_size=8,                  # séries por requisição
)
selected, summary = run_pipeline(cfg)
```

`run_pipeline` faz, em ordem:

1. lê o esquema da API e escolhe os nomes de campo da versão (`begin_utc`/`end_utc` etc.);
2. baixa o catálogo de séries de vazão média diária (`time-series-metadata`), com cache em `catalog_timeseries.parquet`;
3. marca a cobertura de cada série (`overlaps`: toca o período; `full_coverage`: cobre o período inteiro, com 1 dia de tolerância);
4. busca os locais do tipo Stream (`site_type_code = ST`) de cada estado, com cache em `sites_ST_<estado>_all.parquet`, e mantém só as séries desses locais;
5. escolhe uma série por estação (a `primary` e, no empate, a de início mais antigo) e, se houver `max_sites`, sorteia as estações com `seed`. A lista vai para `..._selected.csv`;
6. baixa as séries pendentes em lotes de `batch_size` e grava **cada série no próprio arquivo** assim que o lote termina. Em cada lote, confere se vieram séries não pedidas e datas fora do período; se o lote passar de 50.000 linhas, é dividido ao meio.

**Se cair** (rede, erro 429, kernel reiniciado ou Ctrl+C): rode a Célula 2 de novo. O que já está em disco é pulado e só as séries pendentes são baixadas. Um lote que falha é registrado e pulado; a execução para depois de 5 falhas seguidas (`max_consecutive_failures`).

**Célula 3, conferir se terminou:**

```python
print(f"{len(summary['pending'])} séries pendentes | {len(summary['failures'])} lotes com falha")
```

Repita a Célula 2 até `pending` zerar. Séries para as quais a API não devolve dados no período ficam salvas como arquivo vazio e não são consultadas de novo.

**Célula 4 (opcional), juntar as séries:** `daily = load_daily(cfg, selected["time_series_id"])` devolve todas as observações num só DataFrame (o mesmo `daily` do notebook antigo). A partir dele, o `01_download.ipynb` monta e salva o `df_full` (uma linha por série e dia, com metadados da estação e vazão em m³/s).

**Cada arquivo de série** tem uma linha por dia com valor (dias sem valor não têm linha) e as colunas `time_series_id`, `monitoring_location_id`, `parameter_code`, `statistic_id`, `unit_of_measure`, `approval_status`, `qualifier`, `last_modified`, `time_api`, `date` e `value_cfs`.

Para trocar de estados, rode de novo com outra lista em `states`: as séries já baixadas são reaproveitadas, e o `..._selected.csv` passa a listar a nova seleção. Baixar a rede inteira (`states=None`, `use_top_state=False`) significa milhares de estações e mais de mil lotes, o que leva horas.

### Passo 2: montar e salvar a `serie` (`notebooks/02_serie_modelos.ipynb`)

Reinicie o kernel e rode o notebook em ordem. As configurações ficam na seção 2:

```python
SELECAO = SelectionConfig(n_sensors=200, min_completeness=0.95, max_zero_frac=0.05, candidates=None, seed=42)
SPLITS = SplitConfig(fracs=(0.60, 0.15, 0.10, 0.15), hidden_frac=0.10, hidden_block_len=1, seed=42)
NOME = "serie_2010_2025_200est"
```

Na primeira execução, a seção 3 chama `build_model_dataset(SELECAO, SPLITS)` e salva em `data/exports/` três arquivos: `<NOME>.parquet` (a `serie`), `<NOME>_stats.csv` (média e desvio por estação, que desfazem a normalização) e `<NOME>_config.json` (as configurações usadas). Nas execuções seguintes, lê os arquivos do disco; se as configurações forem diferentes das salvas, para com erro. **Para gerar uma base com outras configurações, troque `NOME`.**

`build_model_dataset` lê a lista `..._selected.csv` e as séries do período de `src/config.py`, monta uma linha por estação e dia (com `NaN` nos faltantes, sem imputação) e depois cria rótulos, blocos, seleção de estações, pontos escondidos e normalização. Para ler outro período ou outra pasta, passe `config=DownloadConfig(date_start=..., date_end=..., out_dir=...)`.

A seção 4 faz as conferências da base:

- `split_summary(serie)`: por bloco, o período, os dias visíveis, os escondidos, as anomalias e os provisórios. **Confira se `validacao`, `calibracao` e `teste` têm anomalias**: sem elas, as métricas de detecção ficam vazias (veja [Anomalias fora do treino](#anomalias-fora-do-treino));
- os qualificadores reais e quais viram anomalia;
- as anomalias por estado e bloco;
- a cobertura por estação e bloco (veja [Cobertura fora do treino](#cobertura-fora-do-treino));
- as estações candidatas para o caso local (veja [Avaliar a detecção numa estação](#avaliar-a-detecção-numa-estação-caso-local)).

### Passo 3: gerar e salvar a entrada de cada modelo (`04`, `05` e `06`)

Os três notebooks leem a `serie` salva no Passo 2, com o mesmo `NOME`:

```python
from src.config import EXPORT_ROOT

NOME = "serie_2010_2025_200est"
serie = pd.read_parquet(EXPORT_ROOT / f"{NOME}.parquet")
stats = pd.read_csv(EXPORT_ROOT / f"{NOME}_stats.csv", index_col="sensor_id")   # para voltar a ft³/s
```

Cada um monta a entrada do seu modelo a partir da mesma `serie`, com as 200 estações:

| Modelo | Notebook | Função | Como lê a `serie` | Arquivo salvo |
|---|---|---|---|---|
| 1. GP Student‑t | `04_entradas_modelo1_gp.ipynb` | `gp_inputs(serie, sensor_id)` | pares (dia, vazão) de uma estação, sem NaN | `modelo1_gp/entradas.parquet`: uma linha por (estação, dia), com `ajuste`, `visivel` e `escondido_aval` |
| 2. RGP‑t | `05_entradas_modelo2_rgp.ipynb` | `rgp_inputs(serie)` | todas as estações como sequências completas `(S, T)`, com 0 nos dias sem valor e uma máscara | `modelo2_rgp/entradas.parquet`: uma linha por (estação, dia), com `y_entrada`, `visivel`, `escondido_aval` e `y_true` |
| 3. Bayesian GPLVM | `06_entradas_modelo3_gplvm.ipynb` | `gplvm_inputs(serie, window=7)` | janelas de 7 dias de cada estação, montadas dentro de cada bloco, também com máscara | `modelo3_gplvm/janelas.parquet`: uma linha por janela, com `t_k`, `y_k`, `mask_k`, `true_k` e `hidden_k` |

Os arquivos ficam em `data/exports/<NOME>/`, ao lado de um `config.json` com as escolhas usadas (estações, estação local do GP, janela do GPLVM). Os rótulos de anomalia não vão para esses arquivos: ficam na `serie`, que é o que a avaliação lê. Os três notebooks são independentes entre si.

O `03_guia_bases_modelos.ipynb` mostra as três funções em uso, o formato da saída e as métricas. Os detalhes de cada uma estão em [Como cada modelo lê a tabela](#como-cada-modelo-lê-a-tabela).

### Passo 4: treinar e avaliar os modelos

Os notebooks de modelo não remontam as entradas: leem os arquivos exportados e os convertem nos arrays. O `modelo3_bayesian_gplvm.ipynb` usa a `serie` salva pelo `02` e as janelas do `06`; ele avalia previsão/reconstrução, intervalos conformais e detecção LOO. As funções `gp_arrays`, `rgp_arrays` e `gplvm_arrays` devolvem exatamente o mesmo que `gp_inputs`, `rgp_inputs` e `gplvm_inputs`:

```python
from src.model_exports import load_inputs, gp_arrays, gp_global_arrays, rgp_arrays, gplvm_arrays

# Modelo 1, local: uma estação por vez
entradas, cfg = load_inputs("serie_2010_2025_200est", "modelo1_gp")
gp = gp_arrays(entradas, cfg["estacao_local"])            # ou qualquer estação de cfg["estacoes"]

# Modelo 1, global: várias estações juntas, X = [t, índice da estação]
gp_g = gp_global_arrays(entradas, cfg["estacoes"])        # ou uma lista menor (ex.: vizinhas)
X_train, Y_train = gp_g["X_train"], gp_g["y_train"]       # gp_g["sensors"]: índice -> sensor_id

# Modelo 2: todas as estações
entradas, cfg = load_inputs("serie_2010_2025_200est", "modelo2_rgp")
rgp = rgp_arrays(entradas)                                # rgp["rnn_in"]: (S, T, 2)

# Modelo 3: janelas
entradas, cfg = load_inputs("serie_2010_2025_200est", "modelo3_gplvm")
gl = gplvm_arrays(entradas)                               # select_split(gl, "treino"), ...
```

Para usar menos estações, filtre `entradas` antes de converter (por exemplo, `entradas[entradas["sensor_id"].isin(lista)]`). A avaliação continua usando a `serie` e as funções de `src/evaluation.py`.

**Modelos globais:** as três entradas já têm as 200 estações. O RGP‑t e o GPLVM são globais por natureza. O GP pode ser local (`gp_arrays`, uma estação por vez) ou global (`gp_global_arrays`), lendo o mesmo `entradas.parquet`. No global, cada linha de `X` é `[t, índice da estação]`, e `sensors` traduz o índice de volta para o `sensor_id` na hora de devolver a saída. Com as 200 estações são cerca de 700 mil pontos de treino, então o GP global precisa ser variacional esparso (pontos de indução, `IndexKernel` de posto baixo) ou usar um subconjunto de estações. Os dias escondidos são os mesmos no local e no global.

### Onde mudar cada coisa

| O que | Onde |
|---|---|
| Período, estados, cobertura, número de estações baixadas | `DownloadConfig`, no `01_download.ipynb` |
| Estações que entram na `serie` (quantidade, completude, zeros, lista de candidatas) | `SelectionConfig`, no `02_serie_modelos.ipynb` (com outro `NOME`) |
| Proporção dos blocos, pontos escondidos, transformação | `SplitConfig`, no `02_serie_modelos.ipynb` (com outro `NOME`) |
| Qual base cada entrada usa | `NOME`, no início dos notebooks `04`–`06` |
| Estação do caso local | `ESTACAO`, no `04_entradas_modelo1_gp.ipynb` |
| Tamanho da janela e fração máxima sem valor do GPLVM | `JANELA` e `MAX_FALTANTE`, no `06_entradas_modelo3_gplvm.ipynb` |
| Gerar de novo uma entrada com outras escolhas | apagar a pasta `data/exports/<NOME>/<modelo>/` e rodar o notebook de novo |
| Códigos que viram anomalia | `PROBLEM_QUALIFIERS`, em `src/model_data.py` (depois, gere a base de novo com outro `NOME`) |
| Chave da API | `.env` |

Se `n_sensors` passar do número de estações que atendem aos filtros, aparece o erro `Só N estações passam nos filtros; pedido: M`; N é o máximo possível.

## Outros usos

Todos leem os arquivos locais gerados pelo download; nenhum consulta a API.

### 1. Executar a análise local

Uma linha por estação e dia com valor (dias sem linha não são criados), mais um resumo de cobertura por estação. É o que o `análise_seleção.ipynb` usa.

```python
from src.main import build_analysis_dataset

observations, summary = build_analysis_dataset()
print(observations.head())
print(summary.head())
```

### 2. Carregar um conjunto de dados específico

```python
from src.catalog import load_dataset

df = load_dataset("data/usgs/raw/parquets/df_full_2010-01-01_2025-12-31.parquet")
print(df.head())
```

Lê qualquer CSV ou Parquet dentro de `data/`.

### 3. Gerar a tabela de modelagem fora do notebook

```python
from src.main import build_model_dataset, export_dataset, SelectionConfig, SplitConfig

serie, stats = build_model_dataset(SelectionConfig(n_sensors=200), SplitConfig())
export_dataset(serie, "serie_2010_2025.parquet")   # data/exports/, sem sobrescrever
```

`stats` (média e desvio por estação) desfaz a normalização: `y_bruto = expm1(y * std + mean)`. Para o caso univariado, use `SelectionConfig(n_sensors=1)`. Para restringir a estações vizinhas, passe `candidates=(...)` com IDs tirados, por exemplo, de `pares_nldi_*_150km.csv`.

### 4. Visualizar uma estação

```python
from src.main import build_observation_table
from src.plots import plot_station_series

observations = build_observation_table()
fig, ax = plot_station_series(observations, observations["monitoring_location_id"].iloc[0])
```

### Formato antigo

Os arquivos do download antigo (2010–2024, um arquivo por lote) estão em `data/usgs/raw/backup/`. O fluxo atual não os usa. Os leitores desse formato continuam em `src/catalog.py` (`load_station_selection`, `load_cached_daily_observations`), caso seja preciso consultá-los.

## Tabela de modelagem

`build_model_dataset` devolve uma tabela no formato longo: uma linha por (estação, dia), com o calendário completo do período. Exemplo ilustrativo da saída:

| sensor_id | t | data | split | y_bruto | y | observado | escondido_aval | visivel | aprovacao | qualificador | anomalia |
|---|---|---|---|---|---|---|---|---|---|---|---|
| USGS-11532500 | 0 | 2010-01-01 | treino | 812.0 | 0.41 | 1 | 0 | 1 | Approved | | 0 |
| USGS-11532500 | 1 | 2010-01-02 | treino | NaN | NaN | 0 | 0 | 0 | | | 0 |
| USGS-11532500 | 19 | 2010-01-20 | treino | 2350.0 | 1.37 | 1 | 0 | 1 | Approved | ESTIMATED;ICE | 1 |
| USGS-11532500 | 3339 | 2019-02-22 | validacao | 640.0 | 0.18 | 1 | **1** | 0 | Approved | | 0 |
| USGS-11532500 | 4657 | 2022-10-02 | teste | 95.3 | −1.22 | 1 | 0 | 1 | Provisional | | 0 |
| USGS-11530500 | 0 | 2010-01-01 | treino | 1540.0 | 0.33 | 1 | 0 | 1 | Approved | | 0 |

| Coluna | Significado |
|---|---|
| `sensor_id` | estação (`monitoring_location_id`) |
| `t` | índice do dia dentro da estação (0, 1, 2, …); o mesmo `t` é o mesmo dia em todas as estações |
| `data` | data do dia |
| `split` | bloco cronológico: `treino`, `validacao`, `calibracao` ou `teste` |
| `y_bruto` | vazão original em ft³/s (NaN quando não existe valor) |
| `y` | `log1p(y_bruto)` padronizado por estação, com média e desvio só do treino |
| `observado` | 1 se existe valor; 0 se é faltante real |
| `escondido_aval` | 1 se o valor existe mas foi escondido dos modelos para medir a reconstrução |
| `visivel` | 1 se o modelo pode usar o valor (`observado = 1` e `escondido_aval = 0`) |
| `aprovacao` | status de revisão da USGS: `Approved` (revisado) ou `Provisional` (ainda pode mudar); vazio sem valor |
| `qualificador` | qualificador original da USGS, por extenso e em maiúsculas (ex.: `ICE`, `EQUIP`, `ESTIMATED`); vazio quando não há; vários são separados por `;` |
| `anomalia` | 1 se `qualificador` indica problema (`EQUIP`, `ICE`, `BACKWATER`, `MAINT…`, `FLOOD`); só para avaliação |

### Uso de cada split

| Split | Padrão | Uso |
|---|---|---|
| `treino` | 60% (2010-01-01 → 2019-08-07) | ajustar os modelos (ELBO) e as estatísticas de normalização |
| `validacao` | 15% (2019-08-08 → 2021-12-31) | objetivo da otimização Bayesiana: NLPD nos pontos escondidos |
| `calibracao` | 10% (2022-01-01 → 2023-08-07) | conformal prediction: quantil dos resíduos normalizados nos pontos escondidos |
| `teste` | 15% (2023-08-08 → 2025-12-31) | métricas finais, usado uma única vez |

As datas valem para o período 2010–2025 com as frações padrão; confira em `split_summary(serie)`.

Regras para os modelos:

- os modelos recebem apenas valores com `visivel = 1`; `aprovacao`, `qualificador` e `anomalia` nunca entram no treino;
- dias com código de problema entram no treino normalmente: são as anomalias que os modelos devem detectar;
- parâmetros (ELBO) usam só `treino`; hiperparâmetros externos (janela, dimensão latente, pontos de indução, ν) usam só `validacao`; o conformal usa só `calibracao`.

### O que entra no treino

- Filtro único para todos: `split == "treino"` e `visivel == 1`.
- Isso inclui todos os dias de treino com valor, **inclusive os com código de problema** (`EQUIP`, `ICE` etc.).
- Ficam de fora só os dias sem valor (NaN). No bloco de treino nada é escondido; a máscara (`escondido_aval`) só existe em `validacao`, `calibracao` e `teste`, com semente fixa (os mesmos dias em toda execução). Para desligá-la: `SplitConfig(hidden_frac=0)`.
- Nenhum NaN entra nos cálculos dos modelos (o GPyTorch não aceita NaN).

### Uma `serie` para todos os modelos

A mesma `serie` é a base dos três modelos. Cada um só a lê de um jeito diferente (`gp_inputs`, `rgp_inputs`, `gplvm_inputs`; veja abaixo). Usar o mesmo arquivo garante que todos tenham as mesmas estações, os mesmos dias escondidos, a mesma normalização e os mesmos rótulos de anomalia. Assim, a diferença entre os resultados vem dos modelos, e não dos dados.

**Monte uma vez, salve e leia sempre o mesmo arquivo.** Os dias escondidos são sorteados por um único gerador aleatório que percorre as estações em sequência (`hide_evaluation_points`, em `src/model_data.py`). Se a `serie` for montada de novo com outra seleção (outro `n_sensors`, `seed` ou `candidates`), os dias escondidos de uma mesma estação mudam, e os modelos deixam de ser avaliados nos mesmos pontos. Filtrar uma `serie` já salva não tem esse problema.

Por isso a montagem fica só no `02_serie_modelos.ipynb`, que salva a `serie`, o `stats` e as configurações em `data/exports/` (cerca de 10 MB com 200 estações) e para com erro se as configurações mudarem sem troca de `NOME`. Os notebooks `04`–`06` só leem o arquivo (código no [Passo 3](#passo-3-gerar-e-salvar-a-entrada-de-cada-modelo-04-05-e-06)).

**Global ou local é só filtro:**

- **Uma estação** (GP local): `gp_inputs(serie, sensor_id=...)` já filtra por dentro.
- **Um subconjunto** (por exemplo, estações vizinhas para um GP multitarefa, ou menos estações para aliviar o RGP‑t e o GPLVM, que recebem todas juntas): `serie[serie["sensor_id"].isin(lista)]`, antes de chamar `rgp_inputs` ou `gplvm_inputs`.
- **Todas** (GP multitarefa, RGP‑t, GPLVM): a `serie` inteira.

### Cobertura fora do treino

Os filtros de seleção (`min_completeness`, `max_zero_frac`) só olham o treino, para não usar o futuro. A consequência é que uma estação pode estar completa no treino e quase vazia depois: com os dados atuais, 8 das 200 estações têm menos de 50% de dias visíveis em algum bloco, e 3 não têm nenhum dia escondido no teste. Nessas estações, a avaliação da reconstrução fica limitada ou impossível. Fora do treino, cerca de 90% de dias visíveis é o máximo esperado, porque 10% são escondidos de propósito.

```python
ordem = ["treino", "validacao", "calibracao", "teste"]
por_bloco = (serie.groupby(["sensor_id", "split"])
             .agg(dias=("t", "size"), visiveis=("visivel", "sum"),
                  escondidos=("escondido_aval", "sum"), anomalias=("anomalia", "sum")))
cobertura = (por_bloco["visiveis"] / por_bloco["dias"]).unstack()[ordem].round(2)
escondidos = por_bloco["escondidos"].unstack()[ordem]
problemas = cobertura[(cobertura < 0.5).any(axis=1) | (escondidos["teste"] == 0)]
```

Mantenha essas estações e declare a limitação, ou remova-as da análise. Se removê-las pela cobertura do teste, declare que o critério usa o período de teste.

### Como cada modelo lê a tabela

**Modelo 1, GP Student‑t:** pares (tempo, valor), sem NaN. O GP prevê depois em qualquer `t`, inclusive nos dias faltantes.

```python
tr = serie[(serie.sensor_id == sid) & (serie.split == "treino") & (serie.visivel == 1)]
t_train = torch.tensor(tr["t"].values, dtype=torch.float32)
y_train = torch.tensor(tr["y"].values, dtype=torch.float32)
t_all = torch.tensor(serie.loc[serie.sensor_id == sid, "t"].values, dtype=torch.float32)  # prediction
```

Com várias estações: um GP por estação (laço sobre `sensor_id`).

**Modelo 2, RGP‑t:** sequência completa e ordenada, porque a ordem dos dias importa. Dias sem valor visível viram 0 e a máscara manda o modelo ignorá-los.

```python
y_vis = serie.assign(y=serie["y"].where(serie["visivel"] == 1, 0.0))              # hides NaN and masked days
wide_y = y_vis.pivot(index="sensor_id", columns="t", values="y")                  # (S, T)
wide_m = serie.pivot(index="sensor_id", columns="t", values="visivel").fillna(0)   # (S, T)
rnn_in = torch.stack([torch.tensor(wide_y.values), torch.tensor(wide_m.values)], dim=-1).float()  # (S, T, 2)
```

As estações entram como um lote; o ELBO usa só os termos com máscara 1 e só os dias do treino.

**Modelo 3, Bayesian GPLVM:** janelas (por exemplo, semanais: 7 dias) de cada estação, empilhadas. Células sem valor visível viram 0 e a máscara as exclui da verossimilhança.

```python
Y    : (n_janelas, 7)   # values of y, NaN -> 0
mask : (n_janelas, 7)   # column visivel
sensor_id, t_idx        # station and day of each cell, to map results back to the table
```

As janelas são montadas dentro de cada split (nunca atravessando dois blocos). Janelas com mais de 50% sem valor são descartadas.

### Obter `X_train`, `Y_train`, `X_val`, `Y_val`… em cada modelo

`Y_val` (e de teste) com os valores verdadeiros dos dias escondidos é **só para avaliar**: nunca entra no ajuste.

```python
from src.model_inputs import gp_inputs, rgp_inputs, gplvm_inputs, select_split

# Modelo 1: GP Student-t (uma estação por vez; X = tempo t)
gp = gp_inputs(serie, sensor_id=sid)
X_train, Y_train = gp["t_train"], gp["y_train"]                      # ajuste
va, te = gp["splits"]["validacao"], gp["splits"]["teste"]
X_val_ctx, Y_val_ctx = va["t_visible"], va["y_visible"]              # contexto visível (pode ser lido)
X_val, Y_val = va["t_hidden"], va["y_hidden"]                        # reconstrução: prever X_val, comparar com Y_val
X_test, Y_test = te["t_hidden"], te["y_hidden"]
X_test_score = te["t_all"]                                           # dias que recebem escore de anomalia

# Modelo 2: RGP-t (todas as estações; X = sequência inteira, as máscaras escolhem o bloco)
rgp = rgp_inputs(serie)
X = rgp["rnn_in"]                                                    # (S, T, 2), igual para todos os blocos
Y = rgp["y"]                                                         # (S, T), 0 onde não há valor visível
M_train = rgp["fit_mask"]                                            # dias que entram no ELBO
M_val, M_test = rgp["eval_masks"]["validacao"], rgp["eval_masks"]["teste"]  # dias escondidos
Y_true = rgp["y_true"]                                               # valores verdadeiros (avaliação): Y_true[M_val == 1]

# Modelo 3: Bayesian GPLVM (não supervisionado: só Y; X é latente e aprendido)
gl = gplvm_inputs(serie, window=7)
tr, va, te = (select_split(gl, b) for b in ("treino", "validacao", "teste"))
Y_train, M_train = tr["Y"], tr["mask"]                               # ajuste
Y_val, M_val = va["Y"], va["mask"]                                   # inferir q(X) e calcular o escore
Y_val_true, H_val = va["Y_true"], va["hidden"]                       # reconstrução nas células com H_val == 1
```

### Entrada por bloco

| Bloco | Modelo faz | Função de apoio |
|---|---|---|
| `treino` | ajusta os parâmetros só com dias visíveis | GP: `t_train`/`y_train`; RGP: `fit_mask`; GPLVM: `select_split(gl, "treino")` |
| `validacao`, `calibracao`, `teste` | prevê com parâmetros congelados; pode ler dias visíveis como entrada, nunca os escondidos | GP: `splits[bloco]` + `t_context`; RGP: `split_masks[bloco]` e `eval_masks[bloco]`; GPLVM: `select_split(gl, bloco)` |

### Vazão zero × o 0 de preenchimento

O 0 colocado nas lacunas (RGP e GPLVM) está na escala de `y`, não na escala da vazão. Uma vazão zero medida vira `y = (log1p(0) − média) / desvio`, um valor negativo e grande, com `visivel = 1`: é uma observação real e entra no modelo. O 0 de preenchimento tem `visivel = 0` e é ignorado. O que separa os dois casos é a máscara, não o valor. O filtro `max_zero_frac` exclui rios intermitentes; nas estações que sobram, dias de vazão zero tendem a receber escore alto e merecem conferência (qualificadores `Zfl`/`Dry`).

### Saída dos modelos (detecção de anomalias)

Os três modelos entregam a mesma tabela, uma linha por (estação, dia):

| sensor_id | data | split | media | q025 | q975 | escore | alerta |
|---|---|---|---|---|---|---|---|
| USGS-11532500 | 2023-01-10 | teste | 0.42 | −0.30 | 1.15 | 0.9 | 0 |
| USGS-11532500 | 2023-01-11 | teste | 0.45 | −0.28 | 1.18 | 7.3 | 1 |
| USGS-11532500 | 2023-01-12 | teste | 0.47 | −0.25 | 1.20 | NaN | |

- `media`, `q025`, `q975`: previsão e intervalo de 95% na escala de `y` (use `stats` para voltar a ft³/s).
- `escore`: quanto maior, mais anômalo. Modelos 1 e 2: 1/E[τ] (nos dias de validação e teste, a mesma fórmula aplicada à previsão do modelo). Modelo 3: −ELBO da janela, repetido em cada dia dela; o notebook também exporta `escore_loo` como análise adicional por dia. Escores podem ser NaN quando não há previsão.
- `alerta`: 1 se o escore passa de um limiar definido na `calibracao` (ex.: percentil 99, ou via conformal), nunca no teste.

### Duas avaliações separadas

| Avaliação | Pergunta | Colunas | Métricas |
|---|---|---|---|
| Reconstrução | o modelo acerta o valor quando o dado falta? | `escondido_aval` (só dias normais) e `y_bruto` | RMSE, NLPD, cobertura do intervalo de 95% |
| Detecção | o modelo aponta os dias com problema? | `escore`/`alerta` contra `anomalia` | AUC, recall e precisão, só no `teste` |

A máscara não ajuda nem atrapalha a detecção: os dias escondidos são sorteados só entre dias sem código de problema.

**Dados provisórios:** os anos mais recentes (bloco de teste) ainda não foram revisados pela USGS e podem ter erros sem rótulo. Mostrem as métricas finais separando dados `Approved` e `Provisional`.

### Anomalias fora do treino

Os rótulos de problema são raros e se concentram em poucas estações. Com os dados atuais (200 estações de California, Montana e Minnesota), só 33 estações têm alguma anomalia no teste. Com poucas estações (por exemplo, `n_sensors=10`), é comum a `serie` ficar sem nenhuma anomalia em `validacao`, `calibracao` e `teste`, e as métricas de detecção ficam vazias.

- **Para a `serie` usada por todos os modelos:** use mais estações (`n_sensors` alto, até todas as elegíveis) e inclua estados frios, onde o rótulo `ICE` é comum. Não monte a `serie` escolhendo estações ou a `seed` pelas anomalias do teste: os resultados gerais deixariam de representar uma estação qualquer.
- **Rótulos inconsistentes:** a mesma estação pode ter invernos rotulados com `ICE` em alguns anos e só `ESTIMATED` em outros. Trate a precisão como limite inferior.

A análise completa está em `references/Consideracoes_anomalias.md`.

### Avaliar a detecção numa estação (caso local)

Para saber se o modelo detecta anomalias numa estação, ela precisa ter anomalias rotuladas no teste. **Escolher a estação por isso não é vazamento**: é escolher um caso de teste que contém o fenômeno a ser medido. O vazamento está em outras coisas:

| Situação | É vazamento? |
|---|---|
| Escolher estações com anomalias no teste para **avaliar** a detecção, antes de rodar o modelo | não; declare o critério no trabalho |
| Usar o teste para **ajustar** o modelo, escolher hiperparâmetros ou o limiar | sim |
| Rodar o modelo em várias estações e **relatar só as que deram bom resultado** | sim (*cherry-picking*) |
| Apresentar o resultado dessas estações como se valesse para **qualquer** estação | sim; o conjunto foi escolhido por ter anomalias |

O limiar de alerta (`threshold_from_calibration`) é o percentil dos escores da `calibracao` e não usa os rótulos, então basta a estação ter anomalias no teste. Para listar as candidatas, usando `por_bloco` e `cobertura` de [Cobertura fora do treino](#cobertura-fora-do-treino):

```python
anomalias = por_bloco["anomalias"].unstack()[ordem]
candidatas = pd.DataFrame({"anom_treino": anomalias["treino"], "anom_teste": anomalias["teste"],
                           "visivel_teste": cobertura["teste"]})
candidatas = candidatas[(candidatas["anom_teste"] >= 20) & (candidatas["visivel_teste"] >= 0.8)]
```

Com os dados atuais, 13 estações passam nesse critério (por exemplo, `USGS-11224000`, com 125 dias rotulados no teste).

Três formas de avaliar a detecção localmente, que se complementam:

1. **Rótulos reais no teste:** 2 ou 3 estações da lista de candidatas, escolhidas antes de rodar o modelo. Mede se o modelo detecta problemas reais em dados novos.
2. **Dentro da amostra (treino):** o GP Student‑t marca como outliers, durante o ajuste, os pontos com E[τ] pequeno. Como os rótulos não entram no ajuste, comparar o escore do treino com a `anomalia` do treino não é vazamento. Mede se o modelo isola os pontos ruins dos dados que viu, mas não se generaliza.
3. **Anomalias sintéticas:** somar picos artificiais em dias do teste de uma estação limpa (por exemplo, +3 desvios na escala de `y`) e ver se o modelo os encontra. Tem gabarito exato, ao contrário dos rótulos da USGS, mas os resultados valem para esse tipo de pico e não para anomalias reais em geral (ressalva do relatório técnico).

## Condições e restrições dos dados

| Condição | Padrão | Onde configurar |
|---|---|---|
| Vazão média diária (`00060` / `00003`) | fixo | `DownloadConfig` / `.env` |
| Período | 2010-01-01 a 2025-12-31 | `DownloadConfig(date_start, date_end)`; `USGS_DATE_START`, `USGS_DATE_END` |
| Estados baixados | California, Montana, Minnesota | `DownloadConfig(states, use_top_state)` |
| Só locais do tipo Stream (`ST`) | fixo (exclui canais, valas, lagos, nascentes e riachos de maré) | `src/download.py` |
| Cobertura do registro no catálogo | toca o período (`overlaps`) | `DownloadConfig.require_full_coverage` |
| Uma série por estação | `primary` e, no empate, a mais antiga | `src/download.py` (`select_series`) |
| Completude mínima no treino | ≥ 95% dos dias com valor | `SelectionConfig.min_completeness` |
| Fração de zeros no treino (exclui rios intermitentes) | ≤ 5% | `SelectionConfig.max_zero_frac` |
| Vazão negativa | estação descartada | fixo |
| Número de estações | 10 (1 = univariado) | `SelectionConfig.n_sensors` |
| Restringir a um conjunto de estações (ex.: vizinhas) | desligado | `SelectionConfig.candidates` |
| Proporção dos splits | 60 / 15 / 10 / 15 | `SplitConfig.fracs` |
| Pontos escondidos por bloco fora do treino | 10% | `SplitConfig.hidden_frac` |
| Tamanho das lacunas escondidas | 1 dia (isolado) | `SplitConfig.hidden_block_len` |
| Transformação | `log1p` + padronização por estação | `SplitConfig.log_transform` |
| Códigos que viram `anomalia = 1` | `EQUIP`, `ICE`, `BACKWATER`, `MAINT…`, `FLOOD` (e as abreviações Eqp, Ice, Bkw, Mnt, Fld) | `PROBLEM_QUALIFIERS` em `src/model_data.py` |

A API OGC devolve os qualificadores por extenso e em maiúsculas, juntados por `;` (ex.: `ESTIMATED;ICE`, `EQUIP;ESTIMATED`). `ESTIMATED`, `REVISED`, `FORCEINTERPOLATION`, `RATINGDEV` e outros registros de processamento não viram anomalia. A seção 4.1 do `02_serie_modelos.ipynb` lista os qualificadores reais e mostra quais viram anomalia.

## Pontos de atenção: vazamento de dados e viés

| Risco | Por que acontece | Como o código evita / o que fazer |
|---|---|---|
| Split aleatório entre dias | dias vizinhos são quase iguais; o teste "vê" o treino | splits em blocos cronológicos, com as mesmas datas de corte para todas as estações |
| Normalização com dados futuros | média e desvio calculados com validação ou teste | estatísticas só de `treino` com `visivel = 1` |
| Seleção de estações olhando o futuro | completude ou zeros calculados no período inteiro | filtros calculados só no bloco `treino` |
| Rótulos no treino | `anomalia`, `aprovacao` ou `qualificador` usados como entrada do modelo ou para montar a `serie` | nenhuma função de treino ou seleção usa essas colunas; a `serie` compartilhada não é filtrada por número de anomalias |
| Otimização tocando o teste | hiperparâmetros ou limiares escolhidos olhando o teste | otimização Bayesiana só em `validacao`, conformal só em `calibracao`, teste usado uma vez |
| Ponto escondido usado na própria previsão | o valor verdadeiro entra no ajuste | `visivel = 0` nos escondidos; os modelos só recebem `visivel = 1` |
| Imputação fácil demais | dia isolado escondido tem vizinhos observados dos dois lados | reportar também `hidden_block_len > 1` (ex.: 7 dias) para simular lacunas reais |
| Janelas atravessando splits (GPLVM) | uma janela mistura dias de treino e teste | montar janelas dentro de cada split |
| Dados provisórios no teste | os últimos anos costumam ser `Provisional`, com erros ainda não revisados nem rotulados | conferir `split_summary` e reportar o desempenho separando `Approved` e `Provisional` |
| Rótulos incompletos | há dias problemáticos sem código; cheias reais não têm código | tratar a precisão como limite inferior; inspecionar os maiores escores fora dos dias rotulados |
| Código `ESTIMATED` | o valor já foi corrigido pela USGS, a anomalia pode ter sido apagada | não entra em `anomalia`; analisar à parte se necessário |
| `ICE` sazonal | gelo se repete todo inverno e pode ser aprendido como normal | analisar o recall por código; estações frias concentram esse rótulo |
| Escolha de estações pelas anomalias | montar a `serie` (ou escolher a `seed`) para ter anomalias no teste; ou relatar só as estações em que o modelo foi bem | para a `serie`, aumentar `n_sensors` ou incluir estados sem olhar os rótulos; para o caso local, escolher a estação pelos rótulos **antes** de rodar o modelo e declarar o critério (veja [Avaliar a detecção numa estação](#avaliar-a-detecção-numa-estação-caso-local)) |
| `serie` montada de novo para cada modelo | os dias escondidos dependem do conjunto de estações; outra seleção muda a máscara | salvar a `serie` uma vez e todos lerem o mesmo arquivo (veja [Uma `serie` para todos os modelos](#uma-serie-para-todos-os-modelos)) |
| Cobertura só checada no treino | uma estação completa no treino pode estar quase vazia no teste | conferir a cobertura por bloco (veja [Cobertura fora do treino](#cobertura-fora-do-treino)) |
| Conformal em série temporal | o split conformal supõe dados trocáveis, o que não vale no tempo | calibração colada ao teste; citar o conformal adaptativo (ACI) como alternativa |
| Mudança ao longo dos anos | regulação, clima ou troca de equipamento alteram a série | comparar as métricas entre validação e teste; declarar como limitação |

## Dados de referência e semântica

Os dados atuais refletem a configuração padrão do projeto:

- parâmetro: `00060` (discharge)
- estatística: `00003` (média diária)
- janela temporal: `2010-01-01` a `2025-12-31`
- estados: California (1.002 séries), Montana (263) e Minnesota (139), 1.404 séries ao todo; 4 delas não têm dados no período
- unidade de vazão nos dados crus: ft³/s, com conversão local para m³/s em alguns fluxos analíticos (`df_full`)

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
- torch
- gpytorch
- optuna

## Validação e qualidade

Até o momento, o repositório não inclui uma suíte de testes automatizados formalizada com `pytest` ou outra ferramenta de CI. A validação do projeto é majoritariamente manual e baseada em:

- inspeção de arquivos Parquet/CSV;
- execução dos notebooks;
- checagem de integridade das colunas e tipos;
- visualização de séries temporais e resumos de cobertura.

## Observações finais

Este projeto é um ambiente de preparação e análise hidrológica local, com foco em dados de vazão e seleção de estações monitoradas pela USGS. O fluxo de preparação é compartilhado pelos modelos; o Bayesian GPLVM tem uma implementação de referência para previsão/reconstrução e detecção, ainda sujeita a validação e comparação com os outros modelos.

Para reproduzir o GPLVM, siga `01_download.ipynb` → `02_serie_modelos.ipynb` → `06_entradas_modelo3_gplvm.ipynb` → `modelo3_bayesian_gplvm.ipynb`, junto com os módulos em `src/`.

## Referências da USGS

- [API OGC Water Data](https://api.waterdata.usgs.gov/ogcapi/v1?f=html)
- [Coleções disponíveis](https://api.waterdata.usgs.gov/ogcapi/v1/collections?f=json)
- [Schema de monitoring-locations](https://api.waterdata.usgs.gov/ogcapi/v1/collections/monitoring-locations/schema?f=json)
- [Schema de time-series-metadata](https://api.waterdata.usgs.gov/ogcapi/v1/collections/time-series-metadata/schema?f=json)
- [Schema de daily](https://api.waterdata.usgs.gov/ogcapi/v1/collections/daily/schema?f=json)
- [Schema de continuous](https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/schema?f=json)
