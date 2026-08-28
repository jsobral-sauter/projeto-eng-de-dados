import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ingestion.spotify_client import SpotifyClient

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LANDING_DIR = PROJECT_ROOT / "data" / "landing"


class SpotifyExtractor:
    """Coleta dados do Spotify e grava a camada Landing (raw).

    Landing = dado como veio da API, snapshot por partição diária:
        data/landing/YYYY-MM-DD/spotify_raw.json
    O caminho é determinístico por dia: rodar de novo sobrescreve o mesmo
    arquivo (idempotência por partição, sem duplicar arquivos).
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
        max_album_pages = int(config.get("max_album_pages", 3) or 0)
        artists = {}   # spotify_id -> dict cru da API
        albums = {}    # spotify_id -> dict cru da API
        tracks = {}    # spotify_id -> dict cru da API
        track_albums = {}  # track_id -> album_id (a API não devolve o álbum dentro da track)
        playlists = []
        playlist_tracks = []
        user_top_tracks = []
        user_top_artists = []
        user_recently_played = []

        # 1) Artistas da lista fixa do config
        for name in config["artists"]:
            hit = self.client.search_artist(name)
            if hit is None:
                logger.warning("Artista não encontrado na API: %s", name)
                continue
            artist = self.client.artist(hit["id"])
            artists[artist["id"]] = artist
            logger.info("Artista: %s", artist["name"])
            self._collect_artist_albums(artist["id"], artists, albums, tracks, track_albums, max_album_pages)

        # 2) Músicas específicas do config (busca por nome + artista opcional)
        for spec in config.get("tracks", []):
            name = spec["name"]
            artist = spec.get("artist")
            hit = self.client.search_track(name, artist)
            if hit is None:
                logger.warning("Música não encontrada na API: %s (artista: %s)", name, artist or "-")
                continue
            self._register_track_context(hit, artists, albums, tracks, track_albums)
            logger.info(
                "Música: %s — %s",
                hit["name"], ", ".join(a["name"] for a in hit.get("artists", [])),
            )

        # 3) Playlists públicas do config (apenas metadados — conteúdo exige OAuth + posse)
        playlist_ids = set()
        for pl in config.get("playlists", []):
            playlist_id = pl["id"]
            try:
                playlist = self.client.playlist(playlist_id)
            except Exception:
                logger.warning("Playlist indisponível, pulando: %s", playlist_id)
                continue
            playlists.append(playlist)
            playlist_ids.add(playlist_id)
            try:
                items = self.client.playlist_items(playlist_id)
            except Exception as exc:
                logger.warning(
                    "Itens da playlist %s indisponíveis (%s): o endpoint exige OAuth de usuário "
                    "e playlist própria/colaborada. Somente os metadados serão carregados.",
                    playlist_id, type(exc).__name__,
                )
                items = []
            self._collect_playlist_items(playlist_id, items, playlist_tracks, artists, albums, tracks, track_albums)
            logger.info("Playlist: %s (%d tracks)", playlist["name"], len(items))

        # 4) Playlists próprias/colaboradas do usuário (OAuth) — conteúdo real
        if self.client.user_available():
            owned = self.client.owned_or_collaborated_playlists()
            for pl in owned:
                playlist_id = pl["id"]
                if playlist_id in playlist_ids:
                    continue
                playlists.append(pl)
                playlist_ids.add(playlist_id)
                try:
                    items = self.client.playlist_items(playlist_id, user=True)
                except Exception as exc:
                    logger.warning("Itens da playlist própria %s indisponíveis (%s)", playlist_id, type(exc).__name__)
                    items = []
                self._collect_playlist_items(playlist_id, items, playlist_tracks, artists, albums, tracks, track_albums)
                logger.info("Playlist do usuário: %s (%d tracks)", pl.get("name"), len(items))

            # 5) Top do usuário (artists + tracks) por período
            time_ranges = config.get("user_top_time_ranges", ["medium_term", "long_term"])
            for time_range in time_ranges:
                tracks_result = self.client.current_user_top_tracks(time_range=time_range)
                for rank, track in enumerate(tracks_result.get("items", []), start=1):
                    if not track.get("id"):
                        continue
                    user_top_tracks.append({"time_range": time_range, "rank": rank, "track": track})
                    self._register_track_context(track, artists, albums, tracks, track_albums)
                artists_result = self.client.current_user_top_artists(time_range=time_range)
                for rank, artist in enumerate(artists_result.get("items", []), start=1):
                    if not artist.get("id"):
                        continue
                    user_top_artists.append({"time_range": time_range, "rank": rank, "artist": artist})
                    artists.setdefault(artist["id"], artist)
                logger.info(
                    "Top do usuário (%s): %d tracks, %d artists",
                    time_range, len(tracks_result.get("items", [])), len(artists_result.get("items", [])),
                )

            # 6) Histórico recente de reprodução (janela fixa; dedup no banco)
            limit = int(config.get("user_recently_played_limit", 50) or 50)
            result = self.client.current_user_recently_played(limit=limit)
            for item in result.get("items", []):
                track = item.get("track")
                played_at = item.get("played_at")
                if not track or not track.get("id"):
                    continue
                user_recently_played.append({"played_at": played_at, "track": track})
                self._register_track_context(track, artists, albums, tracks, track_albums)
            logger.info("Recently played: %d reproduções na janela (limit=%d)", len(user_recently_played), limit)

        # 7) Grava o bronze
        payload = {
            "_ingestion_timestamp": datetime.now(timezone.utc).isoformat(),
            "artists": list(artists.values()),
            "albums": [self._without_tracks(a) for a in albums.values()],
            "tracks": list(tracks.values()),
            "track_albums": track_albums,
            "playlists": playlists,
            "playlist_tracks": playlist_tracks,
            "user_top_tracks": user_top_tracks,
            "user_top_artists": user_top_artists,
            "user_recently_played": user_recently_played,
        }
        self._save_landing(payload)
        return payload

    def collect_items(self, artist_names=None, track_specs=None, album_ids=None,
                      playlist_ids=None, max_pages=1):
        """Coleta itens específicos (sem ler config.yaml) e retorna o payload.

        Usado pela inserção rápida (src/quick_add.py). Não inclui dados pessoais
        (top/recently) — esses só vêm do pipeline completo (run()).
        """
        artists = {}
        albums = {}
        tracks = {}
        track_albums = {}
        playlists = []
        playlist_tracks = []

        for name in artist_names or []:
            hit = self.client.search_artist(name)
            if hit is None:
                logger.warning("Artista não encontrado na API: %s", name)
                continue
            artist = self.client.artist(hit["id"])
            artists[artist["id"]] = artist
            logger.info("Artista: %s", artist["name"])
            self._collect_artist_albums(artist["id"], artists, albums, tracks, track_albums, max_pages)

        for name, by in track_specs or []:
            hit = self.client.search_track(name, by)
            if hit is None:
                logger.warning("Música não encontrada na API: %s (artista: %s)", name, by or "-")
                continue
            self._register_track_context(hit, artists, albums, tracks, track_albums)
            logger.info(
                "Música: %s — %s",
                hit["name"], ", ".join(a["name"] for a in hit.get("artists", [])),
            )

        for album_id in album_ids or []:
            try:
                full = self.client.album(album_id)
            except Exception:
                logger.warning("Álbum indisponível na API: %s", album_id)
                continue
            if full.get("id") in albums:
                continue
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
            logger.info("Álbum: %s (%d tracks)", full.get("name"), full.get("total_tracks"))

        for playlist_id in playlist_ids or []:
            try:
                pl = self.client.playlist(playlist_id)
            except Exception:
                logger.warning("Playlist indisponível, pulando: %s", playlist_id)
                continue
            playlists.append(pl)
            items = []
            try:
                if self.client.user_available() and (
                    (pl.get("owner") or {}).get("id") == self.client.user_id or pl.get("collaborative")
                ):
                    items = self.client.playlist_items(playlist_id, user=True)
                else:
                    items = self.client.playlist_items(playlist_id)
            except Exception as exc:
                logger.warning(
                    "Itens da playlist %s indisponíveis (%s); apenas metadados.",
                    playlist_id, type(exc).__name__,
                )
            self._collect_playlist_items(playlist_id, items, playlist_tracks, artists, albums, tracks, track_albums)
            logger.info("Playlist: %s (%d tracks)", pl.get("name"), len(items))

        return {
            "_ingestion_timestamp": datetime.now(timezone.utc).isoformat(),
            "artists": list(artists.values()),
            "albums": [self._without_tracks(a) for a in albums.values()],
            "tracks": list(tracks.values()),
            "track_albums": track_albums,
            "playlists": playlists,
            "playlist_tracks": playlist_tracks,
            "user_top_tracks": [],
            "user_top_artists": [],
            "user_recently_played": [],
        }

    def _collect_artist_albums(self, artist_id, artists, albums, tracks, track_albums, max_pages=0):
        first_page = self.client.artist_albums(artist_id)
        for page_num, page in enumerate(self._paginate(first_page), start=1):
            if max_pages and page_num > max_pages:
                break
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

    def _collect_playlist_items(self, playlist_id, items, playlist_tracks, artists, albums, tracks, track_albums):
        for position, item in enumerate(items):
            # Campo da faixa: 'item' no endpoint novo (/playlists/{id}/items);
            # fallback 'track' para respostas antigas/legadas.
            track = item.get("item") or item.get("track")
            if not track:
                logger.warning("Track removida/nula na playlist %s (posição %d)", playlist_id, position)
                continue
            if track.get("type") and track["type"] != "track":
                continue
            if track.get("is_local") or not track.get("id"):
                continue
            playlist_tracks.append({
                "playlist_spotify_id": playlist_id,
                "position": position,
                "added_at": item.get("added_at"),
                "track": track,
            })
            self._register_track_context(track, artists, albums, tracks, track_albums)

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
        # tracks já são extraídas à parte; evita duplicação no payload
        return {k: v for k, v in album.items() if k != "tracks"}

    def _save_landing(self, payload, filename="spotify_raw.json"):
        ingestion_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        out_dir = LANDING_DIR / ingestion_day
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / filename
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.info("Landing gravado em %s", out_file)
        return out_file
