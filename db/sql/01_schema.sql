-- =============================================================
-- 01_schema.sql
-- Camada de catálogo (modelo DER relacional) — schema spotify
-- Re-aplicável: DROP SCHEMA ... CASCADE recomeça do zero
-- Ordem de criação respeita as dependências de FK
-- =============================================================

DROP SCHEMA IF EXISTS spotify CASCADE;
CREATE SCHEMA spotify;

-- -------------------------------------------------------------
-- Entidades
-- -------------------------------------------------------------

CREATE TABLE spotify.genres (
    genre_id     BIGSERIAL    PRIMARY KEY,
    name         VARCHAR(255) NOT NULL UNIQUE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE spotify.artists (
    artist_id    BIGSERIAL    PRIMARY KEY,
    name         VARCHAR(255) NOT NULL,
    spotify_id   VARCHAR(50)  NOT NULL UNIQUE,
    popularity   INTEGER      CHECK (popularity BETWEEN 0 AND 100),
    followers    BIGINT,
    image_url    TEXT,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE spotify.artist_genres (
    artist_id    BIGINT NOT NULL REFERENCES spotify.artists(artist_id) ON DELETE CASCADE,
    genre_id     BIGINT NOT NULL REFERENCES spotify.genres(genre_id)   ON DELETE CASCADE,
    PRIMARY KEY (artist_id, genre_id)
);

CREATE TABLE spotify.albums (
    album_id     BIGSERIAL    PRIMARY KEY,
    name         VARCHAR(255) NOT NULL,
    spotify_id   VARCHAR(50)  NOT NULL UNIQUE,
    album_type   VARCHAR(50),
    release_date VARCHAR(10)  NOT NULL,
    total_tracks INTEGER      CHECK (total_tracks > 0),
    copyright    TEXT,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE spotify.album_artists (
    album_id     BIGINT  NOT NULL REFERENCES spotify.albums(album_id) ON DELETE CASCADE,
    artist_id    BIGINT  NOT NULL REFERENCES spotify.artists(artist_id) ON DELETE CASCADE,
    is_primary   BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (album_id, artist_id)
);

CREATE TABLE spotify.tracks (
    track_id     BIGSERIAL    PRIMARY KEY,
    name         VARCHAR(255) NOT NULL,
    spotify_id   VARCHAR(50)  NOT NULL UNIQUE,
    duration_ms  INTEGER      CHECK (duration_ms > 0),
    track_number INTEGER      CHECK (track_number > 0),
    explicit     BOOLEAN      NOT NULL DEFAULT FALSE,
    album_id     BIGINT       NOT NULL REFERENCES spotify.albums(album_id) ON DELETE RESTRICT,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE spotify.track_artists (
    track_id     BIGINT  NOT NULL REFERENCES spotify.tracks(track_id) ON DELETE CASCADE,
    artist_id    BIGINT  NOT NULL REFERENCES spotify.artists(artist_id) ON DELETE CASCADE,
    is_primary   BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (track_id, artist_id)
);

CREATE TABLE spotify.audio_features (
    track_id         BIGINT PRIMARY KEY REFERENCES spotify.tracks(track_id) ON DELETE CASCADE,
    danceability     REAL,
    energy           REAL,
    key              INTEGER,
    loudness         REAL,
    mode             INTEGER,
    speechiness      REAL,
    acousticness     REAL,
    instrumentalness REAL,
    liveness         REAL,
    valence          REAL,
    tempo            REAL,
    time_signature   INTEGER,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE spotify.playlists (
    playlist_id  BIGSERIAL    PRIMARY KEY,
    name         VARCHAR(255) NOT NULL,
    spotify_id   VARCHAR(50)  NOT NULL UNIQUE,
    description  TEXT,
    followers    BIGINT       NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- -------------------------------------------------------------
-- Tabelas associativas (N:N)
-- -------------------------------------------------------------

CREATE TABLE spotify.playlist_tracks (
    playlist_track_id BIGSERIAL PRIMARY KEY,
    playlist_id  BIGINT NOT NULL REFERENCES spotify.playlists(playlist_id) ON DELETE CASCADE,
    track_id     BIGINT NOT NULL REFERENCES spotify.tracks(track_id)      ON DELETE CASCADE,
    position     INTEGER,
    added_at     TIMESTAMPTZ,
    UNIQUE (playlist_id, position)
);
