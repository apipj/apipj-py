"""Limitador de vazão do ``consultar_varios``.

Janela deslizante de ``limite`` inícios de requisição por ``janela`` segundos (60 s), com o limite
lido de ``X-RateLimit-Limit``. A primeira requisição sai sozinha (sonda) para descobrir o limite do
plano antes de liberar as demais.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from typing import Deque, Optional


class Cancelado(Exception):
    """O lote foi encerrado (erro fatal ou o consumidor parou de ler): não começar nada novo."""


class Limitador:
    def __init__(self, rpm: Optional[int] = None, janela: float = 60.0) -> None:
        #: limite pedido pelo usuário (pode ser menor que o do plano)
        self.rpm_usuario: Optional[int] = int(rpm) if rpm is not None and rpm > 0 else None
        #: limite efetivo; ``None`` até a primeira resposta (sem cabeçalho = sem limite local)
        self.limite: Optional[int] = self.rpm_usuario
        self.janela = float(janela)
        self._inicios: Deque[float] = deque()
        self._bloqueado_ate = 0.0
        self._conhecido = False
        self._sondando = False
        self._encerrado = False
        self._cond = threading.Condition()

    @property
    def encerrado(self) -> bool:
        return self._encerrado

    def aguardar(self) -> None:
        """Bloqueia até uma nova requisição poder começar (e já a registra na janela)."""
        with self._cond:
            while True:
                if self._encerrado:
                    raise Cancelado()
                if not self._conhecido:
                    if not self._sondando:
                        self._sondando = True
                        self._inicios.append(time.monotonic())
                        return
                    self._cond.wait()
                    continue
                agora = time.monotonic()
                while self._inicios and self._inicios[0] <= agora - self.janela:
                    self._inicios.popleft()
                espera = max(0.0, self._bloqueado_ate - agora)
                if self.limite and len(self._inicios) >= self.limite:
                    espera = max(espera, self._inicios[-self.limite] + self.janela - agora)
                if espera <= 0:
                    self._inicios.append(agora)
                    return
                self._cond.wait(espera)

    def registrar(self, limite: Optional[int], restante: Optional[int]) -> None:
        """Registra o resultado de uma tentativa (cabeçalhos ``X-RateLimit-*``, ou ``None`` sem resposta)."""
        with self._cond:
            if limite is not None and limite > 0:
                self.limite = min(self.rpm_usuario, limite) if self.rpm_usuario else limite
                if restante == 0:
                    self._bloquear(self.janela / limite)
            if not self._conhecido:
                self._conhecido = True
            self._cond.notify_all()

    def bloquear(self, segundos: float) -> None:
        """Ninguém começa nada nos próximos ``segundos`` (Retry-After, Remaining = 0)."""
        with self._cond:
            self._bloquear(segundos)

    def _bloquear(self, segundos: float) -> None:
        if math.isfinite(segundos) and segundos > 0:
            self._bloqueado_ate = max(self._bloqueado_ate, time.monotonic() + segundos)

    def encerrar(self) -> None:
        """Cancela as esperas em curso e as futuras."""
        with self._cond:
            self._encerrado = True
            self._cond.notify_all()

    def dormir(self, segundos: float) -> None:
        """Espera ``segundos``, acordando antes (com :class:`Cancelado`) se o lote for encerrado."""
        fim = time.monotonic() + max(0.0, segundos)
        with self._cond:
            while True:
                if self._encerrado:
                    raise Cancelado()
                falta = fim - time.monotonic()
                if falta <= 0:
                    return
                self._cond.wait(falta)
