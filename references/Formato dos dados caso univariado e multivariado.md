# Formato dos dados: caso univariado e multivariado

Oct 18, 2026 · @Alisson Ursulino

Exemplo com séries horárias de sazonalidade diária (período de 24). Os números são ilustrativos; se a frequência for outra, só muda o período.

## Caso univariado (uma série)

### Base comum: `serie.csv` (todos usam o mesmo arquivo)

| t | data\_hora | y\_bruto | y | observado | escondido\_aval | codigo | anomalia |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 2024-01-01 00:00 | 12.1 | −0.85 | 1 | 0 | A | 0 |
| 1 | 2024-01-01 01:00 | 11.4 | −1.02 | 1 | 0 | A | 0 |
| 2 | 2024-01-01 02:00 | NaN | NaN | 0 | 0 | A | 0 |
| 3 | 2024-01-01 03:00 | 10.9 | −1.14 | 1 | **1** | A | 0 |
| 4 | 2024-01-01 04:00 | 31.7 | 3.95 | 1 | 0 | A, Eqp | **1** |
| 5 | 2024-01-01 05:00 | 14.2 | −0.42 | 1 | 0 | P, Ice | **1** |
| … | … | … | … | … | … | … | … |

O que cada coluna significa:

- **y:** a série normalizada.
- **observado = 0:** é um faltante real.
- **escondido\_aval = 1:** o ponto foi observado, mas fica fora do treino. Ele serve para medir a reconstrução. Sorteie esses pontos só entre os que têm `anomalia = 0`.
- **codigo:** o código de qualidade original do dado, mantido como veio (ex.: `A` aprovado, `P` provisório, `e` estimado, `Eqp`, `Ice`, `Bkw`, `Mnt`, `Fld`). Serve para analisar o desempenho por tipo de problema.
- **anomalia:** binária, derivada de `codigo`. Vale 1 se o código contém `Eqp`, `Ice`, `Bkw`, `Mnt` ou `Fld`, e 0 caso contrário. Serve só para avaliar: nenhum modelo vê `codigo` nem `anomalia` no treino, e esses pontos não entram nas métricas de reconstrução.

A regra de treino vale para os três: só entram pontos com `observado = 1` e `escondido_aval = 0`. Isso vale para qualquer código: aprovado, provisório, estimado ou com problema. Todo o resto é tratado como faltante.

### Como cada pessoa lê o dado

**Pessoa 1 (GP Student‑t):** usa pares soltos (tempo, valor) e descarta os faltantes.

```
t_train : (N_obs,)   -> [0., 1., 4., 5., ...]
y_train : (N_obs,)   -> [-0.85, -1.02, 3.95, ...]
t_pred  : (T,)       -> todos os instantes, inclusive os faltantes
```

**Pessoa 2 (RGP‑t):** usa a sequência completa e ordenada, em grade regular, com os faltantes marcados.

```
y_seq  : (T,)     -> [-0.85, -1.02, 0.0, 0.0, 3.95, ...]   # NaN e escondidos -> 0
mask   : (T,)     -> [1, 1, 0, 0, 1, ...]
rnn_in : (T, 2)   -> colunas [y_seq, mask], entrada da GRU
```

**Pessoa 3 (GPLVM):** usa uma matriz com uma linha por dia (janela de 24 horas).

```
Y     : (n_dias, 24)   -> linha d = horas 0..23 do dia d (NaN onde falta)
mask  : (n_dias, 24)
t_idx : (n_dias, 24)   -> qual t corresponde a cada célula (para voltar à série)
```

Dias com mais de 50% faltando são descartados.

### Saída comum: `saida_modeloX.csv` (os três entregam igual)

| t | media | q025 | q975 | escore |
| --- | --- | --- | --- | --- |
| 2 | −1.10 | −1.62 | −0.58 | 0.21 |
| 3 | −1.15 | −1.66 | −0.63 | 0.18 |
| 4 | −0.98 | −1.50 | −0.45 | **4.70** |

Convenções para os três modelos ficarem comparáveis:

- **Escore maior = mais anômalo.** No caso das precisões, use 1/E\[τ\_i\] e não E\[τ\_i\], porque um E\[τ\_i\] pequeno indica outlier.
- **No modelo 3, o escore da janela é repetido nos 24 instantes dela.** A média e os quantis saem da reconstrução de cada célula.

O script de avaliação único lê `serie.csv` e qualquer `saida_modeloX.csv`, cruza tudo pela coluna `t` e calcula as métricas.

## Caso multivariado (vários sensores em zonas diferentes)

Os sensores são identificados por `sensor_id`. O arquivo fica no formato longo: uma linha por (sensor, instante), com os sensores empilhados.

### Base comum: `serie.csv` (todos usam o mesmo arquivo)

| sensor\_id | t | data\_hora | y\_bruto | y | observado | escondido\_aval | codigo | anomalia |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Z1 | 0 | 2024-01-01 00:00 | 12.1 | −0.85 | 1 | 0 | A | 0 |
| Z1 | 1 | 2024-01-01 01:00 | NaN | NaN | 0 | 0 | A | 0 |
| Z1 | 2 | 2024-01-01 02:00 | 31.7 | 3.95 | 1 | 0 | A, Eqp | **1** |
| … | … | … | … | … | … | … | … | … |
| Z2 | 0 | 2024-01-01 00:00 | 230.5 | 0.40 | 1 | 0 | A | 0 |
| Z2 | 1 | 2024-01-01 01:00 | 228.9 | 0.31 | 1 | **1** | A | 0 |
| Z2 | 2 | 2024-01-01 02:00 | 219.0 | −0.12 | 1 | 0 | P, Ice | **1** |
| … | … | … | … | … | … | … | … | … |

O que cada coluna significa:

- **sensor\_id:** identifica a zona. O `t` é o mesmo relógio para todos os sensores, então `t = 2` é o mesmo instante em Z1 e em Z2.
- **y:** a série normalizada **por sensor**, com a média e o desvio-padrão de cada um. Sem isso, um sensor de escala maior (Z2) dominaria os modelos compartilhados.
- **observado = 0:** é um faltante real. Cada sensor tem as suas falhas.
- **escondido\_aval = 1:** o ponto foi observado, mas fica fora do treino e serve para medir a reconstrução. Sorteie esses pontos **dentro de cada sensor**, na mesma proporção para todos, só entre os que têm `anomalia = 0`.
- **codigo:** o código de qualidade original de cada sensor, mantido como veio.
- **anomalia:** binária, derivada de `codigo` como no caso univariado. Serve só para avaliar.

A regra de treino continua valendo para os três: só entram pontos com `observado = 1` e `escondido_aval = 0`.

### Como cada pessoa lê o dado (S = número de sensores)

**Pessoa 1 (GP Student‑t):** usa pares (tempo, valor) e descarta os faltantes.

```
# opção simples: um GP por sensor (loop sobre sensor_id)
t_train[s] : (N_obs_s,)   -> instantes observados do sensor s
y_train[s] : (N_obs_s,)
t_pred[s]  : (T,)         -> todos os instantes do sensor s
```

**Pessoa 2 (RGP‑t):** usa as sequências completas e ordenadas, com um sensor por linha do lote.

```
y_seq  : (S, T)      -> NaN e escondidos -> 0
mask   : (S, T)
rnn_in : (S, T, 2)   -> [y_seq, mask] por sensor, entrada da GRU
```

**Pessoa 3 (GPLVM):** usa as janelas diárias de todos os sensores, empilhadas.

```
Y         : (n_janelas_total, 24)   -> linha = 1 dia de 1 sensor (NaN onde falta)
mask      : (n_janelas_total, 24)
sensor_id : (n_janelas_total,)      -> de qual zona é a janela
t_idx     : (n_janelas_total, 24)   -> qual t corresponde a cada célula
```

Janelas com mais de 50% faltando são descartadas.

### O que muda em cada modelo

| Modelo | Com um sensor | Com vários sensores | Opção mais rica (se as zonas forem correlacionadas) |
| --- | --- | --- | --- |
| 1. GP Student‑t | Um GP | **Um GP independente por sensor.** O código é o mesmo, dentro de um loop. | **GP multitarefa:** a entrada vira (t, sensor) e o kernel vira `K_tempo × IndexKernel(sensor)`, que aprende a correlação entre zonas. Funciona no formato longo e lida com faltantes diferentes por sensor. |
| 2. RGP‑t | Uma sequência | **Um modelo compartilhado.** Os S sensores entram como lote, e as camadas GP aprendem uma dinâmica comum. | Somar um *embedding* do sensor (`nn.Embedding`) à entrada da GRU, para o modelo distinguir as zonas sem perder o compartilhamento. |
| 3. GPLVM | Janelas de uma série | **Um modelo compartilhado.** As janelas de todas as zonas ficam no mesmo espaço latente, onde zonas com comportamento parecido tendem a se agrupar. | Usar o `sensor_id` só para análise: colorir o espaço latente por zona e ver se uma anomalia aparece numa zona ou em várias ao mesmo tempo. |

Se as zonas forem vizinhas, uma anomalia pode ser **regional**, afetando vários sensores ao mesmo tempo, ou **local**, afetando um só. Os modelos compartilhados e o GP multitarefa ajudam a separar os dois casos. Vale citar isso no trabalho mesmo que fiquem na opção simples.

### Saída comum: `saida_modeloX.csv` (os três entregam igual)

| sensor\_id | t | media | q025 | q975 | escore |
| --- | --- | --- | --- | --- | --- |
| Z1 | 1 | −1.10 | −1.62 | −0.58 | 0.21 |
| Z1 | 2 | −0.98 | −1.50 | −0.45 | **4.70** |
| Z2 | 1 | 0.35 | −0.10 | 0.80 | 0.15 |

Convenções:

- **Escore maior = mais anômalo.** Nas precisões, use 1/E\[τ\_i\].
- **No modelo 3, o escore da janela é repetido nos 24 instantes dela,** no sensor dela.
- **As saídas ficam na escala normalizada.** Para relatar em unidades reais, desfaça a normalização de cada sensor.

O script de avaliação único cruza `serie.csv` e `saida_modeloX.csv` pela chave **(sensor\_id, t)**. Ele calcula as métricas **por sensor** e depois a média e o desvio entre sensores, para que nenhuma zona domine o resultado.

## Rótulos de anomalia a partir dos códigos de qualidade

O dataset não tem rótulos de anomalia, mas cada valor de vazão vem com um código de qualidade. A coluna `anomalia` é derivada dele, sem injetar nada. Os três modelos continuam não supervisionados: a coluna só é usada para avaliar.

| Código | Significado | anomalia |
| --- | --- | --- |
| `Eqp` | afetado por falha de equipamento | 1 |
| `Ice` | afetado por gelo | 1 |
| `Bkw` | afetado por remanso (backwater) | 1 |
| `Mnt` | estação em manutenção | 1 |
| `Fld` | afetado por inundação | 1 |
| `A` / `P` | aprovado / provisório | 0 |
| `e` | editado ou estimado pela equipe do USGS | 0 (analisar à parte) |

```python
problemas = "Eqp|Ice|Bkw|Mnt|Fld"
df["anomalia"] = df["codigo"].str.contains(problemas, na=False).astype(int)
```

### O que entra no treino

Entra todo valor que existe, aprovado ou não, inclusive os dias com código de problema. Ficam de fora só os faltantes e os pontos escondidos para avaliação.

| Tipo de dia | Entra no treino? | Por quê |
| --- | --- | --- |
| `A` (aprovado) | Sim | É o dado normal |
| `P` (provisório) | Sim | É um valor real, só não revisado; costuma ser o trecho mais recente da série |
| `e` (estimado) | Sim | O valor existe; na avaliação, analisar esses dias à parte |
| Com código de problema (`Eqp`, `Ice`, `Bkw`, `Mnt`, `Fld`) | **Sim** | São as anomalias que os modelos devem achar; a Student‑t evita que distorçam o ajuste |
| Sem valor (`NaN`) | Não | É faltante (`observado = 0`) |
| Escondido para avaliação | Não | Fica fora para medir a reconstrução |

Os modelos nunca recebem `codigo` nem `anomalia`. Treinar só com dias `anomalia = 0` seria detecção de novidade: usaria os rótulos no treino e deixaria de ser não supervisionado, então não é a abordagem adotada.

### Como avaliar

- **AUC:** separação dos escores entre `anomalia = 1` e `anomalia = 0`.
- **Recall no top 1%:** fração dos dias com `anomalia = 1` que ficam entre os 1% maiores escores.
- **Por tipo de problema:** as mesmas métricas filtrando `codigo` (Eqp, Ice etc.), para ver o que cada modelo enxerga.
- **Otimização Bayesiana:** o objetivo continua sendo o NLPD nos pontos escondidos, sem usar `anomalia`.

### Limitações a declarar

- **Gabarito incompleto:** pode haver dias problemáticos sem código. Eles contam como normais, então a precisão sai subestimada.
- **Sem valor verdadeiro nos dias marcados:** a vazão real nesses dias é desconhecida. Por isso eles ficam fora das métricas de reconstrução.
- **Código `e`:** o valor já foi estimado e corrigido, então a anomalia pode ter sido apagada.
- **Cheias reais:** picos de cheia são eventos verdadeiros, sem código. Escores altos nesses dias não são erro do modelo; vale inspecioná-los e comentar no relatório.
- **GPLVM robusto:** usar a mesma `student_t_elbo_terms` dos modelos 1 e 2 na verossimilhança do GPLVM, para que os dias problemáticos não contaminem o ajuste.

Fontes: [USGS, status codes](https://help.waterdata.usgs.gov/codes-and-parameters/instantaneous-and-daily-value-status-codes) e [USGS, daily value qualification codes](https://help.waterdata.usgs.gov/codes-and-parameters/daily-value-qualification-code-dv_rmk_cd).
