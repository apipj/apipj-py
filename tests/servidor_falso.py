"""Servidor HTTP falso para os testes (não é um arquivo de teste)."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Tuple

from apipj import calcular_dv

#: o tratador recebe (requisição, número da requisição 1, 2...) e devolve (status, corpo, cabeçalhos)
Resposta = Tuple[int, Any, Dict[str, str]]
Tratador = Callable[[Dict[str, Any], int], Resposta]


def json_(status: int, corpo: Any, headers: Optional[Dict[str, str]] = None) -> Resposta:
    return status, corpo, dict(headers or {})


class ServidorFalso:
    def __init__(self) -> None:
        self.requisicoes: List[Dict[str, Any]] = []
        self.tratador: Tratador = lambda req, n: json_(200, {})
        self._trava = threading.Lock()
        self._em_andamento = 0
        self.max_simultaneas = 0
        dono = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:  # silencia o log padrão
                pass

            def do_GET(self) -> None:  # noqa: N802
                registro = {
                    "metodo": self.command,
                    "url": self.path,
                    "headers": {k.lower(): v for k, v in self.headers.items()},
                    "em": time.monotonic(),
                }
                with dono._trava:
                    dono.requisicoes.append(registro)
                    n = len(dono.requisicoes)
                    dono._em_andamento += 1
                    dono.max_simultaneas = max(dono.max_simultaneas, dono._em_andamento)
                try:
                    try:
                        status, corpo, headers = dono.tratador(registro, n)
                    except Exception as e:  # erro no próprio teste
                        status, corpo, headers = 500, {"status": "ERROR", "code": "teste", "message": str(e)}, {}
                    if isinstance(corpo, (dict, list)):
                        bruto = json.dumps(corpo).encode("utf-8")
                        headers.setdefault("Content-Type", "application/json; charset=utf-8")
                    elif isinstance(corpo, bytes):
                        bruto = corpo
                    else:
                        bruto = str(corpo).encode("utf-8")
                        headers.setdefault("Content-Type", "text/html")
                    try:
                        self.send_response(status)
                        for k, v in headers.items():
                            self.send_header(k, v)
                        self.send_header("Content-Length", str(len(bruto)))
                        self.send_header("Connection", "close")
                        self.end_headers()
                        self.wfile.write(bruto)
                    except OSError:
                        pass  # o cliente desistiu (timeout)
                finally:
                    with dono._trava:
                        dono._em_andamento -= 1

        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._srv.daemon_threads = True
        self.url = f"http://127.0.0.1:{self._srv.server_address[1]}"
        self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True)
        self._thread.start()

    def limpar(self) -> None:
        with self._trava:
            self.requisicoes.clear()
            self.max_simultaneas = 0

    def fechar(self) -> None:
        self._srv.shutdown()
        self._srv.server_close()


def cnpj_da_url(url: str) -> str:
    return url.split("?")[0].rsplit("/", 1)[-1]


def documento(cnpj: str) -> Dict[str, Any]:
    """Documento mínimo no formato completo para um CNPJ."""
    return {
        "cnpj": cnpj,
        "cnpj_formatado": f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}",
        "razao_social": f"EMPRESA {cnpj}",
        "situacao_cadastral": {"codigo": "02", "descricao": "ATIVA", "data": "2020-01-01", "motivo": None},
        "atualizado_em": "2026-09",
    }


def gerar_cnpjs(n: int) -> List[str]:
    """``n`` CNPJs numéricos válidos e distintos."""
    lista = []
    i = 1
    while len(lista) < n:
        base = f"{str(10000000 + i * 7919)[:8]}0001"
        lista.append(base + calcular_dv(base))
        i += 1
    return lista


NOT_FOUND = {"status": "ERROR", "message": "CNPJ não encontrado", "code": "not_found"}


def rate_limited(retry_after: int) -> Resposta:
    return json_(
        429,
        {"status": "ERROR", "message": "Limite por minuto atingido", "code": "rate_limited", "retry_after": retry_after},
        {"Retry-After": str(retry_after)},
    )
