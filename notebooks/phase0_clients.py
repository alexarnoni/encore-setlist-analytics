"""
notebooks/phase0_clients.py
----------------------------
Clientes reutilizáveis para as APIs setlist.fm e MusicBrainz.

Frozen na Fase 0: usado apenas por notebooks/00_validacao.ipynb. O
pipeline de produção (spec-01) usa src/encore/clients/ (sem cache em
disco para setlist.fm, dados vão direto para o schema raw_setlistfm).
Este arquivo não deve ganhar novas funcionalidades — mudanças aqui só
para manter o notebook de validação executável.

Regras implementadas:
- Cache em disco: toda resposta é salva como JSON bruto antes de qualquer
  processamento. Se o arquivo de cache já existir, lê do disco.
- setlist.fm: header x-api-key + Accept: application/json, pausa de 1s entre
  chamadas reais, backoff de até 3 tentativas em erro 429/503.
- MusicBrainz: endpoint /recording?artist=MBID, limit=100, paginação por
  offset até esgotar "recording-count". User-Agent obrigatório, 1 req/s,
  backoff de até 3 tentativas em erro 429/503.
- Contadores de requisições reais por API (não incrementam em leitura de
  cache). Contador de hits de cache exibido ao fim de cada etapa.
"""

import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Carrega variáveis do .env localizado na raiz do projeto
load_dotenv(Path(__file__).parent.parent / ".env")

# ---------------------------------------------------------------------------
# Configurações gerais
# ---------------------------------------------------------------------------

# Diretório raiz para cache dos dados brutos
CACHE_DIR = Path(__file__).parent.parent / "data" / "raw"

# User-Agent exigido pela política da MusicBrainz
MUSICBRAINZ_USER_AGENT = "Encore/0.1 (alexandre.anf@gmail.com)"

# Tempo de espera base (segundos) entre chamadas reais
SETLISTFM_RATE_DELAY = 1.0    # 2 req/s → pausa de 1s é segura
MUSICBRAINZ_RATE_DELAY = 1.0  # máximo 1 req/s

# Configurações de retry para 429 / 503
MAX_RETRIES = 3
RETRY_BACKOFF_MAX = 16  # segundos; teto do backoff exponencial (2^n)


# ---------------------------------------------------------------------------
# Contadores de requisições reais e hits de cache
# ---------------------------------------------------------------------------

_counters: dict[str, int] = {
    "setlistfm": 0,
    "musicbrainz": 0,
}

# Contador de respostas servidas pelo cache (não zera entre etapas)
_cache_hits: dict[str, int] = {
    "setlistfm": 0,
    "musicbrainz": 0,
}


def get_counters() -> dict[str, int]:
    """Retorna cópia dos contadores de requisições reais por API."""
    return dict(_counters)


def get_cache_hits() -> dict[str, int]:
    """Retorna cópia dos contadores de leituras de cache por API."""
    return dict(_cache_hits)


def reset_counters() -> None:
    """
    Zera apenas os contadores de requisições reais.
    Os hits de cache NÃO são zerados entre etapas; acumulam na sessão.
    """
    _counters["setlistfm"] = 0
    _counters["musicbrainz"] = 0


# ---------------------------------------------------------------------------
# Utilitários internos
# ---------------------------------------------------------------------------

def _cache_path(api: str, endpoint_key: str) -> Path:
    """
    Retorna o caminho do arquivo de cache para um dado endpoint.

    Parâmetros
    ----------
    api : str
        Nome da API ('setlistfm' ou 'musicbrainz').
    endpoint_key : str
        Identificador único do recurso (ex.: 'artist_mbid_setlists_p1').
        Use apenas caracteres seguros para nomes de arquivo.
    """
    cache_dir = CACHE_DIR / api
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{endpoint_key}.json"


def _load_cache(path: Path, api_name: str = "") -> dict | None:
    """
    Lê e retorna o JSON do cache se existir; caso contrário retorna None.
    Incrementa o contador de cache hits quando encontra o arquivo.
    """
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if api_name:
                _cache_hits[api_name] += 1
            return data
        except (json.JSONDecodeError, OSError):
            # Cache corrompido: descarta e deixa a chamada HTTP acontecer
            return None
    return None


def _save_cache(path: Path, data: dict) -> None:
    """Salva dados como JSON bruto no disco."""
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _request_with_retry(
    session: requests.Session,
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    rate_delay: float = 1.0,
    api_name: str = "",
) -> dict:
    """
    Executa uma requisição GET com backoff exponencial em 429/503.

    Incrementa o contador de requisições reais da API indicada.
    Aguarda `rate_delay` segundos após cada chamada real.
    """
    attempt = 0
    last_status: int | None = None
    while attempt < MAX_RETRIES:
        # Incrementa o contador apenas quando a chamada HTTP é de fato efetuada
        _counters[api_name] += 1
        try:
            response = session.get(url, params=params, headers=headers, timeout=15)
            last_status = response.status_code

            if response.status_code in (429, 503):
                wait = min(2 ** (attempt + 1), RETRY_BACKOFF_MAX)  # 2s, 4s, 8s…
                print(
                    f"  [{api_name}] HTTP {response.status_code} — "
                    f"aguardando {wait}s antes de tentar novamente "
                    f"(tentativa {attempt + 1}/{MAX_RETRIES})…"
                )
                time.sleep(wait)
                attempt += 1
                continue

            response.raise_for_status()
            time.sleep(rate_delay)  # respeita o rate limit após sucesso
            return response.json()

        except requests.exceptions.RequestException as exc:
            wait = min(2 ** (attempt + 1), RETRY_BACKOFF_MAX)  # 2s, 4s, 8s…
            print(
                f"  [{api_name}] Erro de rede: {exc} — "
                f"aguardando {wait}s (tentativa {attempt + 1}/{MAX_RETRIES})…"
            )
            time.sleep(wait)
            attempt += 1

    raise RuntimeError(
        f"[{api_name}] Falha após {MAX_RETRIES} tentativas para: {url} "
        f"(último status HTTP: {last_status})"
    )


# ---------------------------------------------------------------------------
# Cliente setlist.fm
# ---------------------------------------------------------------------------

class SetlistFmClient:
    """
    Cliente para a API setlist.fm.

    Uso básico
    ----------
    >>> client = SetlistFmClient()
    >>> setlists = client.get_artist_setlists(mbid="...", page=1)
    """

    BASE_URL = "https://api.setlist.fm/rest/1.0"

    def __init__(self) -> None:
        api_key = os.getenv("SETLISTFM_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "SETLISTFM_API_KEY não encontrada. "
                "Crie um arquivo .env na raiz do projeto com essa variável."
            )
        self._session = requests.Session()
        self._session.headers.update(
            {
                "x-api-key": api_key,
                "Accept": "application/json",
            }
        )

    def get_artist_setlists(self, mbid: str, page: int = 1) -> dict:
        """
        Busca os setlists de um artista pelo MBID, com cache em disco.

        Parâmetros
        ----------
        mbid : str
            MusicBrainz ID do artista.
        page : int
            Número da página (começa em 1).

        Retorna
        -------
        dict
            Resposta bruta da API (ou cache em disco se disponível).
        """
        cache_key = f"artist_{mbid}_setlists_p{page}"
        cache_file = _cache_path("setlistfm", cache_key)

        cached = _load_cache(cache_file, "setlistfm")
        if cached is not None:
            return cached

        url = f"{self.BASE_URL}/artist/{mbid}/setlists"
        params = {"p": page}
        data = _request_with_retry(
            self._session,
            url,
            params=params,
            rate_delay=SETLISTFM_RATE_DELAY,
            api_name="setlistfm",
        )
        _save_cache(cache_file, data)
        return data

    def search_artist(self, artist_name: str) -> dict:
        """
        Pesquisa artistas pelo nome.

        Parâmetros
        ----------
        artist_name : str
            Nome do artista a pesquisar.

        Retorna
        -------
        dict
            Resposta bruta da API (ou cache em disco se disponível).
        """
        safe_name = "".join(c if c.isalnum() else "_" for c in artist_name).lower()
        cache_key = f"search_artist_{safe_name}"
        cache_file = _cache_path("setlistfm", cache_key)

        cached = _load_cache(cache_file, "setlistfm")
        if cached is not None:
            return cached

        url = f"{self.BASE_URL}/search/artists"
        params = {"artistName": artist_name, "sort": "relevance"}
        data = _request_with_retry(
            self._session,
            url,
            params=params,
            rate_delay=SETLISTFM_RATE_DELAY,
            api_name="setlistfm",
        )
        _save_cache(cache_file, data)
        return data


# ---------------------------------------------------------------------------
# Cliente MusicBrainz
# ---------------------------------------------------------------------------

class MusicBrainzClient:
    """
    Cliente para a API MusicBrainz.

    Uso básico
    ----------
    >>> client = MusicBrainzClient()
    >>> artista = client.search_artist("Arctic Monkeys")
    >>> gravacoes = client.get_artist_recordings(mbid="...")
    """

    BASE_URL = "https://musicbrainz.org/ws/2"

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": MUSICBRAINZ_USER_AGENT})

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        """Executa GET autenticado com rate limit e cache."""
        url = f"{self.BASE_URL}/{endpoint}"
        base_params = {"fmt": "json"}
        if params:
            base_params.update(params)
        return _request_with_retry(
            self._session,
            url,
            params=base_params,
            rate_delay=MUSICBRAINZ_RATE_DELAY,
            api_name="musicbrainz",
        )

    def search_artist(self, artist_name: str) -> dict:
        """
        Busca artistas pelo nome no MusicBrainz.

        Parâmetros
        ----------
        artist_name : str
            Nome do artista.

        Retorna
        -------
        dict
            Resposta bruta com lista de artistas ranqueados por score.
        """
        safe_name = "".join(c if c.isalnum() else "_" for c in artist_name).lower()
        cache_key = f"search_artist_{safe_name}"
        cache_file = _cache_path("musicbrainz", cache_key)

        cached = _load_cache(cache_file, "musicbrainz")
        if cached is not None:
            return cached

        data = self._get("artist", {"query": artist_name, "limit": 5})
        _save_cache(cache_file, data)
        return data

    def get_artist(self, mbid: str) -> dict:
        """
        Busca os detalhes de um artista pelo MBID.

        Parâmetros
        ----------
        mbid : str
            MusicBrainz ID do artista.

        Retorna
        -------
        dict
            Dados brutos do artista (nome, país, life-span, etc.).
        """
        cache_key = f"artist_{mbid}"
        cache_file = _cache_path("musicbrainz", cache_key)

        cached = _load_cache(cache_file, "musicbrainz")
        if cached is not None:
            return cached

        data = self._get(f"artist/{mbid}", {"inc": "aliases"})
        _save_cache(cache_file, data)
        return data

    def get_release_groups(self, mbid: str, offset: int = 0) -> dict:
        """
        Lista os release-groups de um artista.

        Parâmetros
        ----------
        mbid : str
            MusicBrainz ID do artista.
        offset : int
            Paginação: início do bloco de resultados.

        Retorna
        -------
        dict
            Resposta bruta com lista de release-groups.
        """
        cache_key = f"artist_{mbid}_release_groups_off{offset}"
        cache_file = _cache_path("musicbrainz", cache_key)

        cached = _load_cache(cache_file, "musicbrainz")
        if cached is not None:
            return cached

        data = self._get(
            f"artist/{mbid}",
            {
                "inc": "release-groups",
                "type": "album",
                "limit": 100,
                "offset": offset,
            },
        )
        _save_cache(cache_file, data)
        return data

    def get_release_group_detail(self, rg_mbid: str) -> dict:
        """
        Detalhes de um release-group, incluindo datas de lançamento.

        Parâmetros
        ----------
        rg_mbid : str
            MBID do release-group.

        Retorna
        -------
        dict
            Dados brutos do release-group.
        """
        cache_key = f"release_group_{rg_mbid}"
        cache_file = _cache_path("musicbrainz", cache_key)

        cached = _load_cache(cache_file, "musicbrainz")
        if cached is not None:
            return cached

        data = self._get(f"release-group/{rg_mbid}", {"inc": "releases"})
        _save_cache(cache_file, data)
        return data

    def get_releases_for_release_group(self, rg_mbid: str) -> dict:
        """
        Busca os releases oficiais de um release-group, incluindo faixas.

        Usa o endpoint /release?release-group={rg_mbid}&status=official&inc=recordings
        para obter todos os releases com suas faixas (recording id e título).

        Parâmetros
        ----------
        rg_mbid : str
            MBID do release-group.

        Retorna
        -------
        dict
            Resposta bruta com "releases" (lista) e "release-count" (int).
        """
        cache_key = f"releases_rg_{rg_mbid}"
        cache_file = _cache_path("musicbrainz", cache_key)

        cached = _load_cache(cache_file, "musicbrainz")
        if cached is not None:
            return cached

        data = self._get(
            "release",
            {
                "release-group": rg_mbid,
                "status": "official",
                "inc": "recordings",
                "limit": 100,
            },
        )
        _save_cache(cache_file, data)
        return data

    def get_recordings(self, mbid: str, offset: int = 0) -> dict:
        """
        Lista as gravações de um artista via endpoint /recording?artist=MBID,
        paginadas de 100 em 100.

        O campo "recording-count" da resposta informa o total disponível.
        O campo "first-release-date" de cada gravação é retornado como texto
        (pode ser "YYYY", "YYYY-MM" ou "YYYY-MM-DD").

        Parâmetros
        ----------
        mbid : str
            MusicBrainz ID do artista.
        offset : int
            Paginação: início do bloco de resultados (múltiplo de 100).

        Retorna
        -------
        dict
            Resposta bruta com "recordings" (lista) e "recording-count" (int).
        """
        cache_key = f"recordings_artist_{mbid}_off{offset}"
        cache_file = _cache_path("musicbrainz", cache_key)

        cached = _load_cache(cache_file, "musicbrainz")
        if cached is not None:
            return cached

        # Endpoint correto: /recording?artist=MBID&limit=100&offset=N
        data = self._get(
            "recording",
            {
                "artist": mbid,
                "limit": 100,
                "offset": offset,
            },
        )
        _save_cache(cache_file, data)
        return data
