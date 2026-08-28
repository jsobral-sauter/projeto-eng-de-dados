
-- 1) Contagem de registros por tabela
SELECT 'artists' AS tabela, count(*) FROM spotify.artists
UNION ALL SELECT 'albums', count(*) FROM spotify.albums
UNION ALL SELECT 'tracks', count(*) FROM spotify.tracks
UNION ALL SELECT 'genres', count(*) FROM spotify.genres
UNION ALL SELECT 'playlists', count(*) FROM spotify.playlists
UNION ALL SELECT 'artist_genres', count(*) FROM spotify.artist_genres
UNION ALL SELECT 'album_artists', count(*) FROM spotify.album_artists
UNION ALL SELECT 'track_artists', count(*) FROM spotify.track_artists
UNION ALL SELECT 'playlist_tracks', count(*) FROM spotify.playlist_tracks
UNION ALL SELECT 'user_top_tracks', count(*) FROM spotify.user_top_tracks
UNION ALL SELECT 'user_top_artists', count(*) FROM spotify.user_top_artists
UNION ALL SELECT 'user_recently_played', count(*) FROM spotify.user_recently_played
UNION ALL SELECT 'track_metrics', count(*) FROM spotify.track_metrics
UNION ALL SELECT 'bronze_artists_raw', count(*) FROM bronze.artists_raw
UNION ALL SELECT 'bronze_albums_raw', count(*) FROM bronze.albums_raw
UNION ALL SELECT 'bronze_tracks_raw', count(*) FROM bronze.tracks_raw
UNION ALL SELECT 'bronze_playlists_raw', count(*) FROM bronze.playlists_raw
UNION ALL SELECT 'bronze_playlist_tracks_raw', count(*) FROM bronze.playlist_tracks_raw
UNION ALL SELECT 'bronze_user_top_tracks_raw', count(*) FROM bronze.user_top_tracks_raw
UNION ALL SELECT 'bronze_user_top_artists_raw', count(*) FROM bronze.user_top_artists_raw
UNION ALL SELECT 'bronze_user_recently_played_raw', count(*) FROM bronze.user_recently_played_raw
UNION ALL SELECT 'bronze_track_metrics_raw', count(*) FROM bronze.track_metrics_raw
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
SELECT count(*) AS playlist_tracks_sem_playlist
FROM spotify.playlist_tracks pt LEFT JOIN spotify.playlists p USING (playlist_id) WHERE p.playlist_id IS NULL;
SELECT count(*) AS playlist_tracks_sem_track
FROM spotify.playlist_tracks pt LEFT JOIN spotify.tracks t USING (track_id) WHERE t.track_id IS NULL;
SELECT count(*) AS user_top_tracks_sem_track
FROM spotify.user_top_tracks ut LEFT JOIN spotify.tracks t USING (track_id) WHERE t.track_id IS NULL;
SELECT count(*) AS user_top_artists_sem_artist
FROM spotify.user_top_artists ua LEFT JOIN spotify.artists a USING (artist_id) WHERE a.artist_id IS NULL;
SELECT count(*) AS user_recently_played_sem_track
FROM spotify.user_recently_played ur LEFT JOIN spotify.tracks t USING (track_id) WHERE t.track_id IS NULL;
SELECT count(*) AS track_metrics_sem_track
FROM spotify.track_metrics tm LEFT JOIN spotify.tracks t USING (track_id) WHERE t.track_id IS NULL;
