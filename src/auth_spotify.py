#!/usr/bin/env python3
"""Autorização isolada do app (OAuth Authorization Code).

Salva o token em .cache_user para o pipeline e a inserção rápida usarem sem
precisar autorizar de novo a cada execução.

Uso:
  python src/auth_spotify.py

Pré-requisitos:
  - Redirect URI cadastrado no dashboard: http://127.0.0.1:8888/callback
  - Conta dona do app com Spotify Premium (requisito do dev mode)
"""
import logging
import sys

from ingestion.oauth import build_user_client

logger = logging.getLogger("auth_spotify")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    print("===== Autorização do Spotify =====")
    client = build_user_client()
    if client is None:
        print("\nFalha na autorização. Token não foi salvo.")
        return 1
    try:
        me = client.me()
        print(f"\nAutenticado como: {me.get('display_name')} ({me.get('id')})")
    except Exception as exc:
        print(f"\nToken salvo, mas não foi possível buscar o perfil: {type(exc).__name__}")
    print("Token salvo em .cache_user — pronto para o pipeline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
