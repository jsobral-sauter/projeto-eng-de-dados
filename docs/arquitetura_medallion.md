# Arquitetura do Projeto Analítico — Spotify Data Pipeline

## Visão Geral

Arquitetura baseada no modelo **Medallion (Bronze → Silver → Gold)** da Databricks/Lakehouse, orquestrada com Apache Airflow e orquestrada de forma incremental.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ARQUITETURA MEDALLION                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐               │
│  │ Spotify  │    │ YouTube  │    │  Last.fm │    │  CSV/    │               │
│  │   API    │    │   API    │    │   API    │    │  JSON    │               │
│  └────┬─────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘               │
│       │               │               │               │                      │
│       └───────────────┴───────┬───────┴───────────────┘                      │
│                               │                                              │
│                    ┌──────────▼──────────┐                                    │
│                    │     INGESTÃO        │  Airflow DAG: ingestao_spotify    │
│                    │  (Python/Spotipy)   │  Formato: JSON cru                 │
│                    └──────────┬──────────┘                                    │
│                               │                                              │
│              ╔════════════════▼════════════════════╗                          │
│              ║         BRONZE (RAW DATA)          ║                          │
│              ║                                    ║                          │
│              ║  Storage: S3 / Data Lake           ║                          │
│              ║  Formato: Parquet / Delta           ║                          │
│              ║  Particionado por: data_ingestao    ║                          │
│              ║                                    ║                          │
│              ║  bronze_artists_raw                 ║                          │
│              ║  bronze_albums_raw                  ║                          │
│              ║  bronze_tracks_raw                  ║                          │
│              ║  bronze_audio_features_raw          ║                          │
│              ╚════════════════╦═══════════════════╝                          │
│                               │                                              │
│                       ┌───────▼────────┐                                      │
│                       │  Data Quality  │  Great Expectations                  │
│                       │  Checks        │  Validações de schema               │
│                       └───────┬────────┘                                      │
│                               │                                              │
│              ╔════════════════▼════════════════════╗                          │
│              ║         SILVER (CLEAN DATA)        ║                          │
│              ║                                    ║                          │
│              ║  Storage: S3 / Data Lake           ║                          │
│              ║  Formato: Parquet / Delta           ║                          │
│              ║                                    ║                          │
│              ║  Transformações:                    ║                          │
│              ║   • Deduplicação (por ID)           ║                          │
│              ║   • Limpeza de campos nulos         ║                          │
│              ║   • Normalização de tipos            ║                          │
│              ║   • Enriquecimento (nomes, etc.)     ║                          │
│              ║   • Join entre entidades             ║                          │
│              ║                                    ║                          │
│              ║  dim_artist                         ║                          │
│              ║  dim_album                          ║                          │
│              ║  dim_track                          ║                          │
│              ║  dim_date                           ║                          │
│              ║  f_audio_features                   ║                          │
│              ╚════════════════╦═══════════════════╝                          │
│                               │                                              │
│              ╔════════════════▼════════════════════╗                          │
│              ║         GOLD (ANALYTICS)           ║                          │
│              ║                                    ║                          │
│              ║  Storage: S3 / Data Lake           ║                          │
│              ║  Formato: Parquet / Delta           ║                          │
│              ║                                    ║                          │
│              ║  Agregações:                        ║                          │
│              ║   • KPIs por artista               ║                          │
│              ║   • Popularidade por período         ║                          │
│              ║   • Distribuição de gêneros         ║                          │
│              ║   • Métricas de audio features      ║                          │
│              ║   • Lançamentos por ano/mês         ║                          │
│              ║                                    ║                          │
│              ║  gold_artist_kpis                   ║                          │
│              ║  gold_genre_distribution            ║                          │
│              ║  gold_trends_timeline               ║                          │
│              ╚════════════════╦═══════════════════╝                          │
│                               │                                              │
│              ┌────────────────┼────────────────┐                              │
│              │                │                │                              │
│     ┌────────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐                       │
│     │    Athena /   │  │  Power BI / │  │  Machine    │                       │
│     │   Trino SQL   │  │  Streamlit  │  │  Learning   │                       │
│     │  (Consultas)  │  │ (Dashboard) │  │ (Modelos)   │                       │
│     └───────────────┘  └─────────────┘  └─────────────┘                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Camada BRONZE (Raw / Landing)

### Objetivo
Armazenar os dados exatamente como vieram da API do Spotify, sem nenhuma transformação. Garantir rastreabilidade total e reprocessamento a qualquer momento.

### O que armazena
| Tabela | Descrição | Fonte |
|--------|-----------|-------|
| `bronze_artists_raw` | Dados brutos de artistas | `sp.artist()` / `sp.search()` |
| `bronze_albums_raw` | Dados brutos de álbuns | `sp.album()` / `sp.artist_albums()` |
| `bronze_tracks_raw` | Dados brutos de faixas | `sp.album().tracks` / `sp.track()` |
| `bronze_audio_features_raw` | Audio features (danceability, energy, etc.) | `sp.audio_features()` |

### Características
- **Formato:** Parquet ou Delta Lake (particionado por `data_ingestao`)
- **Schema-on-read:** armazena como `JSON string` ou colunas semi-estruturadas
- **Append-only:** cada execução gera novas partições (nunca sobrescreve)
- **Governança:** metadados incluídos — `_ingestion_timestamp`, `_source_file`

### Exemplo — `bronze_albums_raw`
```
data_ingestao | album_id   | raw_json                                  | _ingestion_timestamp
2026-08-10    | 3MhU6G... | {"nome":"BRUTAL PARAÍSO","tracks":[...]} | 2026-08-10T14:30:00
```

---

## 2. Camada SILVER (Clean / Curated)

### Objetivo
Limpar, deduplicar, normalizar e estruturar os dados. Implementar Data Quality checks. Transformar de semi-estruturado para modelo relacional (star schema).

### Transformações aplicadas
1. **Deduplicação:** `ROW_NUMBER() OVER (PARTITION BY id ORDER BY ingestion DESC)` — mantém só o mais recente
2. **Limpeza:** campos nulos preenchidos com defaults adequados; strings trimados
3. **Tipagem:** datas → `DATE`, durações → `INT` (ms), booleanos → `BOOLEAN`
4. **Enriquecimento:** extração de ano/mês de `release_date`, categorização de explicit

### Modelo de Dados (Star Schema)

```
┌──────────────────────┐
│     dim_artist       │
├──────────────────────┤
│ artist_id    PK      │
│ name                 │
│ genres[]             │
│ followers            │
│ popularity           │
│ image_url            │
│ external_url         │
└─────────┬────────────┘
          │ 1
          │
          │ N
┌─────────▼────────────┐        ┌──────────────────────┐
│     dim_album        │        │    dim_track         │
├──────────────────────┤        ├──────────────────────┤
│ album_id     PK      │───1:N──│ track_id     PK      │
│ artist_id    FK      │        │ album_id     FK      │
│ name                 │        │ name                 │
│ release_date         │        │ duration_ms          │
│ total_tracks         │        │ track_number         │
│ album_type           │        │ explicit             │
│ label                │        │ preview_url          │
│ copyrights           │        │ popularity           │
└──────────────────────┘        └──────────┬───────────┘
                                           │ 1
                                           │
                                           │ 1
                                ┌──────────▼───────────┐
                                │  f_audio_features    │
                                ├──────────────────────┤
                                │ track_id     PK, FK  │
                                │ danceability         │
                                │ energy               │
                                │ key                  │
                                │ loudness             │
                                │ mode                 │
                                │ speechiness          │
                                │ acousticness         │
                                │ instrumentalness     │
                                │ liveness             │
                                │ valence              │
                                │ tempo                │
                                └──────────────────────┘

                    ┌──────────────────────┐
                    │     dim_date         │
                    ├──────────────────────┤
                    │ date_id      PK      │
                    │ full_date            │
                    │ year                 │
                    │ month                │
                    │ day                  │
                    │ quarter              │
                    │ day_of_week          │
                    │ is_weekend           │
                    └──────────────────────┘
```

### Data Quality (Great Expectations)
- `artist_id` e `album_id` nunca nulos
- `duration_ms` > 0
- `track_number` entre 1 e `total_tracks`
- `popularity` entre 0 e 100
- `release_date` é uma data válida
- Sem duplicatas de `track_id` + `album_id`

---

## 3. Camada GOLD (Analytics / Consumption)

### Objetivo
Criar cubos analíticos, métricas de negócio e visões prontas para consumo via BI, dashboards e modelos de ML.

### Tabelas Agregadas

| Tabela | Descrição | Exemplos de colunas |
|--------|-----------|---------------------|
| `gold_artist_kpis` | KPIs consolidados por artista | total_albums, total_tracks, avg_popularity, avg_duration, followers |
| `gold_genre_distribution` | Distribuição de gêneros musicais | genre, artist_count, avg_popularity |
| `gold_trends_timeline` | Tendências temporais | year, month, releases_count, avg_danceability, avg_energy |
| `gold_audio_features_profile` | Perfil sonoro por artista | artist, avg_danceability, avg_energy, avg_valence, avg_tempo |
| `gold_explicit_analysis` | Análise de conteúdo explícito | artist, explicit_ratio, total_explicit |

### Exemplo de SQL GOLD — `gold_artist_kpis`
```sql
SELECT
    a.artist_id,
    a.name                        AS artist_name,
    COUNT(DISTINCT al.album_id)   AS total_albums,
    COUNT(DISTINCT t.track_id)    AS total_tracks,
    ROUND(AVG(a.popularity), 2)   AS avg_popularity,
    ROUND(AVG(t.duration_ms)/1000, 0) AS avg_duration_sec,
    a.followers                   AS total_followers
FROM silver.dim_artist a
LEFT JOIN silver.dim_album  al ON al.artist_id = a.artist_id
LEFT JOIN silver.dim_track  t  ON t.album_id  = al.album_id
GROUP BY a.artist_id, a.name, a.followers
```

---

## 4. Stack Tecnológico

| Componente | Tecnologia Sugerida | Alternativa |
|------------|---------------------|-------------|
| **Orquestração** | Apache Airflow / Prefect | Dagster |
| **Ingestão** | Python + Spotipy | Singer Taps |
| **Storage** | AWS S3 / MinIO (local) | Azure Data Lake, GCS |
| **Processamento** | PySpark / Polars | DuckDB, Pandas |
| **Catálogo** | AWS Glue / Unity Catalog | Hive Metastore, Amundsen |
| **Data Quality** | Great Expectations | Soda, dbt tests |
| **Query Engine** | Amazon Athena / Trino | Presto, DuckDB |
| **Transformação** | dbt (SQL) + PySpark (Python) | SQLMesh |
| **Dashboard** | Streamlit / Power BI | Metabase, Looker |
| **ML** | Scikit-learn / PyTorch | MLflow para tracking |
| **CI/CD** | GitHub Actions | GitLab CI |
| **IaC** | Terraform | Pulumi, CDK |
| **Controle Versão** | Delta Lake (time travel) | Iceberg, Hudi |
| **Monitoramento** | Prometheus + Grafana | Datadog, CloudWatch |

---

## 5. Orquestração — DAG Airflow

```
                    ┌───────────────────────┐
                    │  ingest_spotify_data  │  1x por dia
                    │  (chama Spotipy API)  │
                    └──────────┬────────────┘
                               │
                    ┌──────────▼────────────┐
                    │   dq_check_bronze     │  Valida schema + nulls
                    └──────────┬────────────┘
                               │
                               ├─── OK ───┐
                               │          │
                    ┌──────────▼─────────┐ │  ┌──────────────────┐
                    │  silver_transform  │ │  │  alert_falha_dq  │
                    └──────────┬─────────┘ │  └──────────────────┘
                               │
                    ┌──────────▼─────────┐
                    │  dq_check_silver    │
                    └──────────┬─────────┘
                               │
                    ┌──────────▼─────────┐
                    │  gold_aggregate     │
                    ├─────────────────────┤
                    │ gold_artist_kpis    │
                    │ gold_genre_dist     │
                    │ gold_trends         │
                    └──────────┬─────────┘
                               │
                    ┌──────────▼─────────┐
                    │  refresh_dashboard  │  Atualiza cache Streamlit
                    └────────────────────┘
```

---

## 6. Estratégia de Particionamento e Performance

| Camada | Particionamento | Justificativa |
|--------|----------------|---------------|
| **Bronze** | `data_ingestao` (YYYY-MM-DD) | Append diário, facilita reprocessamento por período |
| **Silver** | `artist_id` (hash mod 10) | Distribuição uniforme para joins frequentes |
| **Gold** | `year`, `month` | Consultas temporais são as mais comuns em dashboards |

---

## 7. Estrutura de Diretórios do Projeto

```
projeto-eng-de-dados/
├── docs/
│   ├── arquitetura_medallion.md    # Este documento
│   └── Diagram DER.png             # Diagrama Entidade-Relacionamento
├── src/
│   ├── ingestion/
│   │   ├── spotify_extractor.py    # Cliente de extração (refatorado do atual)
│   │   └── api_client.py           # Gerenciador de autenticação/rate-limit
│   ├── bronze/
│   │   └── raw_to_bronze.py        # Escrita na camada bronze (Parquet/Delta)
│   ├── silver/
│   │   ├── dim_artist.py           # Transformação dim_artist
│   │   ├── dim_album.py            # Transformação dim_album
│   │   ├── dim_track.py            # Transformação dim_track
│   │   └── f_audio_features.py     # Transformação fato audio features
│   ├── gold/
│   │   ├── artist_kpis.sql         # Query de agregação GOLD
│   │   ├── genre_distribution.sql
│   │   ├── trends_timeline.sql
│   │   └── audio_profile.sql
│   └── quality/
│       ├── expectations_bronze.json # Great Expectations suites
│       └── expectations_silver.json
├── dags/
│   └── spotify_pipeline.py         # DAG do Airflow
├── dashboards/
│   └── app.py                      # Streamlit dashboard
├── tests/
├── .env
├── requirements.txt
└── README.md
```

---

## 8. Diagrama do Fluxo de Dados (End-to-End)

```
┌─────────────────────────────────────────────────────────────────────┐
│  Spotify API               Airflow DAG              Storage (S3)    │
│  ═════════                 ═══════════             ══════════════   │
│                                                                     │
│  /search    ──► Ingestão ──► bronze_artists_raw ──┐                 │
│  /artists   ──► Ingestão ──► bronze_artists_raw ──┤                 │
│  /albums    ──► Ingestão ──► bronze_albums_raw  ──┤                 │
│  /tracks    ──► Ingestão ──► bronze_tracks_raw  ──┤                 │
│  /audio-    ──► Ingestão ──► bronze_audio_raw   ──┤                 │
│   features                                         │                 │
│                                                    ▼                 │
│                                          ┌─────────────────┐        │
│                                          │  DQ Checks       │        │
│                                          │  (GX Suite)      │        │
│                                          └────────┬────────┘        │
│                                                   ▼                 │
│                                          ┌─────────────────┐        │
│                                          │  Silver Layer    │        │
│                                          │  (Star Schema)   │        │
│                                          │  dim_artist      │        │
│                                          │  dim_album       │        │
│                                          │  dim_track       │        │
│                                          │  dim_date        │        │
│                                          │  f_audio_features│        │
│                                          └────────┬────────┘        │
│                                                   ▼                 │
│                                          ┌─────────────────┐        │
│                                          │  Gold Layer      │        │
│                                          │  (Aggregations)  │        │
│                                          │  gold_artist_kpis│        │
│                                          │  gold_trends     │        │
│                                          └────────┬────────┘        │
│                                                   ▼                 │
│                                          ┌─────────────────┐        │
│                                          │  Consumers       │        │
│                                          │  • Athena SQL    │        │
│                                          │  • Streamlit BI  │        │
│                                          │  • ML Models     │        │
│                                          └─────────────────┘        │
└─────────────────────────────────────────────────────────────────────┘
```
