CREATE INDEX idx_tracks_album_id          ON spotify.tracks(album_id);
CREATE INDEX idx_playlist_tracks_track_id ON spotify.playlist_tracks(track_id);
CREATE INDEX idx_track_artists_artist_id  ON spotify.track_artists(artist_id);
CREATE INDEX idx_album_artists_artist_id  ON spotify.album_artists(artist_id);
CREATE INDEX idx_artist_genres_genre_id   ON spotify.artist_genres(genre_id);
CREATE INDEX idx_user_top_tracks_track_id    ON spotify.user_top_tracks(track_id);
CREATE INDEX idx_user_top_artists_artist_id  ON spotify.user_top_artists(artist_id);
CREATE INDEX idx_user_recently_played_track_id ON spotify.user_recently_played(track_id);
