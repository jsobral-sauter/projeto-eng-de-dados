import logging
import sys
from datetime import datetime

from enrichment.enrich import enrich_payload
from ingestion.extract import SpotifyExtractor
from load.load_bronze import BronzeLoader
from load.load_postgres import PostgresLoader

logger = logging.getLogger("pipeline")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    start = datetime.now()
    logger.info("Início do pipeline")

    extractor = SpotifyExtractor()
    data = extractor.run()
    logger.info(
        "Extração concluída: %d artistas, %d álbuns, %d tracks, %d playlists, %d playlist_tracks, "
        "%d top_tracks, %d top_artists, %d recently_played",
        len(data["artists"]), len(data["albums"]), len(data["tracks"]),
        len(data["playlists"]), len(data["playlist_tracks"]),
        len(data.get("user_top_tracks", [])), len(data.get("user_top_artists", [])),
        len(data.get("user_recently_played", [])),
    )

    enrich_payload(data)
    logger.info(
        "Enriquecimento concluído: %d tracks com métricas",
        len(data.get("track_metrics", [])),
    )

    bronze_loader = BronzeLoader()
    try:
        bronze_loader.load(data)
    finally:
        bronze_loader.close()

    loader = PostgresLoader()
    try:
        loader.load(data)
    finally:
        loader.close()

    logger.info("Pipeline concluído em %s", datetime.now() - start)
    return 0


if __name__ == "__main__":
    sys.exit(main())
