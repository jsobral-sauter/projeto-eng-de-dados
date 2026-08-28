-- Limpeza total da camada bronze: recria o schema do zero.
-- DDL não consome API; os dados voltam na próxima execução do pipeline.
DROP SCHEMA IF EXISTS bronze CASCADE;
CREATE SCHEMA bronze;

CREATE TABLE IF NOT EXISTS bronze.artists_raw (
    artist_raw_id        BIGSERIAL    PRIMARY KEY,
    spotify_id           VARCHAR(50)  NOT NULL,
    name                 VARCHAR(255) NOT NULL,
    image_url            TEXT,
    external_url         TEXT,
    genres               TEXT[],
    ingestion_timestamp  TIMESTAMPTZ  NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.albums_raw (
    album_raw_id         BIGSERIAL    PRIMARY KEY,
    spotify_id           VARCHAR(50)  NOT NULL,
    name                 VARCHAR(255) NOT NULL,
    album_type           VARCHAR(50),
    release_date         VARCHAR(10),
    total_tracks         INTEGER,
    copyright            TEXT[],
    artist_ids           TEXT[],
    genres               TEXT[],
    ingestion_timestamp  TIMESTAMPTZ  NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.tracks_raw (
    track_raw_id         BIGSERIAL    PRIMARY KEY,
    spotify_id           VARCHAR(50)  NOT NULL,
    name                 VARCHAR(255) NOT NULL,
    duration_ms          INTEGER,
    track_number         INTEGER,
    explicit             BOOLEAN      NOT NULL DEFAULT FALSE,
    album_id             VARCHAR(50),
    artist_ids           TEXT[],
    ingestion_timestamp  TIMESTAMPTZ  NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.playlists_raw (
    playlist_raw_id      BIGSERIAL    PRIMARY KEY,
    spotify_id           VARCHAR(50)  NOT NULL,
    name                 VARCHAR(255) NOT NULL,
    description          TEXT,
    followers            BIGINT,
    ingestion_timestamp  TIMESTAMPTZ  NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.playlist_tracks_raw (
    playlist_track_raw_id BIGSERIAL   PRIMARY KEY,
    playlist_spotify_id   VARCHAR(50) NOT NULL,
    track_spotify_id      VARCHAR(50),
    position              INTEGER,
    added_at              TIMESTAMPTZ,
    ingestion_timestamp   TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.user_top_tracks_raw (
    user_top_track_raw_id BIGSERIAL   PRIMARY KEY,
    snapshot_at           TIMESTAMPTZ NOT NULL,
    time_range            VARCHAR(12) NOT NULL,
    rank                  INTEGER     NOT NULL,
    track_spotify_id      VARCHAR(50),
    ingestion_timestamp   TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.user_top_artists_raw (
    user_top_artist_raw_id BIGSERIAL  PRIMARY KEY,
    snapshot_at            TIMESTAMPTZ NOT NULL,
    time_range             VARCHAR(12) NOT NULL,
    rank                   INTEGER     NOT NULL,
    artist_spotify_id      VARCHAR(50),
    ingestion_timestamp    TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.user_recently_played_raw (
    user_recently_played_raw_id BIGSERIAL PRIMARY KEY,
    played_at                   TIMESTAMPTZ NOT NULL,
    track_spotify_id            VARCHAR(50),
    ingestion_timestamp         TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.track_metrics_raw (
    track_metric_raw_id BIGSERIAL PRIMARY KEY,
    track_spotify_id    VARCHAR(50) NOT NULL,
    track_name          VARCHAR(255),
    artist_name         VARCHAR(255),
    playcount           BIGINT,
    listeners           BIGINT,
    tags                TEXT[],
    ingestion_timestamp TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bronze_artists_spotify_id      ON bronze.artists_raw(spotify_id);
CREATE INDEX IF NOT EXISTS idx_bronze_artists_ingestion_ts    ON bronze.artists_raw(ingestion_timestamp);
CREATE INDEX IF NOT EXISTS idx_bronze_artists_genres          ON bronze.artists_raw USING GIN (genres);
CREATE INDEX IF NOT EXISTS idx_bronze_albums_spotify_id       ON bronze.albums_raw(spotify_id);
CREATE INDEX IF NOT EXISTS idx_bronze_albums_ingestion_ts     ON bronze.albums_raw(ingestion_timestamp);
CREATE INDEX IF NOT EXISTS idx_bronze_albums_artist_ids       ON bronze.albums_raw USING GIN (artist_ids);
CREATE INDEX IF NOT EXISTS idx_bronze_tracks_spotify_id       ON bronze.tracks_raw(spotify_id);
CREATE INDEX IF NOT EXISTS idx_bronze_tracks_ingestion_ts     ON bronze.tracks_raw(ingestion_timestamp);
CREATE INDEX IF NOT EXISTS idx_bronze_tracks_artist_ids       ON bronze.tracks_raw USING GIN (artist_ids);
CREATE INDEX IF NOT EXISTS idx_bronze_playlists_spotify_id    ON bronze.playlists_raw(spotify_id);
CREATE INDEX IF NOT EXISTS idx_bronze_playlists_ingestion_ts  ON bronze.playlists_raw(ingestion_timestamp);
CREATE INDEX IF NOT EXISTS idx_bronze_pt_playlist_spotify_id  ON bronze.playlist_tracks_raw(playlist_spotify_id);
CREATE INDEX IF NOT EXISTS idx_bronze_pt_track_spotify_id     ON bronze.playlist_tracks_raw(track_spotify_id);
CREATE INDEX IF NOT EXISTS idx_bronze_pt_ingestion_ts         ON bronze.playlist_tracks_raw(ingestion_timestamp);
CREATE INDEX IF NOT EXISTS idx_bronze_utt_snapshot            ON bronze.user_top_tracks_raw(snapshot_at);
CREATE INDEX IF NOT EXISTS idx_bronze_utt_track_spotify_id    ON bronze.user_top_tracks_raw(track_spotify_id);
CREATE INDEX IF NOT EXISTS idx_bronze_uta_snapshot            ON bronze.user_top_artists_raw(snapshot_at);
CREATE INDEX IF NOT EXISTS idx_bronze_uta_artist_spotify_id   ON bronze.user_top_artists_raw(artist_spotify_id);
CREATE INDEX IF NOT EXISTS idx_bronze_urp_played_at           ON bronze.user_recently_played_raw(played_at);
CREATE INDEX IF NOT EXISTS idx_bronze_urp_track_spotify_id    ON bronze.user_recently_played_raw(track_spotify_id);
CREATE INDEX IF NOT EXISTS idx_bronze_tm_track_spotify_id     ON bronze.track_metrics_raw(track_spotify_id);
