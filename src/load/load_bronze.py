import logging
import os
from datetime import datetime

import psycopg
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class BronzeLoader:
    """Grava os dados crus (estruturados) na camada bronze do PostgreSQL.

    Histórico append-only por execução + idempotência: rodar o pipeline de
    novo para o mesmo ingestion_timestamp não duplica registros (DELETE do
    snapshot antes do INSERT). Sempre em uma única transação.
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
        logger.info("Conectado ao PostgreSQL %s:%s/%s (bronze)",
                    os.getenv("POSTGRES_HOST", "localhost"),
                    os.getenv("POSTGRES_PORT", "5432"),
                    os.getenv("POSTGRES_DB", "spotify"))

    def close(self):
        self.conn.close()

    def load(self, data):
        ingested_at = self._ingestion_time(data)
        with self.conn.transaction():
            self._load_artists(data["artists"], ingested_at)
            self._load_albums(data["albums"], ingested_at)
            self._load_tracks(data, ingested_at)
            self._load_playlists(data["playlists"], ingested_at)
            self._load_playlist_tracks(data["playlist_tracks"], ingested_at)
            self._load_user_top_tracks(data.get("user_top_tracks", []), ingested_at)
            self._load_user_top_artists(data.get("user_top_artists", []), ingested_at)
            self._load_user_recently_played(data.get("user_recently_played", []), ingested_at)
            self._load_track_metrics(data.get("track_metrics", []), ingested_at)

    @staticmethod
    def _ingestion_time(data):
        raw = data.get("_ingestion_timestamp")
        if raw:
            try:
                return datetime.fromisoformat(raw)
            except ValueError:
                pass
        return datetime.now()

    @staticmethod
    def _executemany(cur, query, rows):
        if rows:
            cur.executemany(query, rows)
        return len(rows)

    @staticmethod
    def _delete_snapshot(cur, table, ingested_at):
        """Remove registros do mesmo run antes do INSERT (idempotência).

        Executar o pipeline de novo para o mesmo ingestion_timestamp não
        duplica registros na partição; execuções diferentes continuam
        append-only (histórico preservado).
        """
        cur.execute(f"DELETE FROM bronze.{table} WHERE ingestion_timestamp = %s", (ingested_at,))

    def _load_artists(self, artists, ingested_at):
        rows = []
        for a in artists:
            images = a.get("images") or []
            rows.append((
                a["id"], a["name"],
                images[0]["url"] if images else None,
                (a.get("external_urls") or {}).get("spotify"),
                a.get("genres") or [],
                ingested_at,
            ))
        with self.conn.cursor() as cur:
            self._delete_snapshot(cur, "artists_raw", ingested_at)
            self._executemany(cur, """
                INSERT INTO bronze.artists_raw
                    (spotify_id, name, image_url, external_url, genres, ingestion_timestamp)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, rows)
        logger.info("bronze.artists_raw: %d", len(rows))

    def _load_albums(self, albums, ingested_at):
        rows = []
        for a in albums:
            copyrights = a.get("copyrights") or []
            rows.append((
                a["id"], a["name"],
                a.get("album_type"),
                a.get("release_date"),
                a.get("total_tracks"),
                [c["text"] for c in copyrights if c.get("text")],
                [art["id"] for art in a.get("artists", [])],
                a.get("genres") or [],
                ingested_at,
            ))
        with self.conn.cursor() as cur:
            self._delete_snapshot(cur, "albums_raw", ingested_at)
            self._executemany(cur, """
                INSERT INTO bronze.albums_raw
                    (spotify_id, name, album_type, release_date, total_tracks, copyright, artist_ids, genres, ingestion_timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, rows)
        logger.info("bronze.albums_raw: %d", len(rows))

    def _load_tracks(self, data, ingested_at):
        track_albums = data.get("track_albums", {})
        rows = []
        for t in data["tracks"]:
            album_ref = track_albums.get(t["id"]) or (t.get("album") or {}).get("id")
            rows.append((
                t["id"], t["name"],
                t.get("duration_ms"),
                t.get("track_number"),
                t.get("explicit", False),
                album_ref,
                [art["id"] for art in t.get("artists", [])],
                ingested_at,
            ))
        with self.conn.cursor() as cur:
            self._delete_snapshot(cur, "tracks_raw", ingested_at)
            self._executemany(cur, """
                INSERT INTO bronze.tracks_raw
                    (spotify_id, name, duration_ms, track_number, explicit, album_id, artist_ids, ingestion_timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, rows)
        logger.info("bronze.tracks_raw: %d", len(rows))

    def _load_playlists(self, playlists, ingested_at):
        rows = []
        for p in playlists:
            rows.append((
                p["id"], p["name"],
                p.get("description"),
                (p.get("followers") or {}).get("total") or 0,
                ingested_at,
            ))
        with self.conn.cursor() as cur:
            self._delete_snapshot(cur, "playlists_raw", ingested_at)
            self._executemany(cur, """
                INSERT INTO bronze.playlists_raw
                    (spotify_id, name, description, followers, ingestion_timestamp)
                VALUES (%s, %s, %s, %s, %s)
            """, rows)
        logger.info("bronze.playlists_raw: %d", len(rows))

    def _load_playlist_tracks(self, playlist_tracks, ingested_at):
        rows = []
        for pt in playlist_tracks:
            track = pt.get("track")
            added_at = pt.get("added_at")
            if isinstance(added_at, str):
                try:
                    added_at = datetime.fromisoformat(added_at)
                except ValueError:
                    added_at = None
            rows.append((
                pt["playlist_spotify_id"],
                track["id"] if track else None,
                pt.get("position"),
                added_at,
                ingested_at,
            ))
        with self.conn.cursor() as cur:
            self._delete_snapshot(cur, "playlist_tracks_raw", ingested_at)
            self._executemany(cur, """
                INSERT INTO bronze.playlist_tracks_raw
                    (playlist_spotify_id, track_spotify_id, position, added_at, ingestion_timestamp)
                VALUES (%s, %s, %s, %s, %s)
            """, rows)
        logger.info("bronze.playlist_tracks_raw: %d", len(rows))

    def _load_user_top_tracks(self, user_top_tracks, ingested_at):
        rows = []
        for item in user_top_tracks:
            track = item.get("track")
            rows.append((
                ingested_at, item["time_range"], item["rank"],
                track["id"] if track else None,
                ingested_at,
            ))
        with self.conn.cursor() as cur:
            self._delete_snapshot(cur, "user_top_tracks_raw", ingested_at)
            self._executemany(cur, """
                INSERT INTO bronze.user_top_tracks_raw
                    (snapshot_at, time_range, rank, track_spotify_id, ingestion_timestamp)
                VALUES (%s, %s, %s, %s, %s)
            """, rows)
        logger.info("bronze.user_top_tracks_raw: %d", len(rows))

    def _load_user_top_artists(self, user_top_artists, ingested_at):
        rows = []
        for item in user_top_artists:
            artist = item.get("artist")
            rows.append((
                ingested_at, item["time_range"], item["rank"],
                artist["id"] if artist else None,
                ingested_at,
            ))
        with self.conn.cursor() as cur:
            self._delete_snapshot(cur, "user_top_artists_raw", ingested_at)
            self._executemany(cur, """
                INSERT INTO bronze.user_top_artists_raw
                    (snapshot_at, time_range, rank, artist_spotify_id, ingestion_timestamp)
                VALUES (%s, %s, %s, %s, %s)
            """, rows)
        logger.info("bronze.user_top_artists_raw: %d", len(rows))

    def _load_user_recently_played(self, user_recently_played, ingested_at):
        rows = []
        for item in user_recently_played:
            track = item.get("track")
            played_at = item.get("played_at")
            if isinstance(played_at, str):
                try:
                    played_at = datetime.fromisoformat(played_at.replace("Z", "+00:00"))
                except ValueError:
                    played_at = None
            rows.append((
                played_at,
                track["id"] if track else None,
                ingested_at,
            ))
        with self.conn.cursor() as cur:
            self._delete_snapshot(cur, "user_recently_played_raw", ingested_at)
            self._executemany(cur, """
                INSERT INTO bronze.user_recently_played_raw
                    (played_at, track_spotify_id, ingestion_timestamp)
                VALUES (%s, %s, %s)
            """, rows)
        logger.info("bronze.user_recently_played_raw: %d", len(rows))

    def _load_track_metrics(self, track_metrics, ingested_at):
        rows = []
        for m in track_metrics:
            rows.append((
                m["track_spotify_id"],
                m.get("track_name"),
                m.get("artist_name"),
                m.get("playcount"),
                m.get("listeners"),
                m.get("tags") or [],
                ingested_at,
            ))
        with self.conn.cursor() as cur:
            self._delete_snapshot(cur, "track_metrics_raw", ingested_at)
            self._executemany(cur, """
                INSERT INTO bronze.track_metrics_raw
                    (track_spotify_id, track_name, artist_name, playcount, listeners, tags, ingestion_timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, rows)
        logger.info("bronze.track_metrics_raw: %d", len(rows))
