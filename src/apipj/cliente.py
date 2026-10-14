"""Cliente da API de CNPJ do apipj (https://apipj.com.br)."""

from __future__ import annotations

import email.utils
import http.client
import json
import math
import os
import queue
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings
from typing import Any, Dict, Iterable, Iterator, Literal, Mapping, Optional, Set, Tuple, Union, cast, overload

from ._limitador import Cancelado, Limitador
from ._versao import __version__
from .cnpj import normalizar_cnpj, validar_local
from .erro import ApipjErro
from .tipos import (
    EmpresaCompleta,
    EmpresaSimplificada,
    Formato,
    Limites,
    Planos,
    ResultadoLote,
    ResultadoLoteSimplificado,
    Status,
    Validacao,
)

__all__ = ["Apipj"]

BASE_PADRAO = "https://apipj.com.br"
_FORMATOS = ("completo", "simplificado")
#: erros que valeriam para todos os CNPJs seguintes: ``consultar_varios`` para na hora
_FATAIS = frozenset({"unauthorized", "quota_exceeded"})
_USER_AGENT = f"apipj-python/{__version__}"
#: cadastro da chave grátis, com a origem desta biblioteca (o servidor mede o canal de captação)
URL_CADASTRO = "https://apipj.com.br/criar-conta?origem=api-lib-pypi-apipj"


class _Segredo:
    """Guarda a chave sem que ela apareça em ``repr()``, ``vars()`` ou logs."""

    __slots__ = ("_valor",)

    def __init__(self, valor: str) -> None:
        self._valor = valor

    def __repr__(self) -> str:
        return "'***'"

    __str__ = __repr__

    def revelar(self) -> str:
        return self._valor


class _Resposta:
    __slots__ = ("status", "headers", "corpo")

    def __init__(self, status: int, headers: Mapping[str, str], corpo: Any) -> None:
        self.status = status
        self.headers = headers
        self.corpo = corpo

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def cabecalho(self, nome: str) -> Optional[str]:
        v = self.headers.get(nome)
        return None if v is None else str(v)


class Apipj:
    """Cliente da API de CNPJ do apipj (https://apipj.com.br).

    A chave de API é secreta: use este cliente só no servidor (back-end, scripts, jobs). Nunca a
    coloque em código distribuído para o usuário final.

    :param chave: chave de API (``apipj_live_...``). Padrão: variável de ambiente ``APIPJ_KEY``,
        lida só na hora de consultar.
    :param base_url: URL base da API. Padrão: ``https://apipj.com.br``.
    :param timeout: tempo máximo de espera da rede, em segundos, por tentativa (``0``/``None`` desliga).
    :param tentativas: tentativas por chamada, contando a primeira (``1`` = sem repetir).
    :param espera_base: base do backoff de 5xx e falhas de rede, em segundos (1 s, 2 s, 4 s...).
    :param janela: janela do limite por minuto, em segundos (60). Útil em testes.
    """

    def __init__(
        self,
        chave: Optional[str] = None,
        base_url: str = BASE_PADRAO,
        timeout: Optional[float] = 10,
        tentativas: int = 3,
        *,
        espera_base: float = 1.0,
        janela: float = 60.0,
        avisos: bool = True,
    ) -> None:
        self._chave: Optional[_Segredo] = _Segredo(chave.strip()) if chave and chave.strip() else None
        #: URL base da API, sem barra no fim
        self.base_url: str = str(base_url).rstrip("/")
        #: tempo máximo de espera da rede por tentativa, em segundos (``None`` desliga)
        self.timeout: Optional[float] = float(timeout) if timeout else None
        #: tentativas por chamada, contando a primeira
        self.tentativas: int = max(1, int(tentativas or 1))
        self.espera_base: float = float(espera_base)
        self.janela: float = float(janela)
        #: limites informados pela última consulta (``X-RateLimit-*``, ``X-Quota-*`` e, sem chave, ``X-Daily-*``)
        self.limites: Optional[Limites] = None
        self._avisos = avisos is not False
        self._avisou_sem_chave = False
        self._abridor = urllib.request.build_opener()

    def __repr__(self) -> str:
        chave = "definida" if self._chave else "APIPJ_KEY"
        return (
            f"Apipj(base_url={self.base_url!r}, timeout={self.timeout!r}, "
            f"tentativas={self.tentativas!r}, chave={chave})"
        )

    # ------------------------------------------------------------ consulta

    @overload
    def consultar(self, cnpj: str, *, formato: Literal["simplificado"]) -> Optional[EmpresaSimplificada]: ...

    @overload
    def consultar(self, cnpj: str, *, formato: Literal["completo"] = ...) -> Optional[EmpresaCompleta]: ...

    @overload
    def consultar(
        self, cnpj: str, *, formato: Formato = ...
    ) -> Union[EmpresaCompleta, EmpresaSimplificada, None]: ...

    def consultar(
        self, cnpj: str, *, formato: Formato = "completo"
    ) -> Union[EmpresaCompleta, EmpresaSimplificada, None]:
        """Consulta os dados cadastrais de um CNPJ (exige chave). Valida o DV localmente antes de chamar.

        :param cnpj: CNPJ numérico ou alfanumérico, com ou sem máscara.
        :param formato: ``completo`` (padrão) ou ``simplificado``.
        :returns: o documento, ou ``None`` se o CNPJ não está na base (404 ``not_found``).
        :raises ApipjErro: 400 ``invalid_cnpj`` (sem chamar a API), 401, 429 ``quota_exceeded``,
            429 ``rate_limited`` depois de esgotar as tentativas, 5xx, falha de rede ou tempo
            esgotado depois das tentativas.
        """
        v = validar_local(cnpj)
        if not v["valido"]:
            raise ApipjErro(400, "invalid_cnpj", v["erro"] or "CNPJ inválido", cnpj=v["cnpj"])
        return cast(
            Union[EmpresaCompleta, EmpresaSimplificada, None],
            self._consultar(v["cnpj"], _conferir_formato(formato), None),
        )

    def validar(self, cnpj: str) -> Validacao:
        """Valida formato e DV pela API (``GET /v1/valida/{cnpj}``: sem chave e sem consumo de cota).

        Para validar offline, use :func:`apipj.cnpj_valido`.
        """
        c = normalizar_cnpj(cnpj)
        if len(c) == 0 or len(c) > 32:
            return validar_local(c)
        res = self._requisitar("/v1/valida/" + urllib.parse.quote(c, safe=""))
        return cast(Validacao, _exigir_json(res))

    def status(self) -> Status:
        """Status do serviço e da base (``GET /v1/status``, sem chave)."""
        return cast(Status, _exigir_json(self._requisitar("/v1/status")))

    def planos(self) -> Planos:
        """Planos públicos, preços e limites (``GET /v1/plans``, sem chave)."""
        return cast(Planos, _exigir_json(self._requisitar("/v1/plans")))

    # ------------------------------------------------------------ lote

    @overload
    def consultar_varios(
        self,
        lista: Iterable[str],
        *,
        simultaneas: int = ...,
        formato: Literal["simplificado"],
        rpm: Optional[int] = ...,
    ) -> Iterator[ResultadoLoteSimplificado]: ...

    @overload
    def consultar_varios(
        self,
        lista: Iterable[str],
        *,
        simultaneas: int = ...,
        formato: Literal["completo"] = ...,
        rpm: Optional[int] = ...,
    ) -> Iterator[ResultadoLote]: ...

    @overload
    def consultar_varios(
        self,
        lista: Iterable[str],
        *,
        simultaneas: int = ...,
        formato: Formato = ...,
        rpm: Optional[int] = ...,
    ) -> Iterator[Union[ResultadoLote, ResultadoLoteSimplificado]]: ...

    def consultar_varios(
        self,
        lista: Iterable[str],
        *,
        simultaneas: int = 4,
        formato: Formato = "completo",
        rpm: Optional[int] = None,
    ) -> Iterator[Any]:
        """Consulta vários CNPJs em paralelo (threads), respeitando o limite por minuto do plano.

        Gera dicts ``{"cnpj", "documento", "erro"}`` na ordem de conclusão.

        - O limite por minuto é lido de ``X-RateLimit-Limit``/``Remaining``/``Reset`` e nunca é
          ultrapassado (a primeira consulta sai sozinha para descobrir o limite). ``rpm`` fixa um
          teto menor que o do plano.
        - CNPJs repetidos (depois de normalizados) são consultados uma vez só.
        - CNPJs inválidos não chamam a API: saem com ``documento=None`` e ``erro`` ``invalid_cnpj``.
        - 404 sai com ``documento=None`` e ``erro=None``.
        - Erro de um CNPJ (5xx, rede ou tempo esgotado depois das tentativas) sai no próprio item.
        - 401 e cota mensal esgotada (``quota_exceeded``) encerram o lote lançando ``ApipjErro``,
          depois de entregar os resultados já prontos.
        - Sair do laço (``break``) ou fechar o gerador para de chamar a API.
        """
        if lista is None or isinstance(lista, (str, bytes)) or not hasattr(lista, "__iter__"):
            raise TypeError("consultar_varios espera uma lista (ou iterável) de CNPJs")
        fmt = _conferir_formato(formato)
        n = max(1, int(simultaneas or 1))
        return self._lote(iter(lista), fmt, n, rpm)

    def _lote(self, fonte: Iterator[str], formato: str, simultaneas: int, rpm: Optional[int]) -> Iterator[Any]:
        limitador = Limitador(rpm=rpm, janela=self.janela)
        trava_fonte = threading.Lock()
        vistos: Set[str] = set()
        fila: "queue.Queue[Tuple[str, Any]]" = queue.Queue(maxsize=simultaneas * 2)
        fechado = threading.Event()  # o consumidor parou de ler
        estado: Dict[str, Optional[BaseException]] = {"fatal": None}

        def entregar(tipo: str, valor: Any) -> bool:
            while not fechado.is_set():
                try:
                    fila.put((tipo, valor), timeout=0.05)
                    return True
                except queue.Full:
                    continue
            return False

        def proximo() -> Optional[str]:
            with trava_fonte:
                if limitador.encerrado:
                    return None
                for entrada in fonte:
                    v = validar_local(entrada)
                    if v["cnpj"] in vistos:
                        continue
                    vistos.add(v["cnpj"])
                    if not v["valido"]:
                        erro = ApipjErro(400, "invalid_cnpj", v["erro"] or "CNPJ inválido", cnpj=v["cnpj"])
                        if not entregar("item", {"cnpj": v["cnpj"], "documento": None, "erro": erro}):
                            return None
                        continue
                    return v["cnpj"]
                return None

        def falhar(e: BaseException) -> None:
            if estado["fatal"] is None:
                estado["fatal"] = e
            limitador.encerrar()

        def trabalhador() -> None:
            try:
                while not limitador.encerrado and not fechado.is_set():
                    try:
                        cnpj = proximo()
                    except BaseException as e:  # erro vindo do iterável de entrada
                        falhar(e)
                        return
                    if cnpj is None:
                        return
                    try:
                        documento = self._consultar(cnpj, formato, limitador)
                    except Cancelado:
                        return
                    except ApipjErro as e:
                        if e.code in _FATAIS:
                            falhar(e)
                            return
                        entregar("item", {"cnpj": cnpj, "documento": None, "erro": e})
                        continue
                    except BaseException as e:  # defeito inesperado: encerra o lote e propaga
                        falhar(e)
                        return
                    entregar("item", {"cnpj": cnpj, "documento": documento, "erro": None})
            finally:
                entregar("fim", None)

        def gerar() -> Iterator[Any]:
            # as threads só começam na primeira leitura do gerador
            ativos = 0
            try:
                for i in range(simultaneas):
                    threading.Thread(target=trabalhador, name=f"apipj-lote-{i + 1}", daemon=True).start()
                    ativos += 1
                while ativos:
                    tipo, valor = fila.get()
                    if tipo == "fim":
                        ativos -= 1
                    else:
                        yield valor
                # entrega primeiro o que já ficou pronto (consulta paga é consulta entregue), depois o erro
                fatal = estado["fatal"]
                if fatal is not None:
                    raise fatal
            finally:
                fechado.set()
                limitador.encerrar()

        return gerar()

    # ------------------------------------------------------------ internos

    def _consultar(self, cnpj: str, formato: str, limitador: Optional[Limitador]) -> Optional[Dict[str, Any]]:
        sufixo = "?formato=simplificado" if formato == "simplificado" else ""
        res = self._requisitar(f"/v1/cnpj/{cnpj}{sufixo}", autenticar=True, limitador=limitador)
        if res.status == 404:
            if isinstance(res.corpo, dict) and res.corpo.get("code") == "not_found":
                return None
            raise _erro_da_resposta(res)
        return _exigir_json(res)

    def _obter_chave(self) -> Optional[str]:
        """Chave do argumento ou de APIPJ_KEY; sem nenhuma, ``None`` (consulta sem chave, com limite de teste)."""
        if self._chave is not None:
            return self._chave.revelar()
        chave = (os.environ.get("APIPJ_KEY") or "").strip()
        return chave or None

    def _avisar_sem_chave(self) -> None:
        if self._avisou_sem_chave or not self._avisos:
            return
        self._avisou_sem_chave = True
        warnings.warn(
            "apipj: consultando sem chave de API (limite de teste por IP: poucas consultas por minuto e por dia). "
            f"Crie uma chave grátis, com 10 consultas por minuto e 50 mil por mês, em {URL_CADASTRO} e use "
            "Apipj(chave=...) ou APIPJ_KEY. Para não ver este aviso: Apipj(avisos=False).",
            UserWarning,
            stacklevel=4,
        )

    def _requisitar(
        self, caminho: str, *, autenticar: bool = False, limitador: Optional[Limitador] = None
    ) -> _Resposta:
        """Faz a chamada com repetição: 429 ``rate_limited`` espera Retry-After; 5xx e rede, backoff
        1 s, 2 s... Devolve a resposta 2xx ou 404 com o corpo já lido; demais status viram ApipjErro."""
        chave = self._obter_chave() if autenticar else None
        if autenticar and chave is None:
            self._avisar_sem_chave()
        url = self.base_url + caminho
        dormir = limitador.dormir if limitador is not None else time.sleep

        tentativa = 0
        while True:
            tentativa += 1
            ultima = tentativa >= self.tentativas
            if limitador is not None:
                limitador.aguardar()
            res: Optional[_Resposta] = None
            try:
                res = self._tentar(url, chave)
            except ApipjErro:
                if limitador is not None:
                    limitador.registrar(None, None)
                if ultima:
                    raise
                dormir(self._backoff(tentativa))
                continue

            if autenticar:
                self._guardar_limites(res)
            erro = None if (res.ok or res.status == 404) else _erro_da_resposta(res)
            if limitador is not None:
                if erro is not None and erro.code in _FATAIS:
                    # ninguém mais do lote deve chamar a API (a sonda não libera os demais)
                    limitador.encerrar()
                limitador.registrar(
                    _inteiro(res.cabecalho("X-RateLimit-Limit")), _inteiro(res.cabecalho("X-RateLimit-Remaining"))
                )
            if erro is None:
                return res

            if res.status == 429 and erro.code != "quota_exceeded":
                if ultima:
                    raise erro
                espera = max(0.0, erro.retry_after if erro.retry_after is not None else 1.0)
                if limitador is not None:
                    limitador.bloquear(espera)
                dormir(espera)
                continue
            if res.status >= 500:
                if ultima:
                    raise erro
                dormir(self._backoff(tentativa))
                continue
            raise erro

    def _tentar(self, url: str, chave: Optional[str]) -> _Resposta:
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", _USER_AGENT)
        if chave is not None:
            # não redirecionável: a chave nunca segue um redirecionamento para outro endereço
            req.add_unredirected_header("Authorization", f"Bearer {chave}")
        status: int
        headers: Any
        try:
            try:
                with self._abridor.open(req, timeout=self.timeout or socket.getdefaulttimeout()) as r:
                    status, headers, bruto = r.status, r.headers, r.read()
            except urllib.error.HTTPError as e:
                status, headers = e.code, e.headers
                try:
                    bruto = e.read()
                finally:
                    e.close()
        except (socket.timeout, TimeoutError) as e:
            raise self._erro_timeout() from e
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise self._erro_timeout() from e
            raise ApipjErro(0, "network_error", f"Falha de rede ao chamar a API: {e.reason}") from e
        except (OSError, http.client.HTTPException, ValueError) as e:
            raise ApipjErro(0, "network_error", f"Falha de rede ao chamar a API: {e}") from e
        return _Resposta(status, headers, _ler_corpo(bruto))

    def _erro_timeout(self) -> ApipjErro:
        return ApipjErro(0, "timeout", f"Sem resposta da API em {self.timeout:g} s" if self.timeout else "Sem resposta da API")

    def _backoff(self, tentativa: int) -> float:
        return float(min(30.0, self.espera_base * 2 ** (tentativa - 1)))

    def _guardar_limites(self, res: _Resposta) -> None:
        def h(nome: str) -> Optional[int]:
            return _inteiro(res.cabecalho(nome))

        limite = h("X-RateLimit-Limit")
        cota = h("X-Quota-Limit")
        diario = h("X-Daily-Limit")
        if limite is None and cota is None and diario is None:
            return
        self.limites = {
            "sem_chave": (res.cabecalho("X-Apipj-Acesso") or "").lower() == "sem-chave",
            "por_minuto": {"limite": limite, "restante": h("X-RateLimit-Remaining"), "reset": h("X-RateLimit-Reset")},
            "mensal": {"limite": cota, "restante": h("X-Quota-Remaining"), "reset": h("X-Quota-Reset")},
            "diario": {"limite": diario, "restante": h("X-Daily-Remaining"), "reset": h("X-Daily-Reset")},
        }


# ---------------------------------------------------------------- funções auxiliares


def _conferir_formato(formato: Any) -> str:
    f = "completo" if formato is None else formato
    if f not in _FORMATOS:
        raise ApipjErro(400, "validation_error", "formato deve ser um de: " + ", ".join(_FORMATOS))
    return str(f)


def _ler_corpo(bruto: bytes) -> Any:
    if not bruto:
        return None
    texto = bruto.decode("utf-8", errors="replace")
    try:
        return json.loads(texto)
    except ValueError:
        return texto


def _exigir_json(res: _Resposta) -> Dict[str, Any]:
    if not res.ok:
        raise _erro_da_resposta(res)
    if not isinstance(res.corpo, dict):
        raise ApipjErro(res.status, "invalid_response", "Resposta inesperada da API (não é JSON)", corpo=res.corpo)
    return res.corpo


def _erro_da_resposta(res: _Resposta) -> ApipjErro:
    c: Dict[str, Any] = res.corpo if isinstance(res.corpo, dict) else {}
    code = c["code"] if isinstance(c.get("code"), str) else _codigo_padrao(res.status)
    message = c["message"] if isinstance(c.get("message"), str) else f"A API respondeu HTTP {res.status}"
    retry_after: Optional[float] = None
    if res.status == 429:
        retry_after = _segundos_retry_after(res.cabecalho("Retry-After"))
        if retry_after is None:
            retry_after = _numero(c.get("retry_after"))
    upgrade_url = c.get("upgrade_url")
    signup_url = c.get("signup_url")
    reset = _numero(c.get("reset"))
    cnpj = c.get("cnpj")
    return ApipjErro(
        res.status,
        code,
        message,
        retry_after=retry_after,
        upgrade_url=upgrade_url if isinstance(upgrade_url, str) else None,
        signup_url=signup_url if isinstance(signup_url, str) else None,
        reset=int(reset) if reset is not None else None,
        cnpj=cnpj if isinstance(cnpj, str) else None,
        details=c.get("details"),
        corpo=res.corpo,
    )


def _codigo_padrao(status: int) -> str:
    if status == 400:
        return "bad_request"
    if status == 401:
        return "unauthorized"
    if status == 403:
        return "forbidden"
    if status == 404:
        return "not_found"
    if status == 429:
        return "rate_limited"
    if status == 503:
        return "dataset_unavailable"
    if status >= 500:
        return "server_error"
    return "http_error"


def _numero(v: Any) -> Optional[float]:
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(n):
        return None
    return int(n) if n.is_integer() else n


def _inteiro(v: Any) -> Optional[int]:
    n = _numero(v)
    return None if n is None else int(n)


def _segundos_retry_after(v: Optional[str]) -> Optional[float]:
    if v is None or v.strip() == "":
        return None
    n = _numero(v.strip())
    if n is not None:
        return max(0, n)
    try:
        data = email.utils.parsedate_to_datetime(v)
    except (TypeError, ValueError, IndexError):
        return None
    if data is None:
        return None
    return max(0, math.ceil(data.timestamp() - time.time()))

