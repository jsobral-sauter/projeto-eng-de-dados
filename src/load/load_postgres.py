import logging
import os

import psycopg
from dotenv import load_dotenv
from psycopg import sql

logger = logging.getLogger(__name__)

AUDIO_FEATURE_KEYS = [
    "danceability", "energy", "key", "loudness", "mode", "speechiness",
    "acousticness", "instrumentalness", "liveness", "valence", "tempo",
    "time_signature",
]


class PostgresLoader:
    """Carrega o payload bronze no schema spotify com upserts idempotentes.

    Estratégias por tipo de tabela:
    - entidades: ON CONFLICT (spotify_id) DO UPDATE (+ updated_at = now())
    - genres:    ON CONFLICT (name) DO NOTHING
    - N:N:       ON CONFLICT (pk composta) DO NOTHING
    - playlist_tracks (PK surrogate): delete da snapshot + insert completo
    Toda a carga roda em uma única transação (tudo ou nada).
    """

    def __init__(self):
        load_dotenv()
        self.conn = psycopg.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            dbname=os.getenv("POSTGRES_DB", "spotify"),
            user=os.getenv("POSTGRES_USER", "admin"),
            password=os.getenv("POSTGRES_PASSWORD"),
        )
        logger.info("Conectado ao PostgreSQL %s:%s/%s",
                    os.getenv("POSTGRES_HOST", "localhost"),
                    os.getenv("POSTGRES_PORT", "5432"),
                    os.getenv("POSTGRES_DB", "spotify"))

    def close(self):
        self.conn.close()

    def load(self, data):
        with self.conn.transaction():
            genre_map = self._load_genres(data)
            artist_map = self._load_artists(data)
            self._load_artist_genres(data, artist_map, genre_map)
            album_map = self._load_albums(data)
            self._load_album_artists(data, album_map, artist_map)
            track_map = self._load_tracks(data, album_map)
            self._load_track_artists(data, track_map, artist_map)
            self._load_audio_features(data, track_map)
            playlist_map = self._load_playlists(data)
            self._load_playlist_tracks(data, playlist_map, track_map)

    def _id_map(self, table, id_col, key_col, keys):
        """Mapeia valor único (ex: spotify_id) -> PK local para resolver FKs."""
        if not keys:
            return {}
        query = sql.SQL("SELECT {}, {} FROM spotify.{} WHERE {} = ANY(%s)").format(
            sql.Identifier(id_col), sql.Identifier(key_col),
            sql.Identifier(table), sql.Identifier(key_col),
        )
        with self.conn.cursor() as cur:
            cur.execute(query, (list(keys),))
            return {k: pk for pk, k in cur.fetchall()}

    def _load_genres(self, data):
        names = sorted(
            {g for a in data["artists"] for g in a.get("genres", [])}
            | {g for a in data["albums"] for g in a.get("genres", [])}
        )
        if names:
            with self.conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO spotify.genres (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
                    [(n,) for n in names],
                )
            genre_map = self._id_map("genres", "genre_id", "name", names)
            logger.info("genres: %d", len(names))
            return genre_map
        return {}

    def _load_artists(self, data):
        rows = []
        for a in data["artists"]:
            images = a.get("images") or []
            rows.append((
                a["name"], a["id"],
                a.get("popularity"),
                (a.get("followers") or {}).get("total"),
                images[0]["url"] if images else None,
            ))
        if rows:
            with self.conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO spotify.artists (name, spotify_id, popularity, followers, image_url)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (spotify_id) DO UPDATE SET
                        name       = EXCLUDED.name,
                        popularity = COALESCE(EXCLUDED.popularity, spotify.artists.popularity),
                        followers  = COALESCE(EXCLUDED.followers, spotify.artists.followers),
                        image_url  = COALESCE(EXCLUDED.image_url, spotify.artists.image_url),
                        updated_at = now()
                    """,
                    rows,
                )
        artist_map = self._id_map("artists", "artist_id", "spotify_id", [a["id"] for a in data["artists"]])
        logger.info("artists: %d", len(rows))
        return artist_map

    def _load_artist_genres(self, data, artist_map, genre_map):
        rows = []
        for a in data["artists"]:
            artist_id = artist_map.get(a["id"])
            if not artist_id:
                continue
            for g in a.get("genres", []):
                genre_id = genre_map.get(g)
                if genre_id:
                    rows.append((artist_id, genre_id))
        if rows:
            with self.conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO spotify.artist_genres (artist_id, genre_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    rows,
                )
        logger.info("artist_genres: %d", len(rows))

    def _load_albums(self, data):
        rows = []
        skipped = 0
        for a in data["albums"]:
            release_date = a.get("release_date")
            if not release_date:
                skipped += 1
                continue
            copyrights = a.get("copyrights") or []
            rows.append((
                a["name"], a["id"],
                a.get("album_type"),
                release_date,
                a.get("total_tracks"),
                copyrights[0]["text"] if copyrights else None,
            ))
        if rows:
            with self.conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO spotify.albums (name, spotify_id, album_type, release_date, total_tracks, copyright)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (spotify_id) DO UPDATE SET
                        name         = EXCLUDED.name,
                        album_type   = COALESCE(EXCLUDED.album_type, spotify.albums.album_type),
                        release_date = EXCLUDED.release_date,
                        total_tracks = COALESCE(EXCLUDED.total_tracks, spotify.albums.total_tracks),
                        copyright    = COALESCE(EXCLUDED.copyright, spotify.albums.copyright),
                        updated_at   = now()
                    """,
                    rows,
                )
        if skipped:
            logger.warning("albums pulados (sem release_date): %d", skipped)
        album_map = self._id_map("albums", "album_id", "spotify_id", [a["id"] for a in data["albums"]])
        logger.info("albums: %d", len(rows))
        return album_map

    def _load_album_artists(self, data, album_map, artist_map):
        rows = []
        for a in data["albums"]:
            album_id = album_map.get(a["id"])
            if not album_id:
                continue
            for idx, art in enumerate(a.get("artists", [])):
                artist_id = artist_map.get(art["id"])
                if artist_id:
                    rows.append((album_id, artist_id, idx == 0))
        if rows:
            with self.conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO spotify.album_artists (album_id, artist_id, is_primary) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                    rows,
                )
        logger.info("album_artists: %d", len(rows))

    def _load_tracks(self, data, album_map):
        track_albums = data.get("track_albums", {})
        rows = []
        skipped = 0
        for t in data["tracks"]:
            album_ref = track_albums.get(t["id"]) or (t.get("album") or {}).get("id")
            album_id = album_map.get(album_ref) if album_ref else None
            if not album_id:
                skipped += 1
                continue
            rows.append((
                t["name"], t["id"],
                t.get("duration_ms"),
                t.get("track_number"),
                t.get("explicit", False),
                album_id,
            ))
        if rows:
            with self.conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO spotify.tracks (name, spotify_id, duration_ms, track_number, explicit, album_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (spotify_id) DO UPDATE SET
                        name         = EXCLUDED.name,
                        duration_ms  = EXCLUDED.duration_ms,
                        track_number = EXCLUDED.track_number,
                        explicit     = EXCLUDED.explicit,
                        album_id     = EXCLUDED.album_id,
                        updated_at   = now()
                    """,
                    rows,
                )
        if skipped:
            logger.warning("tracks puladas (álbum não mapeado): %d", skipped)
        track_map = self._id_map("tracks", "track_id", "spotify_id", [t["id"] for t in data["tracks"]])
        logger.info("tracks: %d", len(rows))
        return track_map

    def _load_track_artists(self, data, track_map, artist_map):
        rows = []
        for t in data["tracks"]:
            track_id = track_map.get(t["id"])
            if not track_id:
                continue
            for idx, art in enumerate(t.get("artists", [])):
                artist_id = artist_map.get(art["id"])
                if artist_id:
                    rows.append((track_id, artist_id, idx == 0))
        if rows:
            with self.conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO spotify.track_artists (track_id, artist_id, is_primary) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                    rows,
                )
        logger.info("track_artists: %d", len(rows))

    def _load_audio_features(self, data, track_map):
        rows = []
        for f in data["audio_features"]:
            track_id = track_map.get(f["id"])
            if not track_id:
                continue
            rows.append((track_id, *(f.get(k) for k in AUDIO_FEATURE_KEYS)))
        if rows:
            columns = ", ".join(AUDIO_FEATURE_KEYS)
            placeholders = ", ".join(["%s"] * (len(AUDIO_FEATURE_KEYS) + 1))
            updates = ", ".join(f"{k} = EXCLUDED.{k}" for k in AUDIO_FEATURE_KEYS)
            with self.conn.cursor() as cur:
                cur.executemany(
                    f"""
                    INSERT INTO spotify.audio_features (track_id, {columns})
                    VALUES ({placeholders})
                    ON CONFLICT (track_id) DO UPDATE SET
                        {updates},
                        updated_at = now()
                    """,
                    rows,
                )
        logger.info("audio_features: %d", len(rows))

    def _load_playlists(self, data):
        rows = []
        for p in data["playlists"]:
            rows.append((
                p["name"], p["id"],
                p.get("description"),
                (p.get("followers") or {}).get("total"),
            ))
        if rows:
            with self.conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO spotify.playlists (name, spotify_id, description, followers)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (spotify_id) DO UPDATE SET
                        name        = EXCLUDED.name,
                        description = COALESCE(EXCLUDED.description, spotify.playlists.description),
                        followers   = COALESCE(EXCLUDED.followers, spotify.playlists.followers),
                        updated_at  = now()
                    """,
                    rows,
                )
        playlist_map = self._id_map("playlists", "playlist_id", "spotify_id", [p["id"] for p in data["playlists"]])
        logger.info("playlists: %d", len(rows))
        return playlist_map

    def _load_playlist_tracks(self, data, playlist_map, track_map):
        by_playlist = {}
        for pt in data["playlist_tracks"]:
            playlist_id = playlist_map.get(pt["playlist_spotify_id"])
            track = pt.get("track")
            track_id = track_map.get(track["id"]) if track else None
            if not playlist_id or not track_id:
                continue
            by_playlist.setdefault(playlist_id, []).append(
                (playlist_id, track_id, pt["position"], pt["added_at"])
            )
        total = 0
        with self.conn.cursor() as cur:
            for playlist_id, rows in by_playlist.items():
                # PK surrogate: sem alvo para ON CONFLICT -> substitui a snapshot inteira
                cur.execute("DELETE FROM spotify.playlist_tracks WHERE playlist_id = %s", (playlist_id,))
                cur.executemany(
                    "INSERT INTO spotify.playlist_tracks (playlist_id, track_id, position, added_at) VALUES (%s, %s, %s, %s)",
                    rows,
                )
                total += len(rows)
        logger.info("playlist_tracks: %d", total)
