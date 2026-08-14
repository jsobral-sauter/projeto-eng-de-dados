# Projeto de Engenharia de Dados — Spotify Data Pipeline

Pipeline de dados end-to-end que consome a API pública do Spotify e carrega um catálogo musical relacional em PostgreSQL, seguindo os princípios de uma arquitetura Medallion (bronze local + banco analítico).

## Arquitetura

```
Spotify API ──► src/ingestion/ ──► data/bronze/YYYY-MM-DD/spotify_raw.json
                                     │
                                     ▼
                              src/load/ (upserts)
                                     │
                                     ▼
                              PostgreSQL (schema spotify, 10 tabelas)
```

- **Extração:** Spotipy (client credentials) com retry/backoff em 429, 5xx e falhas de rede
- **Bronze:** JSON cru, append-only, particionado por data de ingestão
- **Carga:** psycopg 3, transação atômica, `ON CONFLICT` idempotente, ordem topológica das FKs
- **Modelo:** DER relacional — artists, albums, tracks, audio_features, genres, playlists + 4 tabelas N:N

## Stack

| Camada | Tecnologia |
|---|---|
| Banco | PostgreSQL 17 (Docker) |
| UI do banco | pgAdmin 9 (Docker) |
| Ingestão | Python 3.14 + Spotipy |
| Carga | psycopg 3 |
| Config | YAML + dotenv |

## Setup

```bash
# 1. Configurar variáveis de ambiente
cp .env.example .env   # preencher com credenciais reais

# 2. Subir PostgreSQL + pgAdmin
docker compose up -d

# 3. Criar o schema (10 tabelas + índices)
./db/apply.sh

# 4. Dependências Python
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

- PostgreSQL: `localhost:5432` (db `spotify`, ver `.env`)
- pgAdmin: `http://localhost:5050` — ao registrar o servidor, usar host `postgres` e database `spotify`

## Executar o pipeline

```bash
.venv/bin/python src/run_pipeline.py
```

- Artistas e playlists alvo são definidos em `config.yaml`
- Bronze gravado em `data/bronze/<data>/spotify_raw.json`
- O load é idempotente: rodar N vezes não duplica registros
- Atenção: rodadas consecutivas muito próximas podem disparar rate limit da API

## Validar a carga

```bash
docker exec -i spotify_postgres psql -U admin -d spotify < db/sql/03_validate.sql
```

Checa contagens por tabela, duplicatas de `spotify_id` e FKs órfãs (tudo deve retornar 0).

## Estrutura

```
├── docker-compose.yml        # postgres + pgadmin
├── config.yaml               # artistas e playlists alvo
├── requirements.txt
├── db/
│   ├── sql/                  # 01_schema, 02_indexes, 03_validate
│   └── apply.sh              # aplica o DDL no container
├── src/
│   ├── ingestion/
│   │   ├── spotify_client.py # auth + retry/backoff
│   │   └── extract.py        # coleta e grava bronze
│   ├── load/
│   │   └── load_postgres.py  # upserts em transação atômica
│   └── run_pipeline.py       # orquestrador
├── data/bronze/              # dados crus (ignorado pelo git)
└── docs/                     # DER e arquitetura Medallion
```

## Limitações conhecidas da API

- Artistas retornam objeto simplificado (sem popularity/followers/genres)
- Endpoint de audio features depreciado (403) — tabela `audio_features` fica vazia
- Itens de playlists exigem OAuth de usuário — apenas metadados são carregados
- Paginação limitada a 10 itens em alguns endpoints

## Próximos passos

- Fluxo OAuth (Authorization Code) para playlists pessoais
- Camadas silver/gold em SQL (star schema + agregações)
- Orquestração com Apache Airflow
- Migração para GCP (GCS + BigQuery + Cloud Run)
