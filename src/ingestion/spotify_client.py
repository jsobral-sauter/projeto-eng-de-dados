import logging
import os
import time

import requests
import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyClientCredentials

from ingestion.oauth import build_user_client

logger = logging.getLogger(__name__)

MAX_RETRIES = 5


class SpotifyClient:
    """Wrapper do Spotipy: autenticação (client credentials + OAuth opcional) e retry."""

    def __init__(self):
        load_dotenv()
        credentials = SpotifyClientCredentials(
            client_id=os.getenv("SPOTIFY_CLIENT_ID"),
            client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        )
        self._sp = spotipy.Spotify(client_credentials_manager=credentials, requests_timeout=30)
        self._sp_user = None
        self.user_id = None
        self._init_user_client()
        logger.info("Cliente Spotify autenticado (client credentials)")

    def _init_user_client(self):
        self._sp_user = build_user_client()
        if self._sp_user is None:
            return
        try:
            me = self._safe_call(self._sp_user.me)
            self.user_id = me.get("id")
            logger.info("Cliente de usuário autenticado: %s", me.get("display_name"))
        except Exception as exc:
            logger.warning("Falha ao obter perfil do usuário (%s) — dados pessoais indisponíveis", type(exc).__name__)
            self._sp_user = None
            self.user_id = None

    def user_available(self):
        return self._sp_user is not None

    def _safe_call(self, fn, *args, **kwargs):
        """Executa a chamada com retry em erros retryable.

        - 429 (rate limit): respeita o header Retry-After da API;
          se ausente, aplica backoff exponencial (2, 4, 8, 16, 32, 60s).
        - 5xx e falhas de rede (timeout/conexão): backoff exponencial.
        """
        retries = 0
        while True:
            try:
                return fn(*args, **kwargs)
            except spotipy.SpotifyException as exc:
                status = exc.http_status or 0
                retryable = status == 429 or 500 <= status < 600
                if not retryable or retries >= MAX_RETRIES:
                    raise
                retries += 1
                wait = self._backoff(exc.headers, retries)
                logger.warning("HTTP %s — retry %d/%d, aguardando %ds", status, retries, MAX_RETRIES, wait)
                time.sleep(wait)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                if retries >= MAX_RETRIES:
                    raise
                retries += 1
                wait = min(2 ** retries, 60)
                logger.warning("%s — retry %d/%d, aguardando %ds", type(exc).__name__, retries, MAX_RETRIES, wait)
                time.sleep(wait)

    @staticmethod
    def _backoff(headers, retries):
        retry_after = (headers or {}).get("Retry-After")
        if retry_after is not None:
            try:
                return min(int(retry_after), 60)
            except ValueError:
                pass
        return min(2 ** retries, 60)

    def search_artist(self, name):
        results = self._safe_call(self._sp.search, q=name, type="artist", limit=1)
        items = results.get("artists", {}).get("items") or []
        return items[0] if items else None

    def search_track(self, name, artist=None):
        query = f"track:{name}"
        if artist:
            query += f" artist:{artist}"
        results = self._safe_call(self._sp.search, q=query, type="track", limit=1)
        items = results.get("tracks", {}).get("items") or []
        return items[0] if items else None

    def artist(self, artist_id):
        return self._safe_call(self._sp.artist, artist_id)

    def artist_albums(self, artist_id):
        return self._safe_call(
            self._sp.artist_albums, artist_id,
            album_type="album,single", country="BR", limit=10, offset=0,
        )

    def album(self, album_id):
        return self._safe_call(self._sp.album, album_id)

    def next_page(self, results, user=False):
        sp = self._sp_user if user else self._sp
        return self._safe_call(sp.next, results)

    def playlist(self, playlist_id):
        return self._safe_call(self._sp.playlist, playlist_id)

    def playlist_items(self, playlist_id, user=False):
        sp = self._sp_user if user else self._sp
        items = []
        results = self._safe_call(sp.playlist_items, playlist_id, limit=50, offset=0)
        while True:
            items.extend(results["items"])
            if not results.get("next"):
                break
            results = self._safe_call(sp.next, results)
        return items

    # ---------- dados do usuário (exigem OAuth Authorization Code) ----------

    def current_user_playlists(self):
        items = []
        results = self._safe_call(self._sp_user.current_user_playlists, limit=50, offset=0)
        while True:
            items.extend(results["items"])
            if not results.get("next"):
                break
            results = self.next_page(results, user=True)
        return items

    def owned_or_collaborated_playlists(self):
        """Playlists cujo conteúdo a API devolve: dono do app ou colaborador."""
        return [
            p for p in self.current_user_playlists()
            if (p.get("owner") or {}).get("id") == self.user_id or p.get("collaborative")
        ]

    def current_user_top_tracks(self, time_range="medium_term", limit=50):
        return self._safe_call(self._sp_user.current_user_top_tracks, limit=limit, time_range=time_range)

    def current_user_top_artists(self, time_range="medium_term", limit=50):
        return self._safe_call(self._sp_user.current_user_top_artists, limit=limit, time_range=time_range)

    def current_user_recently_played(self, after=None, limit=50):
        return self._safe_call(self._sp_user.current_user_recently_played, limit=limit, after=after)
