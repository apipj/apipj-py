"""Validação, normalização e formatação de CNPJ, 100% local (sem rede).

Vale para o CNPJ numérico e para o alfanumérico (IN RFB 2.229/2024):

- 14 caracteres: posições 1 a 12 em ``[A-Z0-9]``, posições 13 e 14 (dígitos verificadores) numéricas;
- valor de cada caractere = código ASCII - 48 (``'0'..'9'`` => 0..9, ``'A'..'Z'`` => 17..42);
- DV1 com pesos 5,4,3,2,9,8,7,6,5,4,3,2 e DV2 com pesos 6,5,4,3,2,9,8,7,6,5,4,3,2;
- resto = soma % 11; DV = 0 se resto < 2, senão 11 - resto;
- ``00000000000000`` é inválido mesmo com o DV "certo".
"""

from __future__ import annotations

import re
from typing import Optional

from .tipos import Validacao

__all__ = ["normalizar_cnpj", "calcular_dv", "validar_local", "cnpj_valido", "formatar_cnpj"]

_PESOS = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_RE_CNPJ = re.compile(r"[A-Z0-9]{12}[0-9]{2}")
_RE_BASE = re.compile(r"[A-Z0-9]{12}")
_RE_PONTUACAO = re.compile(r"[./\s-]")
_RE_INVALIDO = re.compile(r"[^A-Z0-9]")
_RE_LETRA = re.compile(r"[A-Z]")


def normalizar_cnpj(entrada: Optional[str]) -> str:
    """Remove pontuação (``.``, ``/``, ``-``) e espaços e converte para maiúsculas. Não valida.

    >>> normalizar_cnpj("12.abc.345/01de-35")
    '12ABC34501DE35'
    """
    if entrada is None:
        return ""
    return _RE_PONTUACAO.sub("", str(entrada).upper())


def calcular_dv(base12: str) -> str:
    """Calcula os dois dígitos verificadores de uma base de 12 caracteres ``[A-Z0-9]``.

    >>> calcular_dv("12ABC34501DE")
    '35'
    """
    base = normalizar_cnpj(base12)
    if not _RE_BASE.fullmatch(base):
        raise ValueError("a base do CNPJ deve ter 12 caracteres [A-Z0-9]")
    valores = [ord(ch) - 48 for ch in base]
    s1 = sum(v * p for v, p in zip(valores, _PESOS[1:]))
    dv1 = 0 if s1 % 11 < 2 else 11 - s1 % 11
    s2 = sum(v * p for v, p in zip(valores, _PESOS)) + dv1 * _PESOS[12]
    dv2 = 0 if s2 % 11 < 2 else 11 - s2 % 11
    return f"{dv1}{dv2}"


def validar_local(entrada: Optional[str]) -> Validacao:
    """Validação local, com o mesmo formato de resposta de ``GET /v1/valida/{cnpj}``.

    >>> validar_local("12.abc.345/01de-35")["valido"]
    True
    """
    cnpj = normalizar_cnpj(entrada)

    def invalido(erro: str) -> Validacao:
        return {"cnpj": cnpj, "valido": False, "formatado": None, "alfanumerico": False, "erro": erro}

    if not cnpj:
        return invalido("CNPJ vazio")
    if len(cnpj) != 14:
        return invalido(f"CNPJ deve ter 14 caracteres (recebido {len(cnpj)})")
    if not _RE_CNPJ.fullmatch(cnpj):
        if _RE_INVALIDO.search(cnpj):
            return invalido("CNPJ contém caracteres inválidos (permitidos: letras A-Z e dígitos)")
        return invalido("Os dois últimos caracteres (dígitos verificadores) devem ser numéricos")
    if cnpj == "00000000000000":
        return invalido("CNPJ zerado é inválido")
    if cnpj[12:] != calcular_dv(cnpj[:12]):
        return invalido("Dígitos verificadores inválidos")
    return {
        "cnpj": cnpj,
        "valido": True,
        "formatado": formatar_cnpj(cnpj),
        "alfanumerico": bool(_RE_LETRA.search(cnpj[:12])),
        "erro": None,
    }


def cnpj_valido(entrada: Optional[str]) -> bool:
    """``True`` se o CNPJ (numérico ou alfanumérico, com ou sem máscara) tem formato e DV válidos.

    Local e offline: não consulta a API nem diz se o CNPJ existe na base da Receita Federal.

    >>> cnpj_valido("12.ABC.345/01DE-35")
    True
    >>> cnpj_valido("12.ABC.345/01DE-36")
    False
    """
    return validar_local(entrada)["valido"]


def formatar_cnpj(entrada: Optional[str]) -> str:
    """Formata como ``AA.AAA.AAA/AAAA-DD``. Não confere os dígitos verificadores.

    Se a entrada normalizada não tiver 14 caracteres, devolve a entrada normalizada, sem máscara.

    >>> formatar_cnpj("11378117000120")
    '11.378.117/0001-20'
    """
    c = normalizar_cnpj(entrada)
    if len(c) != 14:
        return c
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
