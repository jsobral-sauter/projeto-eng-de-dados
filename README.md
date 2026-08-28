# Projeto de Engenharia de Dados — Spotify Data Pipeline

Pipeline de dados end-to-end que consome a API pública do Spotify e carrega um catálogo musical relacional em PostgreSQL, seguindo os princípios de uma arquitetura Medallion (Landing local + Bronze + banco analítico).

## Arquitetura

```
Spotify API ──► src/ingestion/ ──► data/landing/YYYY-MM-DD/spotify_raw.json
    │   ▲             │
    │   └─ OAuth      │  src/enrichment/ (Last.fm / MusicBrainz)
    │  (dados pessoais)│        │
    │                 ▼        ▼
    │             src/load/ (bronze + upserts)
    │                    │
    └────────────────────┤
                         ▼
                  PostgreSQL (schema bronze append-only + schema spotify, 13 tabelas)
```

- **Extração:** Spotipy (client credentials) com retry/backoff em 429, 5xx e falhas de rede
- **OAuth:** dados pessoais (top artists/tracks, recently played, playlists próprias) via Authorization Code
- **Landing:** snapshot cru por partição diária em `data/landing/` (simula armazenamento em nuvem via pastas no SO; MinIO/fake-gcs-server é adicional futuro)
- **Enriquecimento:** gêneros de artistas + métricas de tracks via Last.fm (ou MusicBrainz) com cache local
- **Bronze:** camada estruturada append-only no PostgreSQL (schema `bronze`), idempotente por execução
- **Carga:** psycopg 3, transação atômica, `ON CONFLICT` idempotente, ordem topológica das FKs
- **Modelo:** DER relacional — artists, albums, tracks, genres, playlists, track_metrics + tabelas N:N e dados pessoais (user_top, recently_played)

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

# 3. Criar o schema (13 tabelas + índices)
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
- Landing gravado em `data/landing/<data>/spotify_raw.json` (snapshot diário; rerun no mesmo dia sobrescreve — sem duplicar arquivos)
- Camada bronze no PostgreSQL (schema `bronze`) é append-only por execução: cada execução adiciona histórico
- O load do schema `spotify` é idempotente: rodar N vezes não duplica registros
- Atenção: rodadas consecutivas muito próximas podem disparar rate limit da API

### Primeira execução (OAuth)

Para acessar os dados pessoais (top artists/tracks, recently played e playlists próprias), autorize uma vez:

1. No [dashboard](https://developer.spotify.com/dashboard) → seu app → Settings → **Redirect URIs**,
   cadastre exatamente `http://127.0.0.1:8888/callback` e salve
2. Rode no terminal (interativo):
   ```bash
   .venv/bin/python src/auth_spotify.py
   ```
3. O navegador abre → logar com a conta dona do app → **Accept**; o código é capturado
   automaticamente pelo servidor local (`http://127.0.0.1:8888`)
4. Se o navegador não abrir, acesse manualmente a URL impressa no terminal

O token fica em `.cache_user` e é renovado automaticamente. Sem autorização, o pipeline roda apenas
com dados públicos (playlists de terceiros viram só metadados). A conta dona do app precisa de
**Spotify Premium** (requisito do dev mode).

### Enriquecimento

Gêneros de artistas e métricas de tracks (playcount/listeners) vêm do Last.fm — requer `LASTFM_API_KEY`
no `.env` (crie em last.fm/api/account/create). Sem chave, usa MusicBrainz (apenas gêneros). Resultados
ficam em `data/enrichment_cache.json` para não refazer chamadas a cada execução. Configuração na seção
`enrichment` do `config.yaml` (`max_artists`/`max_tracks` limitam quantos itens por execução; o cache
faz execuções seguintes pegarem só o que falta).

## Estratégia de carga (Full vs Incremental) e idempotência

| Camada / dado | Estratégia | Como a idempotência é garantida |
|---|---|---|
| Landing (arquivos) | **Full** — snapshot diário | Caminho determinístico por partição (`data/landing/<dia>/spotify_raw.json`); rerun sobrescreve o mesmo arquivo |
| Bronze Postgres | **Histórico** por execução | `DELETE ... WHERE ingestion_timestamp = <run>` antes de cada INSERT → rerun não duplica |
| artists/albums/tracks/playlists (spotify) | **Full** (upsert) | `ON CONFLICT (spotify_id) DO UPDATE` |
| playlist_tracks | **Full** (snapshot) | DELETE + INSERT por playlist |
| user_top_tracks/artists | **Full** (snapshot) | `ON CONFLICT (snapshot_at, time_range, rank) DO NOTHING` |
| user_recently_played | **Incremental** | janela da API + `ON CONFLICT (played_at, track_id) DO NOTHING` |
| track_metrics | **Full** (upsert) | `ON CONFLICT (track_id) DO UPDATE` |
| Enrichment | cache local | chave estável por artista/track em `data/enrichment_cache.json` |

Executar o pipeline mais de uma vez para os mesmos dados **não duplica arquivos nem registros**.

## Inserção rápida

Para inserir algo pontual sem rodar o pipeline completo (segundos, poucas chamadas à API):

```bash
# CLI
.venv/bin/python src/quick_add.py --artist "Rush"
.venv/bin/python src/quick_add.py --track "Back in Black" --by "AC/DC"
.venv/bin/python src/quick_add.py --album <spotify_id> --playlist <spotify_id>
.venv/bin/python src/quick_add.py --from payload.json    # carrega payload pronto

# Menu interativo
.venv/bin/python src/quick_add.py
```

- Repetível (`--artist`/`--track`/`--album`/`--playlist` podem ser usados várias vezes no mesmo comando)
- `--album-pages N` controla quantas páginas de álbuns por artista (default 1)
- `--skip-enrich` pula o enriquecimento (máxima velocidade)
- **Idempotente**: inserir o mesmo item de novo não duplica registros no schema `spotify`
- **Landing**: grava em `data/landing/<dia>/quick_<hash>.json` — nome determinístico por conteúdo (rerun sobrescreve); o snapshot diário `spotify_raw.json` não é tocado
- Cada inserção vira um snapshot no bronze (histórico); a camada analítica (`spotify`) fica deduplicada

## Validar a carga

```bash
docker exec -i spotify_postgres psql -U admin -d spotify < db/sql/03_validate.sql
```

Checa contagens por tabela, duplicatas de `spotify_id` e FKs órfãs (tudo deve retornar 0).

## Estrutura

```
├── docker-compose.yml        # postgres + pgadmin
├── config.yaml               # artistas, playlists, enrichment e dados do usuário
├── requirements.txt
├── db/
│   ├── sql/                  # 01_schema, 02_indexes, 03_validate, 04_bronze
│   └── apply.sh              # aplica o DDL no container
├── src/
│   ├── ingestion/
│   │   ├── spotify_client.py # auth (client credentials + OAuth) + retry/backoff
│   │   ├── oauth.py          # SpotifyOAuth (Authorization Code) auto + manual
│   │   └── extract.py        # coleta e grava a Landing (data/landing)
│   ├── enrichment/
│   │   └── enrich.py         # gêneros/métricas via Last.fm ou MusicBrainz
│   ├── load/
│   │   ├── load_bronze.py    # bronze estruturada append-only no Postgres
│   │   └── load_postgres.py  # upserts em transação atômica
│   ├── run_pipeline.py       # orquestrador
│   ├── quick_add.py          # inserção rápida (CLI + menu interativo)
│   └── auth_spotify.py       # autorização OAuth isolada
├── data/landing/              # snapshot raw diário (ignorado pelo git)
└── docs/                     # DER e arquitetura Medallion
```

## Limitações conhecidas da API

A API do Spotify passou por mudanças (Nov/2024 e Fev/2026) que afetam apps em development mode:

- **Audio features / audio analysis** foram deprecados (403) — a tabela `audio_features` foi removida do modelo
- `popularity`/`followers` de artistas e `popularity` de tracks/albums foram **removidos** da resposta
- Gêneros de artistas não vêm mais da API → compensados via Last.fm/MusicBrainz
- Conteúdo de playlists só é devolvido para playlists **que o usuário é dono ou colabora** (OAuth)
- Search: `limit` máximo de 10 itens por página
- Preview de 30s (`preview_url`) removido

## Próximos passos

- ISRC/UPC (`external_ids`) — reativados pela API em Mar/2026, colunas ainda não adicionadas
- Camadas silver/gold em SQL
- Orquestração com Apache Airflow
- Migração para GCP (GCS + BigQuery + Cloud Run)
