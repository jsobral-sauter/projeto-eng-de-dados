import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ingestion.spotify_client import SpotifyClient

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BRONZE_DIR = PROJECT_ROOT / "data" / "bronze"

AUDIO_FEATURE_KEYS = [
    "danceability", "energy", "key", "loudness", "mode", "speechiness",
    "acousticness", "instrumentalness", "liveness", "valence", "tempo",
    "time_signature",
]


class SpotifyExtractor:
    """Coleta dados públicos do Spotify e grava a camada bronze local.

    Bronze = dado como veio da API, append-only, particionado por data:
        data/bronze/YYYY-MM-DD/spotify_raw.json
    """

    def __init__(self, config_path=None):
        self.config_path = Path(config_path) if config_path else PROJECT_ROOT / "config.yaml"
        self.client = SpotifyClient()

    def _load_config(self):
        with open(self.config_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _paginate(self, results):
        while True:
            yield results
            if not results.get("next"):
                break
            results = self.client.next_page(results)

    def run(self):
        config = self._load_config()
        artists = {}   # spotify_id -> dict cru da API
        albums = {}    # spotify_id -> dict cru da API
        tracks = {}    # spotify_id -> dict cru da API
        track_albums = {}  # track_id -> album_id (a API não devolve o álbum dentro da track)
        audio_features = []
        playlists = []
        playlist_tracks = []

        # 1) Artistas da lista fixa do config
        for name in config["artists"]:
            hit = self.client.search_artist(name)
            if hit is None:
                logger.warning("Artista não encontrado na API: %s", name)
                continue
            artist = self.client.artist(hit["id"])
            artists[artist["id"]] = artist
            logger.info("Artista: %s", artist["name"])
            self._collect_artist_albums(artist["id"], artists, albums, tracks, track_albums)

        # 2) Playlists públicas do config
        for pl in config.get("playlists", []):
            playlist_id = pl["id"]
            try:
                playlist = self.client.playlist(playlist_id)
            except Exception:
                logger.warning("Playlist indisponível, pulando: %s", playlist_id)
                continue
            playlists.append(playlist)
            try:
                items = self.client.playlist_items(playlist_id)
            except Exception as exc:
                logger.warning(
                    "Itens da playlist %s indisponíveis (%s): o endpoint exige OAuth de usuário. "
                    "Somente os metadados da playlist serão carregados.",
                    playlist_id, type(exc).__name__,
                )
                items = []
            for position, item in enumerate(items):
                track = item.get("track")
                if not track:
                    logger.warning("Track removida/nula na playlist %s (posição %d)", playlist_id, position)
                    continue
                playlist_tracks.append({
                    "playlist_spotify_id": playlist_id,
                    "position": position,
                    "added_at": item.get("added_at"),
                    "track": track,
                })
                self._register_track_context(track, artists, albums, tracks, track_albums)
            logger.info("Playlist: %s (%d tracks)", playlist["name"], len(items))

        # 3) Audio features em lotes de 100 IDs por chamada
        # OBS: endpoint pode estar depreciado/indisponível — pipeline continua sem ele
        track_ids = list(tracks.keys())
        for i in range(0, len(track_ids), 100):
            batch = track_ids[i:i + 100]
            try:
                for feat in self.client.audio_features(batch):
                    if feat is not None:
                        audio_features.append(feat)
            except Exception as exc:
                logger.warning("Endpoint audio-features indisponível (%s); audio_features ficará vazio", type(exc).__name__)
                break
        logger.info("Audio features obtidas: %d/%d", len(audio_features), len(track_ids))

        payload = {
            "_ingestion_timestamp": datetime.now(timezone.utc).isoformat(),
            "artists": list(artists.values()),
            "albums": [self._without_tracks(a) for a in albums.values()],
            "tracks": list(tracks.values()),
            "track_albums": track_albums,
            "audio_features": audio_features,
            "playlists": playlists,
            "playlist_tracks": playlist_tracks,
        }
        self._save_bronze(payload)
        return payload

    def _collect_artist_albums(self, artist_id, artists, albums, tracks, track_albums):
        first_page = self.client.artist_albums(artist_id)
        for page in self._paginate(first_page):
            for alb in page["items"]:
                if alb["id"] in albums:
                    continue
                full = self.client.album(alb["id"])
                albums[full["id"]] = full
                for a in full.get("artists", []):
                    artists.setdefault(a["id"], a)
                tracks_page = full["tracks"]
                while True:
                    for t in tracks_page["items"]:
                        tracks[t["id"]] = t
                        track_albums[t["id"]] = full["id"]
                    if not tracks_page.get("next"):
                        break
                    tracks_page = self.client.next_page(tracks_page)

    @staticmethod
    def _register_track_context(track, artists, albums, tracks, track_albums):
        """Registra artistas/álbum que apareceram via playlist (objetos simplificados)."""
        tracks[track["id"]] = track
        album = track.get("album")
        if album:
            albums[album["id"]] = album
            track_albums[track["id"]] = album["id"]
            for a in album.get("artists", []):
                artists.setdefault(a["id"], a)
        for a in track.get("artists", []):
            artists.setdefault(a["id"], a)

    @staticmethod
    def _without_tracks(album):
        # tracks já são extraídas à parte; evita duplicação no arquivo bronze
        return {k: v for k, v in album.items() if k != "tracks"}

    def _save_bronze(self, payload):
        ingestion_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        out_dir = BRONZE_DIR / ingestion_day
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "spotify_raw.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.info("Bronze gravado em %s", out_file)
        return out_file
