import logging
import os
from pathlib import Path

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_PATH = PROJECT_ROOT / ".cache_user"

USER_SCOPES = (
    "playlist-read-private "
    "playlist-read-collaborative "
    "user-top-read "
    "user-read-recently-played "
    "user-read-private"
)


def build_user_client():
    """Cria um cliente Spotify autenticado com OAuth do usuário.

    Falha soft: se não houver credenciais/token e o usuário não autorizar,
    retorna None para o pipeline seguir apenas com dados públicos.

    Fluxo:
    1) Token já cacheado e válido (ou renovável) -> usa direto;
    2) Sem token: imprime a URL, abre o navegador e o servidor local captura
       o código automaticamente (redirect http://127.0.0.1:8888/callback);
       se o navegador não abrir, basta abrir a URL impressa manualmente;
    3) Se o fluxo automático falhar, fallback manual (colar o código).
    """
    load_dotenv()
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")
    if not all([client_id, client_secret, redirect_uri]):
        logger.warning("Credenciais OAuth incompletas — dados de usuário indisponíveis")
        return None

    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=USER_SCOPES,
        cache_path=str(CACHE_PATH),
    )

    # 1) Token já autorizado e válido (validação renova se expirado)
    try:
        cached = auth_manager.validate_token(auth_manager.cache_handler.get_cached_token())
    except Exception:
        cached = None
    if cached:
        logger.info("Token de usuário carregado do cache")
        return spotipy.Spotify(auth_manager=auth_manager, requests_timeout=30)

    # 2) Fluxo interativo: navegador + servidor local (captura automática).
    #    Imprime a URL sempre — se o navegador não abrir no WSL, abra manualmente.
    auth_url = auth_manager.get_authorize_url()
    print("\n============================================================")
    print("Autorize o aplicativo. Se o navegador não abrir, acesse:")
    print(auth_url)
    print("============================================================")
    logger.info("Aguardando autorização do usuário...")
    try:
        token_info = auth_manager.get_access_token()
        if token_info:
            logger.info("Usuário autorizado pelo fluxo automático")
            return spotipy.Spotify(auth_manager=auth_manager, requests_timeout=30)
    except Exception as exc:
        logger.warning("Fluxo automático falhou (%s); tentando manual...", type(exc).__name__)

    # 3) Fallback manual: URL + código colado
    try:
        url = auth_manager.get_authorize_url()
        print("\n============================================================")
        print("Autorize o aplicativo acessando a URL abaixo e copie o código:")
        print(url)
        print("============================================================")
        code = input("Cole o código de autorização aqui e pressione Enter: ").strip()
        if not code:
            raise ValueError("Nenhum código informado")
        if "code=" in code:
            _, code = auth_manager.parse_auth_response_url(code)
        token_info = auth_manager.get_access_token(code)
        if token_info:
            logger.info("Usuário autorizado pelo fluxo manual")
            return spotipy.Spotify(auth_manager=auth_manager, requests_timeout=30)
    except Exception as exc:
        logger.warning("Autorização manual falhou (%s)", type(exc).__name__)

    logger.warning("Sem autenticação de usuário — dados pessoais indisponíveis nesta execução")
    return None
