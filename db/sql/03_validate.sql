-- =============================================================
-- 03_validate.sql — Validações pós-carga (data quality)
-- Qualquer resultado > 0 indica problema a investigar.
-- =============================================================

-- 1) Contagem de registros por tabela
SELECT 'artists' AS tabela, count(*) FROM spotify.artists
UNION ALL SELECT 'albums', count(*) FROM spotify.albums
UNION ALL SELECT 'tracks', count(*) FROM spotify.tracks
UNION ALL SELECT 'audio_features', count(*) FROM spotify.audio_features
UNION ALL SELECT 'genres', count(*) FROM spotify.genres
UNION ALL SELECT 'playlists', count(*) FROM spotify.playlists
UNION ALL SELECT 'artist_genres', count(*) FROM spotify.artist_genres
UNION ALL SELECT 'album_artists', count(*) FROM spotify.album_artists
UNION ALL SELECT 'track_artists', count(*) FROM spotify.track_artists
UNION ALL SELECT 'playlist_tracks', count(*) FROM spotify.playlist_tracks
ORDER BY tabela;

-- 2) Duplicatas de spotify_id (deve retornar 0 linhas)
SELECT spotify_id, count(*) FROM spotify.artists GROUP BY spotify_id HAVING count(*) > 1;
SELECT spotify_id, count(*) FROM spotify.albums  GROUP BY spotify_id HAVING count(*) > 1;
SELECT spotify_id, count(*) FROM spotify.tracks  GROUP BY spotify_id HAVING count(*) > 1;

-- 3) FKs órfãs (todos devem retornar 0)
SELECT count(*) AS tracks_sem_album
FROM spotify.tracks t LEFT JOIN spotify.albums a USING (album_id) WHERE a.album_id IS NULL;
SELECT count(*) AS track_artists_sem_track
FROM spotify.track_artists ta LEFT JOIN spotify.tracks t USING (track_id) WHERE t.track_id IS NULL;
SELECT count(*) AS track_artists_sem_artist
FROM spotify.track_artists ta LEFT JOIN spotify.artists a USING (artist_id) WHERE a.artist_id IS NULL;
SELECT count(*) AS album_artists_sem_album
FROM spotify.album_artists aa LEFT JOIN spotify.albums a USING (album_id) WHERE a.album_id IS NULL;
SELECT count(*) AS album_artists_sem_artist
FROM spotify.album_artists aa LEFT JOIN spotify.artists a USING (artist_id) WHERE a.artist_id IS NULL;
SELECT count(*) AS artist_genres_sem_artist
FROM spotify.artist_genres ag LEFT JOIN spotify.artists a USING (artist_id) WHERE a.artist_id IS NULL;
SELECT count(*) AS artist_genres_sem_genre
FROM spotify.artist_genres ag LEFT JOIN spotify.genres g USING (genre_id) WHERE g.genre_id IS NULL;
SELECT count(*) AS audio_features_sem_track
FROM spotify.audio_features af LEFT JOIN spotify.tracks t USING (track_id) WHERE t.track_id IS NULL;
SELECT count(*) AS playlist_tracks_sem_playlist
FROM spotify.playlist_tracks pt LEFT JOIN spotify.playlists p USING (playlist_id) WHERE p.playlist_id IS NULL;
SELECT count(*) AS playlist_tracks_sem_track
FROM spotify.playlist_tracks pt LEFT JOIN spotify.tracks t USING (track_id) WHERE t.track_id IS NULL;
