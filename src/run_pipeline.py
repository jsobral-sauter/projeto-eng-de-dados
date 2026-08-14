import logging
import sys
from datetime import datetime

from ingestion.extract import SpotifyExtractor
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
        "Extração concluída: %d artistas, %d álbuns, %d tracks, %d audio_features, %d playlists, %d playlist_tracks",
        len(data["artists"]), len(data["albums"]), len(data["tracks"]),
        len(data["audio_features"]), len(data["playlists"]), len(data["playlist_tracks"]),
    )

    loader = PostgresLoader()
    try:
        loader.load(data)
    finally:
        loader.close()

    logger.info("Pipeline concluído em %s", datetime.now() - start)
    return 0


if __name__ == "__main__":
    sys.exit(main())
