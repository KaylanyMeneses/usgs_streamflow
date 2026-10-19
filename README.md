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

- tabela de modelagem compartilhada (`src/model_data.py`) para o trabalho de modelos probabilísticos: rótulos de anomalia a partir dos códigos de qualidade da USGS, splits cronológicos, pontos escondidos para avaliação e normalização sem vazamento.

Os modelos (GP Student‑t, RGP‑t e Bayesian GPLVM) ainda não estão implementados; eles consomem a tabela descrita em [Tabela de modelagem](#tabela-de-modelagem).

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
│   │   └── serie.parquet          (gerado por build_model_dataset)
│   └── usgs/
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
│   ├── construcao_bases_modelos.ipynb   (novo)
│   └── usgs_streamflow.ipynb
├── references/
│   ├── Formato dos dados caso univariado e multivariado.md
│   └── Relatório técnico GPs para séries com faltantes e anomalias.md
├── reports/
│   └── figures/
├── src/
│   ├── __init__.py
│   ├── api.py
│   ├── catalog.py
│   ├── config.py
│   ├── main.py
│   ├── evaluation.py              (novo)
│   ├── model_data.py              (novo)
│   ├── model_inputs.py            (novo)
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
- `notebooks/análise_seleção.ipynb`: notebook de análise local com base nos arquivos já presentes em `data/`, sem depender de nova chamada à API;
- `notebooks/construcao_bases_modelos.ipynb`: mostra como montar a tabela compartilhada, a entrada de cada modelo por bloco (`X_train`, `Y_train`, `X_val`…), o formato da saída e o cálculo das métricas, a partir dos Parquets locais.

### Referências

A pasta `references/` guarda os documentos de planejamento do trabalho de modelagem. Eles não são lidos pelo código: servem como especificação de onde vieram as decisões implementadas em `src/model_data.py`, `src/model_inputs.py` e `src/evaluation.py`, e como guia comum para quem implementa cada modelo.

- `Relatório técnico GPs para séries com faltantes e anomalias.md`: descreve o problema (faltantes, sazonalidade, picos anômalos e dependência temporal), os três modelos (GP Student‑t, RGP‑t e Bayesian GPLVM), a divisão do trabalho por pessoa, a implementação prevista com GPyTorch/BoTorch e as ressalvas a declarar;
- `Formato dos dados caso univariado e multivariado.md`: define o formato da base comum e da saída dos modelos nos casos univariado e multivariado, como cada modelo lê os dados, os rótulos de anomalia a partir dos códigos de qualidade e o que entra no treino e na avaliação.

Os exemplos desses documentos são ilustrativos (por exemplo, séries horárias com `serie.csv`); quando houver diferença, vale o que está descrito neste README e no código (dados diários, `serie.parquet`).

### Módulos Python

- `src/config.py`: define as rotas do projeto e as configurações padrão da API, além de ler variáveis do arquivo `.env` no diretório raiz;
- `src/api.py`: cliente opcional para a API OGC da USGS, com paginação e tratamento de erros temporários;
- `src/catalog.py`: carrega, valida e indexa CSV e Parquet, além de ler os caches diários (incluindo `approval_status` e `qualifier`, quando presentes);
- `src/processing.py`: transforma observações em tabela analítica por estação, calcula sumários de cobertura e completa o calendário diário sem imputar valores;
- `src/model_data.py`: monta a tabela de modelagem (rótulos, splits, seleção de estações, pontos escondidos e normalização);
- `src/model_inputs.py`: converte a tabela na entrada de cada modelo (`gp_inputs`, `rgp_inputs`, `gplvm_inputs`), sem NaN;
- `src/evaluation.py`: confere o formato da saída dos modelos e calcula as métricas de reconstrução, conformal e detecção de anomalias;
- `src/plots.py`: gera gráficos de série temporal por estação;
- `src/main.py`: orquestra a criação da tabela analítica, do resumo por estação e da tabela de modelagem (`build_model_dataset`).

## Fluxo atual do projeto

A pipeline atual combina dados do USGS com dados locais já coletados. O fluxo típico é:

1. consultar metadados da API e definir a seleção de séries;
2. armazenar arquivos em Parquet em `data/usgs/raw/`;
3. validar e carregar vetores de estações em `data/usgs/processed/`;
4. montar uma tabela de observações por data e estação;
5. resumir registros, vazões ausentes e vazões zero;
6. produzir gráficos de série temporal.
7. montar a tabela de modelagem (`build_model_dataset`) para os modelos probabilísticos.

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

### 3. Gerar a tabela de modelagem

```python
from src.main import build_model_dataset, export_dataset, SelectionConfig, SplitConfig
from src.model_data import split_summary

serie, stats = build_model_dataset(
    SelectionConfig(n_sensors=10, min_completeness=0.95, max_zero_frac=0.05),
    SplitConfig(fracs=(0.60, 0.15, 0.10, 0.15), hidden_frac=0.10, hidden_block_len=1),
)
print(split_summary(serie))            # conferir períodos, escondidos, anomalias e provisórios
export_dataset(serie, "serie.parquet") # data/exports/, sem sobrescrever
# stats (média e desvio por estação) desfaz a normalização: y_bruto = expm1(y * std + mean)
```

Para o caso univariado, use `SelectionConfig(n_sensors=1)`. Para restringir a estações vizinhas, passe `candidates=(...)` com IDs tirados, por exemplo, de `pares_nldi_*_150km.csv`.

### 4. Visualizar uma estação

```python
from src.catalog import load_station_selection
from src.main import build_observation_table
from src.plots import plot_station_series

stations = load_station_selection()
observations = build_observation_table()
fig, ax = plot_station_series(observations, stations["monitoring_location_id"].iloc[0])
```

## Tabela de modelagem

`build_model_dataset` devolve uma tabela no formato longo: uma linha por (estação, dia), com o calendário completo de `USGS_DATE_START` a `USGS_DATE_END`. Exemplo ilustrativo da saída:

| sensor_id | t | data | split | y_bruto | y | observado | escondido_aval | visivel | aprovacao | qualificador | anomalia |
|---|---|---|---|---|---|---|---|---|---|---|---|
| USGS-11532500 | 0 | 2010-01-01 | treino | 812.0 | 0.41 | 1 | 0 | 1 | Approved | | 0 |
| USGS-11532500 | 1 | 2010-01-02 | treino | NaN | NaN | 0 | 0 | 0 | | | 0 |
| USGS-11532500 | 19 | 2010-01-20 | treino | 2350.0 | 1.37 | 1 | 0 | 1 | Approved | Ice | 1 |
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
| `qualificador` | qualificador original da USGS (ex.: `Ice`, `Equipment`); vazio quando não há; vários são separados por `;` |
| `anomalia` | 1 se `qualificador` indica problema (Eqp, Ice, Bkw, Mnt, Fld); só para avaliação |

### Uso de cada split

| Split | Padrão | Uso |
|---|---|---|
| `treino` | 60% (2010 → 2018) | ajustar os modelos (ELBO) e as estatísticas de normalização |
| `validacao` | 15% | objetivo da otimização Bayesiana: NLPD nos pontos escondidos |
| `calibracao` | 10% | conformal prediction: quantil dos resíduos normalizados nos pontos escondidos |
| `teste` | 15% (até 2024) | métricas finais, usado uma única vez |

Regras para os modelos:

- os modelos recebem apenas valores com `visivel = 1`; `aprovacao`, `qualificador` e `anomalia` nunca entram no treino;
- dias com código de problema entram no treino normalmente: são as anomalias que os modelos devem detectar;
- parâmetros (ELBO) usam só `treino`; hiperparâmetros externos (janela, dimensão latente, pontos de indução, ν) usam só `validacao`; o conformal usa só `calibracao`.

### O que entra no treino

- Filtro único para todos: `split == "treino"` e `visivel == 1`.
- Isso inclui todos os dias de treino com valor, **inclusive os com código de problema** (Eqp, Ice etc.).
- Ficam de fora só os dias sem valor (NaN). No bloco de treino nada é escondido; a máscara (`escondido_aval`) só existe em `validacao`, `calibracao` e `teste`, com semente fixa (os mesmos dias em toda execução). Para desligá-la: `SplitConfig(hidden_frac=0)`.
- Nenhum NaN entra nos cálculos dos modelos (o GPyTorch não aceita NaN).

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
- `escore`: quanto maior, mais anômalo. Modelos 1 e 2: 1/E[τ] (nos dias de validação e teste, a mesma fórmula aplicada à previsão do modelo). Modelo 3: −ELBO da janela, repetido em cada dia dela. É NaN nos dias sem valor visível.
- `alerta`: 1 se o escore passa de um limiar definido na `calibracao` (ex.: percentil 99, ou via conformal), nunca no teste.

### Duas avaliações separadas

| Avaliação | Pergunta | Colunas | Métricas |
|---|---|---|---|
| Reconstrução | o modelo acerta o valor quando o dado falta? | `escondido_aval` (só dias normais) e `y_bruto` | RMSE, NLPD, cobertura do intervalo de 95% |
| Detecção | o modelo aponta os dias com problema? | `escore`/`alerta` contra `anomalia` | AUC, recall e precisão, só no `teste` |

A máscara não ajuda nem atrapalha a detecção: os dias escondidos são sorteados só entre dias sem código de problema.

**Dados provisórios:** os anos mais recentes (bloco de teste) ainda não foram revisados pela USGS e podem ter erros sem rótulo. Mostrem as métricas finais separando dados `Approved` e `Provisional`.

## Condições e restrições dos dados

| Condição | Padrão | Onde configurar |
|---|---|---|
| Vazão média diária (`00060` / `00003`) | fixo | `.env` / `src/config.py` |
| Período | 2010-01-01 a 2024-12-31 | `USGS_DATE_START`, `USGS_DATE_END` |
| Uma série por estação | obrigatório (validado no catálogo) | `src/catalog.py` |
| Completude mínima no treino | ≥ 95% dos dias com valor | `SelectionConfig.min_completeness` |
| Fração de zeros no treino (exclui rios intermitentes) | ≤ 5% | `SelectionConfig.max_zero_frac` |
| Vazão negativa | estação descartada | fixo |
| Número de estações | 10 (1 = univariado) | `SelectionConfig.n_sensors` |
| Restringir a um conjunto de estações (ex.: vizinhas) | desligado | `SelectionConfig.candidates` |
| Proporção dos splits | 60 / 15 / 10 / 15 | `SplitConfig.fracs` |
| Pontos escondidos por bloco fora do treino | 10% | `SplitConfig.hidden_frac` |
| Tamanho das lacunas escondidas | 1 dia (isolado) | `SplitConfig.hidden_block_len` |
| Transformação | `log1p` + padronização por estação | `SplitConfig.log_transform` |
| Códigos que viram `anomalia = 1` | Eqp, Ice, Bkw, Mnt, Fld | `PROBLEM_QUALIFIERS` em `src/model_data.py` |

Antes de usar, confira os textos reais de `qualifier` (`df["qualifier"].value_counts()`) e ajuste `PROBLEM_QUALIFIERS`: a API OGC pode trazer os códigos por extenso (por exemplo, `Ice`).

## Pontos de atenção: vazamento de dados e viés

| Risco | Por que acontece | Como o código evita / o que fazer |
|---|---|---|
| Split aleatório entre dias | dias vizinhos são quase iguais; o teste "vê" o treino | splits em blocos cronológicos, com as mesmas datas de corte para todas as estações |
| Normalização com dados futuros | média e desvio calculados com validação ou teste | estatísticas só de `treino` com `visivel = 1` |
| Seleção de estações olhando o futuro | completude ou zeros calculados no período inteiro | filtros calculados só no bloco `treino` |
| Rótulos no treino | `anomalia`, `aprovacao` ou `qualificador` usados como entrada ou para escolher estações | nenhuma função de treino ou seleção usa essas colunas; não filtrar estações por número de anomalias |
| Otimização tocando o teste | hiperparâmetros ou limiares escolhidos olhando o teste | otimização Bayesiana só em `validacao`, conformal só em `calibracao`, teste usado uma vez |
| Ponto escondido usado na própria previsão | o valor verdadeiro entra no ajuste | `visivel = 0` nos escondidos; os modelos só recebem `visivel = 1` |
| Imputação fácil demais | dia isolado escondido tem vizinhos observados dos dois lados | reportar também `hidden_block_len > 1` (ex.: 7 dias) para simular lacunas reais |
| Janelas atravessando splits (GPLVM) | uma janela mistura dias de treino e teste | montar janelas dentro de cada split |
| Dados provisórios no teste | os últimos anos costumam ser `Provisional`, com erros ainda não revisados nem rotulados | conferir `split_summary` e reportar o desempenho separando `Approved` e `Provisional` |
| Rótulos incompletos | há dias problemáticos sem código; cheias reais não têm código | tratar a precisão como limite inferior; inspecionar os maiores escores fora dos dias rotulados |
| Código `e` (estimado) | o valor já foi corrigido pela USGS, a anomalia pode ter sido apagada | não entra em `anomalia`; analisar à parte se necessário |
| `Ice` sazonal | gelo se repete todo inverno e pode ser aprendido como normal | analisar o recall por código; estações frias concentram esse rótulo |
| Conformal em série temporal | o split conformal supõe dados trocáveis, o que não vale no tempo | calibração colada ao teste; citar o conformal adaptativo (ACI) como alternativa |
| Mudança ao longo dos anos | regulação, clima ou troca de equipamento alteram a série | comparar as métricas entre validação e teste; declarar como limitação |

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
