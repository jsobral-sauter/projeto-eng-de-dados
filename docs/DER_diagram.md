# 📊 Visão Geral do Banco de Dados

O diagrama representa um esquema de banco de dados relacional para um sistema de catálogo de músicas (semelhante ao Spotify). O esquema gerencia as relações complexas entre **Músicas (Tracks)**, **Álbuns (Albums)**, **Artistas (Artists)**, **Gêneros (Genres)** e **Listas de Reprodução (Playlists)**. 

O banco utiliza tabelas associativas (tabelas de junção) para resolver relacionamentos muitos-para-muitos (N:N).

---

## 🗄️ Dicionário de Dados (Tabelas e Colunas)

### 1. Entidades Principais

*   **`playlists`** (Listas de reprodução dos usuários/sistema)
    *   `playlist_id` **(PK)**
    *   `name`
    *   `spotify_id`
    *   `description`
    *   `followers`

*   **`tracks`** (Músicas)
    *   `track_id` **(PK)**
    *   `name`
    *   `duration_ms`
    *   `track_number`
    *   `expllicit` *(Nota: Escrito com dois 'L's no diagrama original)*
    *   `album_id` **(FK)** -> Referencia `albums(album_id)`

*   **`track_metrics`** (Métricas de tracks vindas do Last.fm)
    *   `track_metric_id` **(PK)**
    *   `track_id` **(FK)** -> Referencia `tracks(track_id)` (1:1)
    *   `playcount`
    *   `listeners`
    *   `tags`

*   **`albums`** (Álbuns musicais)
    *   `album_id` **(PK)**
    *   `name`
    *   `spotify_id`
    *   `album_type` *(Nota: Este campo aparece duplicado no diagrama original)*
    *   `release_date`
    *   `total_tracks`
    *   `copyright`

*   **`artists`** (Artistas/Bandas)
    *   `artist_id` **(PK)**
    *   `name`
    *   `spotify_id`
    *   `image_url`

*   **`genres`** (Gêneros musicais)
    *   `genre_id` **(PK)**
    *   `name`

---

### 2. Tabelas Associativas (Resolução de Relacionamentos N:M)

*   **`playlist_tracks`** (Relaciona Playlists com Músicas)
    *   `playlist_id` **(PK/FK)** -> Referencia `playlists`
    *   `track_id` **(PK/FK)** -> Referencia `tracks`
    *   `position` (Ordem da música na playlist)
    *   `added_at` (Data em que foi adicionada)

*   **`track_artists`** (Relaciona Músicas com Artistas)
    *   `track_id` **(PK/FK)** -> Referencia `tracks`
    *   `artist_id` **(PK/FK)** -> Referencia `artists`
    *   `is_primary` (Booleano/Flag indicando se é o artista principal da música)

*   **`album_artists`** (Relaciona Álbuns com Artistas)
    *   `album_id` **(PK/FK)** -> Referencia `albums`
    *   `artist_id` **(PK/FK)** -> Referencia `artists`
    *   `is_primary` (Booleano/Flag indicando se é o artista principal do álbum)

*   **`artist_genres`** (Relaciona Artistas com Gêneros)
    *   `genre_id` **(PK/FK)** -> Referencia `genres`
    *   `artist_id` **(PK/FK)** -> Referencia `artists`

### 3. Dados Pessoais do Usuário (OAuth)

*   **`user_top_tracks`** (Ranking das tracks mais ouvidas — snapshot por execução)
    *   `snapshot_at`, `time_range`, `rank` **(PK composto)**
    *   `track_id` **(FK)** -> Referencia `tracks`

*   **`user_top_artists`** (Ranking dos artistas mais ouvidos — snapshot por execução)
    *   `snapshot_at`, `time_range`, `rank` **(PK composto)**
    *   `artist_id` **(FK)** -> Referencia `artists`

*   **`user_recently_played`** (Histórico recente de reprodução)
    *   `played_at`, `track_id` **(PK composto)**
    *   `track_id` **(FK)** -> Referencia `tracks`

---

> **⚠️ O diagrama `Diagram DER.png` está desatualizado** (ainda contém `audio_features` e
> `popularity`/`followers` de artistas). Este documento reflete o modelo atual.

---

## 🔗 Relacionamentos e Cardinalidades

| Entidade A | Cardinalidade | Entidade B | Tabela de Resolução | Descrição do Relacionamento |
| :--- | :---: | :--- | :--- | :--- |
| `playlists` | **N:M** | `tracks` | `playlist_tracks` | Uma playlist pode ter várias músicas; uma música pode estar em várias playlists. (1:N de ambas para a tabela associativa). |
| `tracks` | **1:1** | `track_metrics` | *(Nenhuma)* | Cada música tem um registro opcional com métricas do Last.fm (playcount/listeners/tags). `track_id` é UNIQUE em `track_metrics`. |
| `albums` | **1:N** | `tracks` | *(Nenhuma)* | Um álbum contém várias músicas. A tabela `tracks` armazena o `album_id` (FK). |
| `tracks` | **N:M** | `artists` | `track_artists` | Uma música pode ter vários artistas (ex: feats), e um artista tem várias músicas. |
| `albums` | **N:M** | `artists` | `album_artists` | Um álbum pode ser colaborativo (vários artistas), e um artista lança vários álbuns. |
| `artists` | **N:M** | `genres` | `artist_genres` | Um artista pode ser classificado em vários gêneros, e um gênero engloba vários artistas. |

> **💡 Notas úteis (Anomalias do diagrama):** 
> 1. A coluna de conteúdo explícito na tabela `tracks` foi nomeada com um erro de digitação como **`expllicit`** (com dois 'L').
> 2. A tabela `albums` possui o atributo **`album_type`** listado duas vezes consecutivas.
