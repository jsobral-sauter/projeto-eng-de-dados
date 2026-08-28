#!/usr/bin/env python3
"""Inserção rápida de itens do Spotify no banco (sem rodar o pipeline completo).

Exemplos:
  python src/quick_add.py --artist "Rush"
  python src/quick_add.py --track "One" --by "Metallica"
  python src/quick_add.py --album <spotify_id> --playlist <spotify_id>
  python src/quick_add.py --artist "Rush" --track "Heroes" --by "David Bowie"
  python src/quick_add.py            # menu interativo
  python src/quick_add.py --from payload.json

Comportamento:
  - Custo de poucas chamadas à API (segundos por item);
  - Idempotente: inserir o mesmo item de novo não duplica registros;
  - Sempre grava na Landing em data/landing/<dia>/quick_<hash>.json
    (nome determinístico por conteúdo: rerun do mesmo comando sobrescreve).
"""
import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone

from enrichment.enrich import enrich_payload
from ingestion.extract import SpotifyExtractor
from load.load_bronze import BronzeLoader
from load.load_postgres import PostgresLoader

logger = logging.getLogger("quick_add")

REQUIRED_KEYS = {"artists", "albums", "tracks", "track_albums", "playlists", "playlist_tracks"}


def landing_hash(payload):
    """Hash determinístico dos itens do payload (nome do arquivo de Landing)."""
    specs = []
    for a in payload["artists"]:
        specs.append(f"artist:{a.get('id')}")
    for t in payload["tracks"]:
        specs.append(f"track:{t.get('id')}")
    for al in payload["albums"]:
        specs.append(f"album:{al.get('id')}")
    for p in payload["playlists"]:
        specs.append(f"playlist:{p.get('id')}")
    return hashlib.sha1("|".join(sorted(specs)).encode()).hexdigest()[:8]


def load_from_file(path):
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    missing = REQUIRED_KEYS - set(payload)
    if missing:
        raise SystemExit(f"Payload inválido; faltam chaves: {sorted(missing)}")
    return payload


def load_all(payload):
    # Timestamp SEMPRE novo: insere um novo snapshot no bronze (histórico) e
    # nunca colide/apaga snapshots de execuções anteriores (pipeline ou outras).
    payload["_ingestion_timestamp"] = datetime.now(timezone.utc).isoformat()
    bronze_loader = BronzeLoader()
    try:
        bronze_loader.load(payload)
    finally:
        bronze_loader.close()
    loader = PostgresLoader()
    try:
        loader.load(payload)
    finally:
        loader.close()


def build_and_load(ex, artist_names, track_specs, album_ids, playlist_ids,
                   max_pages=1, skip_enrich=False, landing=True):
    payload = ex.collect_items(
        artist_names=artist_names,
        track_specs=track_specs,
        album_ids=album_ids,
        playlist_ids=playlist_ids,
        max_pages=max_pages,
    )
    if not (payload["artists"] or payload["albums"] or payload["tracks"] or payload["playlists"]):
        logger.warning("Nenhum item encontrado; nada será carregado.")
        return None
    if landing:
        ex._save_landing(payload, filename=f"quick_{landing_hash(payload)}.json")
    if not skip_enrich:
        enrich_payload(payload)
    load_all(payload)
    logger.info(
        "Inserção concluída: %d artistas, %d álbuns, %d tracks, %d playlists, %d playlist_tracks",
        len(payload["artists"]), len(payload["albums"]), len(payload["tracks"]),
        len(payload["playlists"]), len(payload["playlist_tracks"]),
    )
    return payload


def interactive(ex):
    """Menu interativo: acumula itens e carrega tudo de uma vez."""
    artist_names, track_specs, album_ids, playlist_ids = [], [], [], []
    print("\n===== INSERÇÃO RÁPIDA (Spotify -> banco) =====")
    while True:
        print("\nO que deseja inserir?")
        print("  [1] Artista (nome)")
        print("  [2] Música (nome + artista opcional)")
        print("  [3] Álbum (spotify_id)")
        print("  [4] Playlist (spotify_id)")
        print("  [5] CARREGAR NO BANCO")
        print("  [0] Sair")
        try:
            opt = input("> ").strip()
        except EOFError:
            print()
            break
        if opt == "0":
            break
        elif opt == "1":
            name = input("  Nome do artista: ").strip()
            if name:
                artist_names.append(name)
                print(f"  + artista: {name}")
        elif opt == "2":
            name = input("  Nome da música: ").strip()
            by = input("  Artista (opcional): ").strip() or None
            if name:
                track_specs.append((name, by))
                print(f"  + música: {name}" + (f" — {by}" if by else ""))
        elif opt == "3":
            aid = input("  Spotify ID do álbum: ").strip()
            if aid:
                album_ids.append(aid)
                print(f"  + álbum: {aid}")
        elif opt == "4":
            pid = input("  Spotify ID da playlist: ").strip()
            if pid:
                playlist_ids.append(pid)
                print(f"  + playlist: {pid}")
        elif opt == "5":
            if not (artist_names or track_specs or album_ids or playlist_ids):
                print("  Nenhum item adicionado ainda.")
                continue
            print("\n  Coletando e carregando...")
            build_and_load(ex, artist_names, track_specs, album_ids, playlist_ids)
            break
        else:
            print("  Opção inválida.")
    print("Encerrado.\n")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Inserção rápida de itens do Spotify no banco (sem o pipeline completo).",
    )
    parser.add_argument("--artist", action="append", default=[], help="Nome do artista (repetível)")
    parser.add_argument("--track", action="append", default=[], help="Nome da música (repetível)")
    parser.add_argument("--by", action="append", default=[], help="Artista da música (pareia com --track em ordem)")
    parser.add_argument("--album", action="append", default=[], help="Spotify ID do álbum (repetível)")
    parser.add_argument("--playlist", action="append", default=[], help="Spotify ID da playlist (repetível)")
    parser.add_argument("--album-pages", type=int, default=1, help="Páginas de álbuns por artista (default 1)")
    parser.add_argument("--skip-enrich", action="store_true", help="Pula o enriquecimento (gêneros/métricas)")
    parser.add_argument("--no-landing", action="store_true", help="Não grava na Landing")
    parser.add_argument("--from", dest="from_file", help="Carrega um payload JSON pronto (pula extração)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    if args.from_file:
        payload = load_from_file(args.from_file)
        if not args.skip_enrich:
            enrich_payload(payload)
        load_all(payload)
        logger.info("Carga do arquivo %s concluída", args.from_file)
        return 0

    track_specs = []
    for i, name in enumerate(args.track):
        track_specs.append((name, args.by[i] if i < len(args.by) else None))

    if args.artist or track_specs or args.album or args.playlist:
        build_and_load(
            ex := SpotifyExtractor(),
            artist_names=args.artist,
            track_specs=track_specs,
            album_ids=args.album,
            playlist_ids=args.playlist,
            max_pages=args.album_pages,
            skip_enrich=args.skip_enrich,
            landing=not args.no_landing,
        )
        return 0

    interactive(SpotifyExtractor())
    return 0


if __name__ == "__main__":
    sys.exit(main())
