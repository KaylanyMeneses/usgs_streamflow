A causa não é falta de anomalias recentes: na rede toda há 1.606 dias rotulados no período de teste. O problema é que **poucas estações elegíveis têm anomalias no teste**. Das 396 estações da Califórnia que passam nos filtros (completude ≥ 95% e zeros ≤ 5% no treino), só **23** têm algum dia rotulado no teste, somando 590 dias. Sorteando 10 entre 396, o mais provável é não pegar nenhuma delas. Testei cada opção com os seus dados, sem alterar nada.

### 1. Aumentar `n_sensors`

```python
SELECAO = SelectionConfig(n_sensors=50, min_completeness=0.95, max_zero_frac=0.05, seed=42)
```

| `n_sensors`              | anomalias no teste | estações com anomalia no teste |
| ------------------------ | ------------------ | ------------------------------ |
| 10                       | 0                  | 0                              |
| 20                       | 18                 | 1                              |
| 50                       | 30                 | 2                              |
| 396 (todas as elegíveis) | **590**            | 23                             |

Com 396 estações, também há anomalias na validação (311) e na calibração (285), e a seção 6 passa a funcionar de verdade. O custo é que a `serie` fica com 2,3 milhões de linhas. Para o GP Student‑t, que roda uma estação por vez, isso não pesa. Para o RGP‑t e o GPLVM, que recebem todas as estações juntas, pesa bastante.

### 2. Escolher as estações por `candidates=(...)`

```python
SELECAO = SelectionConfig(n_sensors=10, candidates=("USGS-...", "USGS-..."), seed=42)
```

⚠️ **Escolher pelas anomalias do teste é vazamento.** O README diz "não filtrar estações por número de anomalias", porque assim a avaliação passa a depender dos rótulos do teste. Escolher só pelas anomalias do **treino** também usa rótulos na seleção e, além disso, rendeu pouco: entre as 44 estações com anomalia no treino, o sorteio de 10 deu 33 dias de anomalia no teste, todos numa só estação.

Esta opção é adequada quando a escolha vem de um critério externo, como as estações vizinhas de `pares_nldi_*_150km.csv`, que é para o que `candidates` foi feito.

### 3. Aumentar o bloco de teste

```python
SPLITS = SplitConfig(fracs=(0.50, 0.15, 0.10, 0.25), hidden_frac=0.10, hidden_block_len=1, seed=42)
```

Não resolve de forma confiável. Mudar as frações muda o período de treino, e com ele as estações que passam nos filtros, então o sorteio muda por completo. Com `(0.50, 0.15, 0.10, 0.25)` saíram 12 dias no teste. Com `(0.40, 0.15, 0.15, 0.30)`, saiu 0 de novo.

### Também não recomendado: trocar a `seed` até aparecer anomalia

Algumas seeds dão de 4 a 18 dias no teste. Mas escolher a seed olhando para o teste é o mesmo vazamento da opção 2.

### Afrouxar os filtros ajuda pouco

Mesmo com `min_completeness=0.80` e `max_zero_frac=0.20`, ficam 536 elegíveis e 30 estações com anomalia no teste (860 dias). Ou seja: a escassez está nos rótulos, não nos filtros.

### Minha recomendação

- **Detecção:** use a **opção 1 com todas as elegíveis** (`n_sensors=396`), ou pelo menos 100 a 200 estações. É a única que gera anomalias suficientes no teste sem olhar para os rótulos.
- **RGP‑t e GPLVM:** se 396 estações pesar demais, treine com um subconjunto e calcule as métricas de detecção sobre todas as estações em que o modelo puder ser aplicado.
- **Outra alternativa:** baixar um estado frio em vez da Califórnia, usando `states=(...)` com `use_top_state=False` no `DownloadConfig`. A Califórnia quase não tem rótulo `ICE`, que costuma ser o qualificador de problema mais comum nos estados frios. Isso exige um download novo.

---

São dois lugares: **os estados ficam no download**, e **os filtros de estação ficam na construção da base**.

### 1. Estados: `01_download.ipynb`, Célula 2 (`DownloadConfig`)

```python
cfg = DownloadConfig(
    date_start="2010-01-01",
    date_end="2025-12-31",
    states=("California", "Minnesota", "Montana"),  # nomes por extenso, como em state_name
    use_top_state=False,                             # obrigatório: com True, só fica o estado com mais estações
    require_full_coverage=False,
    all_columns=True,
    max_sites=None,                                  # None = todas as estações desses estados
    seed=42,
    batch_size=8,
)
selected, summary = run_pipeline(cfg)
```

- **`use_top_state=False` é essencial.** Com `True`, o código continua reduzindo a seleção ao estado com mais estações, mesmo com `states` preenchido ([src/download.py](src/download.py), `select_series`).
- **Nomes dos estados:** use os nomes por extenso que aparecem na tabela de estados por número de estações, aquela que você salvou em `data/usgs/raw/states_daily_discharge_counts.parquet`.
- **O que é reaproveitado:** as séries da Califórnia que já estão em disco não são baixadas de novo. Só as dos estados novos são baixadas.
- **Lista de seleção:** o arquivo `daily_..._selected.csv` é substituído pela lista nova, com todos os estados. O `03_guia_bases_modelos.ipynb` lê esse arquivo e passa a enxergar os novos estados automaticamente.
- **Tempo de download:** cada estado grande tem perto de 1.000 estações, ou cerca de 125 lotes.
- **`require_full_coverage`:** é um filtro de cobertura aplicado já no download. Com `True`, só entram as séries cujo registro cobre 2010–2025 inteiro.

### 2. Filtros de estação: `03_guia_bases_modelos.ipynb`, Célula 5 (seção 3.1)

```python
SELECAO = SelectionConfig(
    n_sensors=200,           # quantas estações entram na serie
    min_completeness=0.95,   # fração mínima de dias com valor no treino
    max_zero_frac=0.05,      # fração máxima de vazão zero no treino (exclui rios intermitentes)
    candidates=None,         # ou uma tupla de IDs para restringir a escolha
    seed=42,
)
```

Esses filtros são calculados só no bloco de treino. Eles são definidos em `SelectionConfig`, em [src/model_data.py](src/model_data.py), mas você só precisa mudar os valores aqui, na célula.

Se `n_sensors` passar do número de estações que atendem aos filtros, aparece o erro `Só N estações passam nos filtros; pedido: M`. Esse N é o máximo que você pode pedir.

**Ordem para rodar:** primeiro o `01_download.ipynb` com os estados novos, até `summary["pending"]` zerar. Depois o `03_guia_bases_modelos.ipynb` desde o início, com o kernel reiniciado.

---

Não. `states=None` só significa "não restringir o catálogo por estado". Quem limitou o download à Califórnia foi o `use_top_state=True`, que atua em dois momentos ([src/download.py](src/download.py)):

1. **Locais do tipo Stream (`stream_series`):** com `use_top_state=True` e `states=None`, o código consulta só os 3 estados com mais estações. Por isso o log mostrou Califórnia, Texas e Flórida.
2. **Seleção (`select_series`):** desses três, mantém só o estado com mais estações. Daí a linha `Estado escolhido: California (1002 estações)`.

Esse comportamento veio do notebook original, que tinha `USE_TOP_STATE = True` e a mesma lógica.

Para baixar a rede inteira:

```python
cfg = DownloadConfig(
    date_start="2010-01-01", date_end="2025-12-31",
    states=None,           # sem filtro de estado
    use_top_state=False,   # não reduz ao estado com mais estações
    max_sites=None,        # todas as estações
    ...
)
```

Antes, considere o tamanho, calculado a partir do catálogo que já está em disco:

- **Estados:** o catálogo tem 66 estados e territórios.
- **Estações:** cerca de 11.300 têm série que toca o período 2010–2025. O filtro de locais Stream reduz esse número, mas devem sobrar alguns milhares.
- **Requisições:** antes de baixar as séries, o código faz uma consulta de locais Stream por estado, ou seja, 66 consultas.
- **Download:** com `batch_size=8`, são mais de mil lotes. A Califórnia, com 125 lotes, já levou um tempo considerável. A rede inteira deve levar horas.

Como agora cada série é salva individualmente, você pode interromper e retomar quando quiser, e as 1.002 séries da Califórnia já baixadas são reaproveitadas.

Se o objetivo for ter anomalias suficientes no teste, um meio-termo é escolher alguns estados frios, onde o rótulo `ICE` é comum, com `states=(...)` e `use_top_state=False`, como mostrei na resposta anterior.

---

O gráfico está certo. Ele mostra uma única estação, `sid = serie["sensor_id"].iloc[0]`, que é a primeira da lista (`USGS-04010500`). Essa estação **não tem nenhum dia rotulado como anomalia depois de 2019**:

| Split      | Anomalias em USGS-04010500 |
| ---------- | -------------------------- |
| treino     | 374                        |
| validacao  | 0                          |
| calibracao | 0                          |
| teste      | 0                          |

Da validação em diante, os únicos qualificadores dela são vazio (1.358 dias) e `ESTIMATED` (980 dias). `ESTIMATED` não conta como anomalia.

As 552 anomalias do teste estão em outras estações: só **33 das 200** têm alguma anomalia no teste. As que têm mais são:

| Estação       | Dias de anomalia no teste |
| ------------- | ------------------------- |
| USGS-11224000 | 125                       |
| USGS-05330000 | 90                        |
| USGS-10336660 | 88                        |
| USGS-11370500 | 72                        |

Para ver no gráfico uma estação com anomalias no teste, troque a primeira linha da célula do gráfico:

```python
# estação com mais anomalias rotuladas no teste
sid = (serie[(serie["split"] == "teste") & (serie["anomalia"] == 1)]
       .groupby("sensor_id").size().idxmax())
```

Ou escreva o ID direto: `sid = "USGS-11224000"`.

Use isso só para visualizar. Escolher estações pelas anomalias do teste para montar a `serie` seria vazamento, mas para olhar o gráfico não tem problema.

Vale reparar num detalhe do seu gráfico. Entre 2016 e 2018, os invernos dessa estação foram rotulados (provavelmente `ICE`). Nos invernos depois de 2019, o padrão da série parece parecido, mas os dias só receberam `ESTIMATED`. Isso é o que o README chama de "rótulos incompletos": a USGS nem sempre marca o problema da mesma forma. Na prática, alguns alertas do modelo nesses invernos vão contar como falso positivo mesmo podendo ser problemas reais, e por isso a precisão deve ser lida como limite inferior.
