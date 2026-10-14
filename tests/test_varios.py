import threading
import time
import unittest
from typing import Any, Dict, Iterator, List

from servidor_falso import NOT_FOUND, ServidorFalso, cnpj_da_url, documento, gerar_cnpjs, json_, rate_limited

from apipj import Apipj, ApipjErro, formatar_cnpj

LIVRE = {"X-RateLimit-Limit": "100", "X-RateLimit-Remaining": "99"}


class TestConsultarVarios(unittest.TestCase):
    srv: ServidorFalso

    @classmethod
    def setUpClass(cls) -> None:
        cls.srv = ServidorFalso()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.srv.fechar()

    def setUp(self) -> None:
        self.srv.limpar()

    def cliente(self, **opcoes: Any) -> Apipj:
        padrao: Dict[str, Any] = {"chave": "apipj_live_teste", "base_url": self.srv.url, "espera_base": 0.02}
        padrao.update(opcoes)
        return Apipj(**padrao)

    def test_deduplica_pula_invalidos_e_404_vira_none(self) -> None:
        a, b, c = gerar_cnpjs(3)

        def tratar(req: Any, n: int) -> Any:
            cnpj = cnpj_da_url(req["url"])
            if cnpj == c:
                return json_(404, NOT_FOUND)
            return json_(200, documento(cnpj), LIVRE)

        self.srv.tratador = tratar
        lista = [a, formatar_cnpj(a), b, "11378117000121", c, b, "12ABC34501DE36", "lixo", "00000000000000"]
        itens = list(self.cliente().consultar_varios(lista, simultaneas=2))

        self.assertEqual(len(self.srv.requisicoes), 3, "só os 3 válidos e distintos chamam a API")
        self.assertEqual(sorted(cnpj_da_url(r["url"]) for r in self.srv.requisicoes), sorted([a, b, c]))
        por_cnpj = {i["cnpj"]: i for i in itens}
        self.assertEqual(len(itens), 7)
        self.assertEqual(set(itens[0].keys()), {"cnpj", "documento", "erro"})
        self.assertEqual(por_cnpj[a]["documento"]["cnpj"], a)  # type: ignore[index]
        self.assertIsNone(por_cnpj[a]["erro"])
        self.assertIsNone(por_cnpj[c]["documento"])
        self.assertIsNone(por_cnpj[c]["erro"])
        for inv in ["11378117000121", "12ABC34501DE36", "LIXO", "00000000000000"]:
            self.assertIsNone(por_cnpj[inv]["documento"])
            erro = por_cnpj[inv]["erro"]
            self.assertIsInstance(erro, ApipjErro)
            assert erro is not None
            self.assertEqual(erro.code, "invalid_cnpj")
            self.assertEqual(erro.status, 400)

    def test_entrega_na_ordem_de_conclusao(self) -> None:
        # a primeira requisição (sonda do limite) sai sozinha; depois y (lento) e z (rápido) saem juntos
        x, y, z = gerar_cnpjs(3)

        def tratar(req: Any, n: int) -> Any:
            cnpj = cnpj_da_url(req["url"])
            time.sleep(0.3 if cnpj == y else 0.01)
            return json_(200, documento(cnpj), LIVRE)

        self.srv.tratador = tratar
        ordem = [i["cnpj"] for i in self.cliente().consultar_varios([x, y, z], simultaneas=2)]
        self.assertEqual(ordem, [x, z, y])

    def test_respeita_simultaneas(self) -> None:
        def tratar(req: Any, n: int) -> Any:
            time.sleep(0.03)
            return json_(200, documento(cnpj_da_url(req["url"])), {"X-RateLimit-Limit": "1000", "X-RateLimit-Remaining": "999"})

        self.srv.tratador = tratar
        itens = list(self.cliente().consultar_varios(gerar_cnpjs(12), simultaneas=3))
        self.assertEqual(len(itens), 12)
        self.assertLessEqual(self.srv.max_simultaneas, 3)
        self.assertGreaterEqual(self.srv.max_simultaneas, 2)

    def test_nunca_passa_do_limite_por_minuto(self) -> None:
        """Servidor conta violações do limite lido de X-RateLimit-* (janela reduzida para 1 s)."""
        limite = 5
        janela = 1.0
        chegadas: List[float] = []
        violacoes = [0]
        trava = threading.Lock()

        def tratar(req: Any, n: int) -> Any:
            with trava:
                agora = req["em"]
                # margem de 60 ms para a latência entre o cliente e o servidor
                na_janela = sum(1 for t in chegadas if t > agora - (janela - 0.06))
                chegadas.append(agora)
                if na_janela >= limite:
                    violacoes[0] += 1
                    return rate_limited(1)
            return json_(
                200,
                documento(cnpj_da_url(req["url"])),
                {"X-RateLimit-Limit": str(limite), "X-RateLimit-Remaining": str(limite - na_janela - 1), "X-RateLimit-Reset": "1"},
            )

        self.srv.tratador = tratar
        lista = gerar_cnpjs(16)
        t0 = time.monotonic()
        itens = list(self.cliente(janela=janela).consultar_varios(lista, simultaneas=10))
        dt = time.monotonic() - t0

        self.assertEqual(violacoes[0], 0, "o servidor não deveria ter respondido 429")
        self.assertEqual(len(itens), 16)
        self.assertTrue(all(i["documento"] and i["erro"] is None for i in itens))
        # 16 requisições a 5 por janela: 4 janelas, a última começa depois de 3 janelas
        self.assertGreaterEqual(dt, 3 * janela - 0.1, f"terminou rápido demais ({dt:.2f} s)")
        for t in chegadas:
            n = sum(1 for u in chegadas if t <= u < t + janela - 0.06)
            self.assertLessEqual(n, limite, f"{n} requisições numa janela")

    def test_opcao_rpm_limita_abaixo_do_plano(self) -> None:
        self.srv.tratador = lambda req, n: json_(
            200, documento(cnpj_da_url(req["url"])), {"X-RateLimit-Limit": "1000", "X-RateLimit-Remaining": "999"}
        )
        t0 = time.monotonic()
        itens = list(self.cliente(janela=0.5).consultar_varios(gerar_cnpjs(6), simultaneas=6, rpm=2))
        self.assertEqual(len(itens), 6)
        self.assertGreaterEqual(time.monotonic() - t0, 2 * 0.5 - 0.05, "com rpm 2 e 6 itens, precisa de 3 janelas")

    def test_remaining_zero_segura_o_lote(self) -> None:
        self.srv.tratador = lambda req, n: json_(
            200, documento(cnpj_da_url(req["url"])), {"X-RateLimit-Limit": "2", "X-RateLimit-Remaining": "0"}
        )
        t0 = time.monotonic()
        itens = list(self.cliente(janela=0.4).consultar_varios(gerar_cnpjs(3), simultaneas=3))
        self.assertEqual(len(itens), 3)
        r = self.srv.requisicoes
        self.assertGreaterEqual(r[1]["em"] - r[0]["em"], 0.19, "Remaining 0 bloqueia janela/limite")
        self.assertGreaterEqual(time.monotonic() - t0, 0.38)

    def test_429_rate_limited_no_meio_espera_e_completa(self) -> None:
        self.srv.tratador = lambda req, n: (
            rate_limited(1) if n == 3 else json_(200, documento(cnpj_da_url(req["url"])), {"X-RateLimit-Limit": "100", "X-RateLimit-Remaining": "50"})
        )
        itens = list(self.cliente().consultar_varios(gerar_cnpjs(5), simultaneas=1))
        self.assertEqual(len(itens), 5)
        self.assertTrue(all(i["documento"] for i in itens))
        self.assertEqual(len(self.srv.requisicoes), 6)
        self.assertGreaterEqual(self.srv.requisicoes[3]["em"] - self.srv.requisicoes[2]["em"], 0.95)

    def test_erro_de_um_cnpj_sai_no_item_e_o_lote_continua(self) -> None:
        lista = gerar_cnpjs(3)

        def tratar(req: Any, n: int) -> Any:
            cnpj = cnpj_da_url(req["url"])
            if cnpj == lista[1]:
                return json_(503, {"status": "ERROR", "message": "Base indisponível", "code": "dataset_unavailable"})
            return json_(200, documento(cnpj), LIVRE)

        self.srv.tratador = tratar
        itens = list(self.cliente(tentativas=2).consultar_varios(lista))
        ruim = next(i for i in itens if i["cnpj"] == lista[1])
        self.assertIsNone(ruim["documento"])
        assert ruim["erro"] is not None
        self.assertEqual(ruim["erro"].code, "dataset_unavailable")
        self.assertEqual(sum(1 for i in itens if i["documento"]), 2)

    def test_401_interrompe_o_lote(self) -> None:
        self.srv.tratador = lambda req, n: json_(401, {"status": "ERROR", "message": "Chave de API inválida ou revogada", "code": "unauthorized"})
        with self.assertRaises(ApipjErro) as ctx:
            list(self.cliente().consultar_varios(gerar_cnpjs(20)))
        self.assertEqual(ctx.exception.code, "unauthorized")
        time.sleep(0.15)
        self.assertEqual(len(self.srv.requisicoes), 1, "a sonda falhou; ninguém mais chamou a API")

    def test_sem_chave_usa_a_consulta_sem_chave_e_para_no_limite_do_dia(self) -> None:
        cad = "https://apipj.com.br/criar-conta?origem=api-lib-pypi-apipj"
        self.srv.tratador = lambda req, n: json_(
            429,
            {"status": "ERROR", "message": "Limite diário sem chave de API: 100 consultas.", "code": "quota_exceeded", "signup_url": cad, "reset": 1793502000},
        )
        api = Apipj(chave=None, base_url=self.srv.url, avisos=False)
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("APIPJ_KEY", None)
            with self.assertRaises(ApipjErro) as ctx:
                list(api.consultar_varios(gerar_cnpjs(5), simultaneas=1))
        self.assertEqual(ctx.exception.code, "quota_exceeded")
        self.assertEqual(ctx.exception.signup_url, cad)
        self.assertGreaterEqual(len(self.srv.requisicoes), 1)
        self.assertTrue(all("authorization" not in r["headers"] for r in self.srv.requisicoes), "sem chave: sem Authorization")

    def test_cota_esgotada_entrega_o_que_ficou_pronto_e_lanca(self) -> None:
        self.srv.tratador = lambda req, n: (
            json_(200, documento(cnpj_da_url(req["url"])), LIVRE)
            if n <= 2
            else json_(429, {"status": "ERROR", "message": "Cota mensal esgotada", "code": "quota_exceeded", "upgrade_url": "https://apipj.com.br/precos"})
        )
        vistos = []
        with self.assertRaises(ApipjErro) as ctx:
            for r in self.cliente().consultar_varios(gerar_cnpjs(30), simultaneas=1):
                vistos.append(r)
        self.assertEqual(ctx.exception.code, "quota_exceeded")
        self.assertEqual(ctx.exception.upgrade_url, "https://apipj.com.br/precos")
        time.sleep(0.15)
        self.assertEqual(len(vistos), 2)
        self.assertEqual(len(self.srv.requisicoes), 3)

    def test_break_para_de_chamar_a_api(self) -> None:
        def tratar(req: Any, n: int) -> Any:
            time.sleep(0.02)
            return json_(200, documento(cnpj_da_url(req["url"])), LIVRE)

        self.srv.tratador = tratar
        gerador = self.cliente().consultar_varios(gerar_cnpjs(50), simultaneas=2)
        for r in gerador:
            self.assertIsNotNone(r["documento"])
            break
        gerador.close()  # o que o CPython faz sozinho quando o gerador sai de escopo
        time.sleep(0.2)
        self.assertLessEqual(len(self.srv.requisicoes), 4, f"{len(self.srv.requisicoes)} requisições depois do break")

    def test_aceita_gerador_e_nao_chama_antes_de_ler(self) -> None:
        self.srv.tratador = lambda req, n: json_(200, documento(cnpj_da_url(req["url"])), LIVRE)
        lista = gerar_cnpjs(4)

        def gerar() -> Iterator[str]:
            for c in lista:
                time.sleep(0.005)
                yield c

        it = self.cliente().consultar_varios(gerar(), simultaneas=2)
        time.sleep(0.1)
        self.assertEqual(len(self.srv.requisicoes), 0, "nada começa antes da primeira leitura")
        self.assertEqual(sorted(i["cnpj"] for i in it), sorted(lista))

    def test_erro_no_iteravel_de_entrada_propaga(self) -> None:
        self.srv.tratador = lambda req, n: json_(200, documento(cnpj_da_url(req["url"])), LIVRE)
        a, b = gerar_cnpjs(2)

        def gerar() -> Iterator[str]:
            yield a
            raise RuntimeError("arquivo corrompido")

        with self.assertRaisesRegex(RuntimeError, "arquivo corrompido"):
            list(self.cliente().consultar_varios(gerar(), simultaneas=1))

    def test_string_no_lugar_da_lista_e_erro_de_uso(self) -> None:
        with self.assertRaises(TypeError):
            self.cliente().consultar_varios("11378117000120")
        with self.assertRaises(TypeError):
            self.cliente().consultar_varios(None)  # type: ignore[call-overload]
        with self.assertRaises(ApipjErro):
            self.cliente().consultar_varios([], formato="xml")  # type: ignore[call-overload]

    def test_lista_vazia(self) -> None:
        self.assertEqual(list(self.cliente().consultar_varios([])), [])
        self.assertEqual(len(self.srv.requisicoes), 0)

    def test_nao_deixa_threads_para_tras(self) -> None:
        self.srv.tratador = lambda req, n: json_(200, documento(cnpj_da_url(req["url"])), LIVRE)
        list(self.cliente().consultar_varios(gerar_cnpjs(8), simultaneas=4))
        time.sleep(0.2)
        vivas = [t for t in threading.enumerate() if t.name.startswith("apipj-lote-")]
        self.assertEqual(vivas, [])


if __name__ == "__main__":
    unittest.main()
