-- =============================================================
-- 02_indexes.sql
-- Índices para joins por FK
-- PostgreSQL não cria índice automático em FK.
-- O UNIQUE (playlist_id, position) de playlist_tracks já cobre
-- buscas por playlist_id (coluna mais à esquerda do índice).
-- =============================================================

CREATE INDEX idx_tracks_album_id          ON spotify.tracks(album_id);
CREATE INDEX idx_playlist_tracks_track_id ON spotify.playlist_tracks(track_id);
CREATE INDEX idx_track_artists_artist_id  ON spotify.track_artists(artist_id);
CREATE INDEX idx_album_artists_artist_id  ON spotify.album_artists(artist_id);
CREATE INDEX idx_artist_genres_genre_id   ON spotify.artist_genres(genre_id);
