import logging
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ingestion.spotify_client import SpotifyClient

logger = logging.getLogger("wait_and_run")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
POLL_MINUTES = 15
DEFAULT_RETRY_AFTER = 18 * 3600
CHECK_ARTIST = "Emicida"


def _retry_after_from(exc):
    try:
        headers = getattr(exc, "headers", None) or {}
        return int(headers.get("Retry-After"))
    except (TypeError, ValueError):
        return None


def probe():
    client = SpotifyClient()
    artist = client.search_artist(CHECK_ARTIST)
    client.artist_albums(artist["id"])


def run_pipeline():
    logger.info("Executando o pipeline completo...")
    return subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "src" / "run_pipeline.py")],
        cwd=PROJECT_ROOT,
    ).returncode


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    target = time.time() + DEFAULT_RETRY_AFTER
    logger.info(
        "Rate limit estimado até %s (UTC). Aguardando sem consumir cota...",
        datetime.fromtimestamp(target, tz=timezone.utc).isoformat(),
    )
    while True:
        remaining = target - time.time()
        if remaining > 0:
            nap = min(POLL_MINUTES * 60, remaining)
            logger.info("Dormindo %.0f min", nap / 60)
            time.sleep(nap)
            continue
        result = run_pipeline()
        if result == 0:
            logger.info("Pipeline finalizado com sucesso")
            return 0
        logger.warning("Pipeline falhou (exit %d). Verificando novo rate limit...", result)
        try:
            probe()
            logger.warning("Probe OK após falha do pipeline; nova tentativa em %d min", POLL_MINUTES)
            target = time.time() + POLL_MINUTES * 60
        except Exception as exc:
            wait = _retry_after_from(exc) or DEFAULT_RETRY_AFTER
            target = time.time() + wait
            logger.warning(
                "API ainda bloqueada (%s). Nova janela até %s (UTC)",
                type(exc).__name__,
                datetime.fromtimestamp(target, tz=timezone.utc).isoformat(),
            )


if __name__ == "__main__":
    sys.exit(main())
