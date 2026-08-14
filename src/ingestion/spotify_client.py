import logging
import os
import time

import requests
import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyClientCredentials

logger = logging.getLogger(__name__)

MAX_RETRIES = 5


class SpotifyClient:
    """Wrapper do Spotipy: autenticação (client credentials) + retry em 429/5xx."""

    def __init__(self):
        load_dotenv()
        credentials = SpotifyClientCredentials(
            client_id=os.getenv("SPOTIFY_CLIENT_ID"),
            client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        )
        self._sp = spotipy.Spotify(client_credentials_manager=credentials, requests_timeout=30)
        logger.info("Cliente Spotify autenticado (client credentials)")

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

    def artist(self, artist_id):
        return self._safe_call(self._sp.artist, artist_id)

    def artist_albums(self, artist_id):
        return self._safe_call(
            self._sp.artist_albums, artist_id,
            album_type="album,single", country="BR", limit=10, offset=0,
        )

    def album(self, album_id):
        return self._safe_call(self._sp.album, album_id)

    def next_page(self, results):
        return self._safe_call(self._sp.next, results)

    def audio_features(self, track_ids):
        return self._safe_call(self._sp.audio_features, track_ids)

    def playlist(self, playlist_id):
        return self._safe_call(self._sp.playlist, playlist_id)

    def playlist_items(self, playlist_id):
        items = []
        results = self._safe_call(self._sp.playlist_items, playlist_id, limit=10, offset=0)
        while True:
            items.extend(results["items"])
            if not results.get("next"):
                break
            results = self.next_page(results)
        return items
