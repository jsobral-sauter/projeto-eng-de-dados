DROP SCHEMA IF EXISTS spotify CASCADE;
CREATE SCHEMA spotify;

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
    image_url    TEXT,
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

CREATE TABLE spotify.playlists (
    playlist_id  BIGSERIAL    PRIMARY KEY,
    name         VARCHAR(255) NOT NULL,
    spotify_id   VARCHAR(50)  NOT NULL UNIQUE,
    description  TEXT,
    followers    BIGINT       NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE spotify.playlist_tracks (
    playlist_track_id BIGSERIAL PRIMARY KEY,
    playlist_id  BIGINT NOT NULL REFERENCES spotify.playlists(playlist_id) ON DELETE CASCADE,
    track_id     BIGINT NOT NULL REFERENCES spotify.tracks(track_id)      ON DELETE CASCADE,
    position     INTEGER,
    added_at     TIMESTAMPTZ,
    UNIQUE (playlist_id, position)
);

CREATE TABLE spotify.user_top_tracks (
    snapshot_at  TIMESTAMPTZ NOT NULL,
    time_range   VARCHAR(12) NOT NULL,
    rank         INTEGER     NOT NULL CHECK (rank > 0),
    track_id     BIGINT NOT NULL REFERENCES spotify.tracks(track_id) ON DELETE CASCADE,
    PRIMARY KEY (snapshot_at, time_range, rank)
);

CREATE TABLE spotify.user_top_artists (
    snapshot_at  TIMESTAMPTZ NOT NULL,
    time_range   VARCHAR(12) NOT NULL,
    rank         INTEGER     NOT NULL CHECK (rank > 0),
    artist_id    BIGINT NOT NULL REFERENCES spotify.artists(artist_id) ON DELETE CASCADE,
    PRIMARY KEY (snapshot_at, time_range, rank)
);

CREATE TABLE spotify.user_recently_played (
    played_at    TIMESTAMPTZ NOT NULL,
    track_id     BIGINT NOT NULL REFERENCES spotify.tracks(track_id) ON DELETE CASCADE,
    PRIMARY KEY (played_at, track_id)
);

CREATE TABLE spotify.track_metrics (
    track_metric_id BIGSERIAL PRIMARY KEY,
    track_id   BIGINT NOT NULL UNIQUE REFERENCES spotify.tracks(track_id) ON DELETE CASCADE,
    playcount  BIGINT,
    listeners  BIGINT,
    tags       TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
