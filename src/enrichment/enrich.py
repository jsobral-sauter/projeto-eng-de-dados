import json
import logging
import os
import time
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_PATH = PROJECT_ROOT / "data" / "enrichment_cache.json"

# Tags comuns no Last.fm que não representam gênero musical
NON_GENRE_TAGS = {
    "seen live", "favourites", "favorite", "favorites", "albums i own",
    "my favorites", "all", "00s", "90s", "80s", "70s", "60s", "50s",
    "2010s", "2020s", "under 2000 listeners", "best of 2010", "best of 2011",
    "best of 2012", "best of 2013", "best of 2014", "best of 2015",
    "best of 2016", "best of 2017", "best of 2018", "best of 2019",
    "best of 2020", "best of 2021", "best of 2022", "best of 2023",
    "best of 2024", "best of 2025", "best of 2026",
}


def _clean_tags(tags, limit):
    cleaned = []
    seen = set()
    for tag in tags:
        tag = tag.strip().lower()
        if not tag or tag in NON_GENRE_TAGS or tag in seen:
            continue
        seen.add(tag)
        cleaned.append(tag)
        if len(cleaned) >= limit:
            break
    return cleaned


class LastFMClient:
    """Cliente da API pública do Last.fm (requer api_key)."""

    BASE = "https://ws.audioscrobbler.com/2.0/"

    def __init__(self, api_key, interval=0.25, timeout=15):
        self.api_key = api_key
        self.interval = interval
        self.timeout = timeout

    def _get(self, method, **params):
        payload = {"method": method, "api_key": self.api_key, "format": "json", **params}
        try:
            resp = requests.get(self.BASE, params=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (requests.exceptions.RequestException, ValueError):
            return None
        if data.get("error"):
            return None
        return data

    def artist_top_tags(self, name, limit=10):
        data = self._get("artist.gettoptags", artist=name)
        if not data:
            return None
        tags = [t["name"] for t in data.get("toptags", {}).get("tag", [])]
        return _clean_tags(tags, limit)

    def track_info(self, artist, track, limit=10):
        data = self._get("track.getinfo", artist=artist, track=track)
        if not data or not data.get("track"):
            return None
        t = data["track"]
        playcount = t.get("playcount")
        listeners = t.get("listeners")
        tags = _clean_tags([tag["name"] for tag in t.get("toptags", {}).get("tag", [])], limit)
        return {
            "playcount": int(playcount) if playcount and playcount.isdigit() else None,
            "listeners": int(listeners) if listeners and listeners.isdigit() else None,
            "tags": tags,
        }


class MusicBrainzClient:
    """Cliente da API do MusicBrainz (sem chave; gêneros de artistas)."""

    BASE = "https://musicbrainz.org/ws/2/artist"

    def __init__(self, interval=1.1, timeout=20, user_agent="spotify-etl/1.0 (projeto-eng-dados)"):
        self.interval = interval
        self.timeout = timeout
        self.user_agent = user_agent

    def artist_top_tags(self, name, limit=10):
        try:
            resp = requests.get(
                self.BASE,
                params={"query": f'artist:"{name}"', "fmt": "json"},
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException:
            return None
        artists = resp.json().get("artists") or []
        if not artists:
            return None
        tags = [t["name"] for t in artists[0].get("tags", [])]
        return _clean_tags(tags, limit)


class Enricher:
    """Enriquece artistas (gêneros) e tracks (métricas) com cache local.

    O cache (data/enrichment_cache.json) evita refazer chamadas a cada execução:
    só busca o que ainda não foi resolvido.
    """

    def __init__(self, provider="lastfm", api_key=None, max_artists=200, max_tracks=300,
                 request_interval=None, genres_per_artist=10, cache_path=None):
        self.provider = provider
        self.max_artists = max_artists
        self.max_tracks = max_tracks
        self.genres_per_artist = genres_per_artist
        self.cache_path = Path(cache_path) if cache_path else CACHE_PATH
        self.supports_track_metrics = provider == "lastfm"
        if provider == "lastfm":
            self.client = LastFMClient(api_key, interval=request_interval or 0.25)
        else:
            self.client = MusicBrainzClient(interval=request_interval or 1.1)
        self.cache = self._load_cache()
        self.cache.setdefault("artists", {})
        self.cache.setdefault("tracks", {})
        self._artist_calls = 0
        self._track_calls = 0

    def _load_cache(self):
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def save_cache(self):
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.warning("Não foi possível salvar o cache de enriquecimento: %s", exc)

    def enrich_artists(self, artists):
        """Adiciona artist['genres'] (cache ou API)."""
        for artist in artists:
            if self._artist_calls >= self.max_artists:
                break
            aid = artist.get("id")
            if not aid:
                continue
            cached = self.cache["artists"].get(aid)
            if cached is not None:
                artist["genres"] = cached
                continue
            genres = self.client.artist_top_tags(artist.get("name", ""), self.genres_per_artist)
            self._artist_calls += 1
            time.sleep(self.client.interval)
            if genres:
                artist["genres"] = genres
                self.cache["artists"][aid] = genres
            else:
                artist["genres"] = []
                self.cache["artists"][aid] = []  # miss cacheado: não refazer
            if self._artist_calls % 200 == 0:
                self.save_cache()
        logger.info("Enriquecimento de artistas (%s): %d chamadas", self.provider, self._artist_calls)

    def enrich_tracks(self, track_list):
        """Retorna métricas das tracks (playcount/listeners/tags) — só Last.fm."""
        if not self.supports_track_metrics:
            logger.info("Provider %s não fornece métricas de tracks; pulando", self.provider)
            return []
        metrics = []
        for track in track_list:
            if self._track_calls >= self.max_tracks:
                break
            tid = track.get("id")
            if not tid:
                continue
            cached = self.cache["tracks"].get(tid)
            if cached is not None:
                if cached.get("playcount") is not None:
                    metrics.append(self._metric(track, cached))
                continue
            primary = (track.get("artists") or [{}])[0]
            info = self.client.track_info(primary.get("name"), track.get("name", ""))
            self._track_calls += 1
            time.sleep(self.client.interval)
            if info:
                self.cache["tracks"][tid] = info
                metrics.append(self._metric(track, info))
            else:
                self.cache["tracks"][tid] = {"playcount": None}  # miss cacheado: não refazer
            if self._track_calls % 200 == 0:
                self.save_cache()
        logger.info("Enriquecimento de tracks (%s): %d chamadas, %d com métricas",
                    self.provider, self._track_calls, len(metrics))
        return metrics

    @staticmethod
    def _metric(track, info):
        primary = (track.get("artists") or [{}])[0]
        return {
            "track_spotify_id": track["id"],
            "track_name": track.get("name"),
            "artist_name": primary.get("name"),
            "playcount": info.get("playcount"),
            "listeners": info.get("listeners"),
            "tags": info.get("tags") or [],
        }


def build_enricher(config):
    conf = config or {}
    api_key = os.getenv("LASTFM_API_KEY") or ""
    provider = conf.get("provider", "lastfm")
    if provider == "lastfm" and not api_key:
        logger.info("Sem LASTFM_API_KEY — usando MusicBrainz (apenas gêneros de artistas)")
        provider = "musicbrainz"
    return Enricher(
        provider=provider,
        api_key=api_key,
        max_artists=int(conf.get("max_artists", 200) or 200),
        max_tracks=int(conf.get("max_tracks", 300) or 300),
        request_interval=conf.get("request_interval"),
        genres_per_artist=int(conf.get("genres_per_artist", 10) or 10),
    )


def enrich_payload(data, config_path=None):
    """Enriquece o payload in-place: artist['genres'] e data['track_metrics']."""
    path = Path(config_path) if config_path else PROJECT_ROOT / "config.yaml"
    try:
        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except OSError:
        config = {}
    en_conf = config.get("enrichment") or {}
    if not en_conf.get("enabled", True):
        logger.info("Enriquecimento desabilitado no config")
        return data
    load_dotenv()
    enricher = build_enricher(en_conf)
    enricher.enrich_artists(data.get("artists", []))
    data["track_metrics"] = enricher.enrich_tracks(_priority_tracks(data))
    enricher.save_cache()
    return data


def _priority_tracks(data):
    """Ordena tracks: top do usuário → recently played → playlists → demais."""
    tracks = {t["id"]: t for t in data.get("tracks", [])}
    ordered = []
    for item in data.get("user_top_tracks", []):
        t = item.get("track")
        if t and t.get("id") in tracks and t["id"] not in ordered:
            ordered.append(t["id"])
    for item in data.get("user_recently_played", []):
        t = item.get("track")
        if t and t.get("id") in tracks and t["id"] not in ordered:
            ordered.append(t["id"])
    for pt in data.get("playlist_tracks", []):
        t = pt.get("track")
        if t and t.get("id") in tracks and t["id"] not in ordered:
            ordered.append(t["id"])
    ordered += [tid for tid in tracks if tid not in ordered]
    return [tracks[tid] for tid in ordered]
