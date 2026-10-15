# USGS Streamflow

Projeto de preparação e análise de séries temporais hidrológicas da USGS. O notebook atual consulta séries de vazão média diária, combina observações com metadados das estações e cria uma grade diária completa para explicitar os dias sem valor como `NaN`. A análise exploratória inclui cobertura, vazões zero e lacunas; o conjunto está sendo preparado para estudos futuros de reconstrução de séries e modelos generativos ou PINNs.

## Escopo atual

- **Fonte:** USGS Water Data APIs, interface OGC API.
- **API configurada no notebook:** `v0`esse v0 é pq  a api vai ser atualizada daqui a alguns anos, dexo claro que é v0 pois eu estou usando a api atual; o notebook consulta os esquemas para conferir os campos disponíveis.
- **Período:** 2010-01-01 a 2024-12-31.
- **Variável-alvo:** vazão (`parameter_code = "00060"`).
- **Série atual:** estatística diária média (`statistic_id = "00003"`).
- **Seleção espacial:** controlada por `STATES`, `USE_TOP_STATE` e `REQUIRE_FULL_COVERAGE` no notebook. O resultado observado numa execução anterior era da Califórnia; reexecute o notebook para atualizar resultados e saídas.
- **Resolução:** diária. A API também oferece dados contínuos/de alta frequência em estações e parâmetros específicos, mas a cobertura e o intervalo real precisam ser verificados antes de migrar o estudo para 15 minutos(claude, diga a ele que pode deixar q eu tô trabalhando nisso no outro notebook, para a gente verificar de qual modo relmente seria melhor para a modelagem:diário ou intradiário - aviso da kaylany).

O objetivo experimental recomendado é reconstruir lacunas de vazão condicionando o modelo às observações restantes e, quando disponíveis, às forçantes hidrometeorológicas, avaliando se restrições físicas melhoram o resultado. Para medir desempenho, o notebook/modelo deve ocultar trechos conhecidos durante a validação e comparar as reconstruções com as observações originais.

## API e metadados

As APIs organizam dados em **coleções**. O notebook usa principalmente:

| Coleção | O que representa | Uso no projeto |
|---|---|---|
| `monitoring-locations` | Local físico monitorado: identificador, nome, coordenadas, estado, condado e atributos do local. | Metadados espaciais e seleção de locais do tipo `Stream` (`site_type_code = "ST"`). |
| `time-series-metadata` | Série específica associada a um local, parâmetro, estatística/período de computação e período de registro. Um local pode ter várias séries. | Catálogo, escolha de uma série por estação e metadados de período. |
| `daily` | Observações diárias de uma série, com horário/data, valor, unidade, estado de aprovação e qualificador. | Fonte de vazão diária usada no `df_full`. |
| `continuous` | Observações de sensores de alta frequência, frequentemente — mas não sempre — em intervalos de 15 minutos. | Possível estudo-piloto futuro de vazão, nível ou precipitação, após conferir cobertura e frequência reais. |

Identificadores importantes:

- **`monitoring_location_id`** identifica o local físico; exemplo: `USGS-09423350`.
- **`time_series_id`** identifica a série temporal específica e conecta metadados às observações. Use-o como chave de junção da série.
- **`parameter_code`** indica a grandeza medida. Neste notebook, `00060` é vazão. `00065` é nível e `00045` é precipitação; a disponibilidade varia por local e período.
- **`statistic_id`** indica a estatística da série. Neste notebook, `00003` é média. Não confunda estatística diária média com uma medição instantânea.
- **`begin_utc` / `end_utc`** indicam o primeiro e o último horário registrados, não a continuidade do registro; a própria documentação alerta que podem existir lacunas entre eles.
- **HUC** (`hydrologic_unit_code`) identifica uma unidade hidrológica. Não é, por si só, a área de drenagem.
- **Coordenadas, área de drenagem e altitude** descrevem o local. Verifique unidade, datum e definição no metadado original antes de converter ou usar em equações.

### Documentação oficial

- [Portal OGC API da USGS Water Data](https://api.waterdata.usgs.gov/ogcapi/v1?f=html)
- [Coleções disponíveis](https://api.waterdata.usgs.gov/ogcapi/v1/collections?f=json)
- [Esquema de `monitoring-locations`](https://api.waterdata.usgs.gov/ogcapi/v1/collections/monitoring-locations/schema?f=json)
- [Esquema de `time-series-metadata`](https://api.waterdata.usgs.gov/ogcapi/v1/collections/time-series-metadata/schema?f=json)
- [Esquema de `daily`](https://api.waterdata.usgs.gov/ogcapi/v1/collections/daily/schema?f=json)
- [Esquema de `continuous`](https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/schema?f=json)
- [Códigos de parâmetros](https://api.waterdata.usgs.gov/ogcapi/v1/collections/parameter-codes/items?f=html)
- [Códigos de estatísticas](https://api.waterdata.usgs.gov/ogcapi/v1/collections/statistic-codes/items?f=html)

Os esquemas das coleções são a referência para nomes, tipos e descrições dos campos. Eles podem mudar entre versões da API; por isso, confira o esquema da versão configurada antes de depender de uma coluna. Respostas paginadas podem conter um link `rel=next`; o notebook percorre essas páginas. `properties` pode restringir as colunas retornadas, enquanto `skipGeometry=true` evita baixar a geometria quando ela não é necessária.

## Dicionário de dados de `df_full`

`df_full` é a tabela analítica diária. A grade é formada por cada `time_series_id` selecionado × cada data do período e então recebe as observações e os metadados. Portanto, dias sem observação permanecem visíveis; nenhum valor é imputado nesta etapa.

| Coluna | Significado |
|---|---|
| `date` | Data diária da grade. A interpretação da data deve ser consistente com o horário/fuso definido pela API para a série. |
| `monitoring_location_id` | Identificador USGS do local físico. |
| `time_series_id` | Identificador único da série da USGS; chave para localizar a observação e seus metadados de série. |
| `monitoring_location_name` | Nome descritivo do local. |
| `state_name`, `county_name` | Estado/território e condado informados para o local. |
| `lat`, `lon` | Latitude e longitude do ponto do local, quando disponíveis. |
| `drainage_area` | Área de drenagem informada no metadado. Confirmar a unidade antes de convertê-la para balanço hídrico. |
| `altitude` | Altitude informada no metadado; verificar datum/unidade se for usada quantitativamente. |
| `site_huc` | Código da unidade hidrológica do local (HUC). |
| `value_cfs` | Valor diário de vazão na unidade original da série; no recorte `00060`, ft³/s. |
| `value_m3s` | Vazão convertida de ft³/s para m³/s. `NaN` permanece `NaN`. |
| `unit_of_measure` | Unidade indicada pela USGS para a série/observação. Conferir antes de combinar séries. |
| `approval_status` | Estado de aprovação, por exemplo `Approved` ou `Provisional`; provisórios podem ser revisados. |
| `qualifier` | Qualificadores da observação (por exemplo, estimativa ou possível efeito de gelo), quando fornecidos. |
| `record_returned` | `True` se a API retornou uma linha para a série/data; `False` se a grade não encontrou linha correspondente. |
| `is_missing` | `True` quando `value_cfs` é ausente/não numérico; inclui lacunas da grade e linhas retornadas sem valor utilizável. |

**Distinções essenciais:** vazão igual a zero é uma medição válida, não ausência. `record_returned=False` indica ausência de linha da API; `record_returned=True` junto de `is_missing=True` indica que houve linha, mas sem valor numérico utilizável. Os `NaN` não devem ser removidos ou imputados antes da análise de cobertura/validação. Os indicadores de ausência também podem ser usados como máscaras de observação em modelos.

## Variáveis úteis para uma PINN ou modelo gerativo

- **Vazão (`00060`):** variável-alvo.
- **Nível (`00065`):** potencial observação auxiliar; relação nível–vazão depende da curva-chave e pode variar.
- **Precipitação (`00045`):** pode ser uma forçante local pontual; não representa automaticamente a precipitação média da bacia.
- **Evapotranspiração e precipitação espaciais:** provavelmente serão necessárias fontes externas à USGS para um balanço hídrico de bacia. Agregue à área de drenagem e alinhe a resolução temporal.
- **Área de drenagem e HUC:** contexto espacial para selecionar/agregar forçantes; confirme unidade da área e delineamento da bacia.

Não misture vazão de 15 minutos com chuva diária sem uma estratégia física e temporal explícita. A coleção `continuous` é de alta frequência e costuma ter intervalo fixo de 15 minutos, mas intervalo, disponibilidade, lacunas, qualificadores e status devem ser medidos por estação e parâmetro. Recomenda-se um piloto em poucas estações antes de um download nacional.

## Arquivos e execução

- `src/config.py`, `src/api.py`, `src/catalog.py`, `src/processing.py`, `src/plots.py` e `src/main.py` — configuração, cliente opcional da USGS OGC API, carregamento dos Parquets locais, preparação da tabela de observações, resumos, gráficos e pontos de entrada.
- `notebooks/usgs_streamflow.ipynb` — coleta, preparação e análise exploratória.
- `notebooks/análise_seleção.ipynb` — interface modular que filtra os Parquets diários pela seleção em `stations_full.parquet` e cria uma tabela longa com `date`, `value_cfs` e `monitoring_location_id`; não cria datas ausentes nem chama a API.
- `notebooks/central_dados_usgs.ipynb` — interface anterior de exploração dos arquivos locais, resumo de lacunas/zeros e gráficos por estação.
- `notebooks/usgs_continuous_15min.ipynb` — inventário e download controlado das séries USGS contínuas para estações sem vazão diária zero.
- `data/usgs/raw/` — cache Parquet do catálogo e dos lotes de observações; permite reaproveitar downloads.
- `data/usgs/processed/catalog_stations.csv` — catálogo de séries/estações incluídas pela etapa de seleção.
- `data/usgs/processed/stations_no_zero_continuous_candidates.csv` — estações reconstruídas a partir dos caches diários com observações e sem vazão zero.
- `data/usgs/processed/continuous_series_catalog.csv` — metadados das séries contínuas disponíveis para as estações selecionadas.
- `data/usgs/raw/continuous/` — páginas Parquet retomáveis das observações de alta frequência, após habilitar explicitamente o download no novo notebook.
- `data/usgs/raw/daily_<parâmetro>_<estatística>_<início>_<fim>_*.parquet` — observações diárias locais usadas por `análise_seleção.ipynb`.
- `data/usgs/processed/stations_full.parquet` — seleção de séries/estações usada para limitar a tabela de análise.
- `df_full` — grade diária completa produzida na memória pelo notebook exploratório; `análise_seleção.ipynb` tem outro objetivo e usa somente linhas existentes nos Parquets.
- `.env` — pode conter `USGS_API_KEY`; não versionar nem compartilhar.

### Executar no VS Code (Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Abra a pasta do projeto no VS Code, selecione o kernel `.venv` para `notebooks/usgs_streamflow.ipynb` e execute as células em ordem. Execute novamente as células após alterar parâmetros; outputs salvos no notebook podem refletir uma execução anterior. O notebook cria os diretórios de dados necessários. A API key é opcional no código atual, mas a ausência dela pode reduzir limites de uso.
