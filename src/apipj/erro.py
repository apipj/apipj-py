"""Exceção do cliente apipj."""

from __future__ import annotations

from typing import Any, Optional, Tuple

__all__ = ["ApipjErro"]


class ApipjErro(Exception):
    """Erro lançado pelo cliente apipj.

    Atributos:

    - ``status``: status HTTP da resposta (400, 401, 404, 429, 5xx) ou ``0`` para falha de rede ou
      tempo esgotado.
    - ``code``: código estável em snake_case (``invalid_cnpj``, ``validation_error``, ``unauthorized``,
      ``rate_limited``, ``quota_exceeded``, ``dataset_unavailable``, ``server_error``,
      ``network_error``, ``timeout``, ``invalid_response``...).
    - ``message``: mensagem em português.
    - ``retry_after``: segundos a esperar (só em ``rate_limited``).
    - ``upgrade_url``: página de planos (``quota_exceeded`` e ``rate_limited`` com chave).
    - ``signup_url``: página para criar a chave grátis (429 da consulta sem chave, ou 401 com ela fechada).
    - ``reset``: epoch Unix (segundos) em que a cota mensal zera (só em ``quota_exceeded``).
    - ``cnpj``: entrada normalizada (só em ``invalid_cnpj``).
    - ``details``: detalhes de ``validation_error``.
    - ``corpo``: corpo da resposta, quando houve.
    """

    status: int
    code: str
    message: str
    retry_after: Optional[float]
    upgrade_url: Optional[str]
    signup_url: Optional[str]
    reset: Optional[int]
    cnpj: Optional[str]
    details: Any
    corpo: Any

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        retry_after: Optional[float] = None,
        upgrade_url: Optional[str] = None,
        signup_url: Optional[str] = None,
        reset: Optional[int] = None,
        cnpj: Optional[str] = None,
        details: Any = None,
        corpo: Any = None,
    ) -> None:
        super().__init__(status, code, message)
        self.status = status
        self.code = code
        self.message = message
        self.retry_after = retry_after
        self.upgrade_url = upgrade_url
        self.signup_url = signup_url
        self.reset = reset
        self.cnpj = cnpj
        self.details = details
        self.corpo = corpo

    def __str__(self) -> str:
        return f"{self.status} {self.code}: {self.message}"

    def __repr__(self) -> str:
        return f"ApipjErro(status={self.status!r}, code={self.code!r}, message={self.message!r})"

    def __reduce__(self) -> Tuple[Any, ...]:
        # permite pickle (multiprocessing, cache) com os argumentos nomeados
        return (
            _recriar,
            (
                self.status,
                self.code,
                self.message,
                {
                    "retry_after": self.retry_after,
                    "upgrade_url": self.upgrade_url,
                    "signup_url": self.signup_url,
                    "reset": self.reset,
                    "cnpj": self.cnpj,
                    "details": self.details,
                    "corpo": self.corpo,
                },
            ),
        )


def _recriar(status: int, code: str, message: str, extras: "dict[str, Any]") -> ApipjErro:
    return ApipjErro(status, code, message, **extras)
