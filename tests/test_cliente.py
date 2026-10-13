import os
import pickle
import time
import unittest
from email.utils import formatdate
from typing import Any, Dict
from unittest import mock

from servidor_falso import NOT_FOUND, ServidorFalso, documento, json_, rate_limited

import apipj
from apipj import Apipj, ApipjErro
from apipj.cliente import _segundos_retry_after

CHAVE = "apipj_live_teste"
CNPJ = "11378117000120"
UA = f"apipj-python/{apipj.__version__}"


class Base(unittest.TestCase):
    srv: ServidorFalso

    @classmethod
    def setUpClass(cls) -> None:
        cls.srv = ServidorFalso()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.srv.fechar()

    def setUp(self) -> None:
        self.srv.limpar()
        self.srv.tratador = lambda req, n: json_(200, {})

    def cliente(self, **opcoes: Any) -> Apipj:
        padrao: Dict[str, Any] = {"chave": CHAVE, "base_url": self.srv.url, "espera_base": 0.02}
        padrao.update(opcoes)
        return Apipj(**padrao)

    def assertErro(self, ctx: Any, **esperado: Any) -> ApipjErro:
        e = ctx.exception
        self.assertIsInstance(e, ApipjErro)
        for k, v in esperado.items():
            self.assertEqual(getattr(e, k), v, k)
        return e


class TestConsultar(Base):
    def test_normaliza_manda_chave_e_user_agent_e_guarda_limites(self) -> None:
        self.srv.tratador = lambda req, n: json_(
            200,
            documento(CNPJ),
            {
                "X-RateLimit-Limit": "10",
                "X-RateLimit-Remaining": "9",
                "X-RateLimit-Reset": "6",
                "X-Quota-Limit": "50000",
                "X-Quota-Remaining": "49999",
                "X-Quota-Reset": "1793502000",
            },
        )
        api = self.cliente()
        self.assertIsNone(api.limites)
        doc = api.consultar("11.378.117/0001-20")
        assert doc is not None
        self.assertEqual(doc["cnpj"], CNPJ)
        self.assertEqual(len(self.srv.requisicoes), 1)
        r = self.srv.requisicoes[0]
        self.assertEqual(r["url"], f"/v1/cnpj/{CNPJ}")
        self.assertEqual(r["headers"]["authorization"], f"Bearer {CHAVE}")
        self.assertEqual(r["headers"]["user-agent"], UA)
        self.assertEqual(r["headers"]["accept"], "application/json")
        self.assertEqual(
            api.limites,
            {
                "por_minuto": {"limite": 10, "restante": 9, "reset": 6},
                "mensal": {"limite": 50000, "restante": 49999, "reset": 1793502000},
            },
        )

    def test_simplificado_na_query_e_alfanumerico_normalizado(self) -> None:
        self.srv.tratador = lambda req, n: json_(200, {"cnpj": "12.ABC.345/01DE-35", "nome": "X"})
        doc = self.cliente().consultar("12.abc.345/01de-35", formato="simplificado")
        assert doc is not None
        self.assertEqual(doc["nome"], "X")
        self.assertEqual(self.srv.requisicoes[0]["url"], "/v1/cnpj/12ABC34501DE35?formato=simplificado")

    def test_cnpj_invalido_lanca_sem_chamar_a_api(self) -> None:
        api = self.cliente()
        with self.assertRaises(ApipjErro) as ctx:
            api.consultar("11.378.117/0001-21")
        self.assertErro(ctx, status=400, code="invalid_cnpj", cnpj="11378117000121", message="Dígitos verificadores inválidos")
        for entrada in ["12ABC34501DE36", "00000000000000", "12ABC34501DE3A", "123", ""]:
            with self.assertRaises(ApipjErro) as ctx:
                api.consultar(entrada)
            self.assertErro(ctx, status=400, code="invalid_cnpj")
        with self.assertRaises(ApipjErro) as ctx:
            api.consultar(CNPJ, formato="xml")  # type: ignore[call-overload]
        self.assertErro(ctx, status=400, code="validation_error")
        self.assertEqual(len(self.srv.requisicoes), 0)

    def test_chave_lida_do_ambiente_so_na_hora(self) -> None:
        self.srv.tratador = lambda req, n: json_(200, documento(CNPJ))
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("APIPJ_KEY", None)
            api = Apipj(base_url=self.srv.url)
            with self.assertRaises(ApipjErro) as ctx:
                api.consultar(CNPJ)
            e = self.assertErro(ctx, status=401, code="unauthorized")
            self.assertIn("APIPJ_KEY", e.message)
            self.assertEqual(len(self.srv.requisicoes), 0)
            os.environ["APIPJ_KEY"] = "apipj_live_do_ambiente\n"
            api.consultar(CNPJ)
            self.assertEqual(self.srv.requisicoes[0]["headers"]["authorization"], "Bearer apipj_live_do_ambiente")

    def test_chave_nao_aparece_no_repr(self) -> None:
        api = self.cliente()
        self.assertNotIn(CHAVE, repr(api))
        self.assertNotIn(CHAVE, str(api))
        self.assertNotIn(CHAVE, repr(vars(api)))
        self.assertNotIn(CHAVE, str(vars(api)))
        self.assertIn("chave=definida", repr(api))

    def test_404_not_found_vira_none(self) -> None:
        self.srv.tratador = lambda req, n: json_(404, NOT_FOUND)
        self.assertIsNone(self.cliente().consultar(CNPJ))
        self.assertEqual(len(self.srv.requisicoes), 1)

    def test_404_sem_corpo_da_api_lanca(self) -> None:
        self.srv.tratador = lambda req, n: (404, "<h1>404</h1>", {})
        with self.assertRaises(ApipjErro) as ctx:
            self.cliente().consultar(CNPJ)
        self.assertErro(ctx, status=404, code="not_found")

    def test_400_e_401_lancam_sem_repetir(self) -> None:
        self.srv.tratador = lambda req, n: json_(
            400, {"status": "ERROR", "message": "Dígitos verificadores inválidos", "code": "invalid_cnpj", "cnpj": CNPJ}
        )
        with self.assertRaises(ApipjErro) as ctx:
            self.cliente().consultar(CNPJ)
        self.assertErro(ctx, status=400, code="invalid_cnpj", cnpj=CNPJ, message="Dígitos verificadores inválidos")
        self.assertEqual(len(self.srv.requisicoes), 1)

        self.srv.limpar()
        self.srv.tratador = lambda req, n: json_(
            401, {"status": "ERROR", "message": "Chave de API inválida ou revogada", "code": "unauthorized"}
        )
        with self.assertRaises(ApipjErro) as ctx:
            self.cliente().consultar(CNPJ)
        e = self.assertErro(ctx, status=401, code="unauthorized", message="Chave de API inválida ou revogada")
        self.assertEqual(str(e), "401 unauthorized: Chave de API inválida ou revogada")
        self.assertEqual(len(self.srv.requisicoes), 1)

    def test_quota_exceeded_lanca_na_hora(self) -> None:
        self.srv.tratador = lambda req, n: json_(
            429,
            {
                "status": "ERROR",
                "message": "Cota mensal esgotada",
                "code": "quota_exceeded",
                "upgrade_url": "https://apipj.com.br/precos",
                "reset": 1793502000,
            },
        )
        with self.assertRaises(ApipjErro) as ctx:
            self.cliente().consultar(CNPJ)
        self.assertErro(
            ctx, status=429, code="quota_exceeded", upgrade_url="https://apipj.com.br/precos", reset=1793502000, retry_after=None
        )
        self.assertEqual(len(self.srv.requisicoes), 1)

    def test_rate_limited_espera_retry_after_e_repete(self) -> None:
        self.srv.tratador = lambda req, n: rate_limited(1) if n == 1 else json_(200, documento(CNPJ))
        t0 = time.monotonic()
        doc = self.cliente().consultar(CNPJ)
        dt = time.monotonic() - t0
        assert doc is not None
        self.assertEqual(doc["cnpj"], CNPJ)
        self.assertEqual(len(self.srv.requisicoes), 2)
        self.assertGreaterEqual(dt, 0.95)
        self.assertGreaterEqual(self.srv.requisicoes[1]["em"] - self.srv.requisicoes[0]["em"], 0.95)

    def test_rate_limited_esgota_tentativas(self) -> None:
        self.srv.tratador = lambda req, n: rate_limited(0)
        with self.assertRaises(ApipjErro) as ctx:
            self.cliente(tentativas=3).consultar(CNPJ)
        self.assertErro(ctx, status=429, code="rate_limited", retry_after=0)
        self.assertEqual(len(self.srv.requisicoes), 3)

    def test_sem_retry_after_no_cabecalho_usa_o_do_corpo(self) -> None:
        self.srv.tratador = lambda req, n: json_(429, {"status": "ERROR", "message": "Limite", "code": "rate_limited", "retry_after": 0})
        with self.assertRaises(ApipjErro) as ctx:
            self.cliente(tentativas=2).consultar(CNPJ)
        self.assertErro(ctx, code="rate_limited", retry_after=0)
        self.assertEqual(len(self.srv.requisicoes), 2)

    def test_retry_after_em_data_http(self) -> None:
        self.assertEqual(_segundos_retry_after("5"), 5)
        self.assertEqual(_segundos_retry_after("-3"), 0)
        self.assertIsNone(_segundos_retry_after(""))
        self.assertIsNone(_segundos_retry_after("amanhã"))
        s = _segundos_retry_after(formatdate(time.time() + 30, usegmt=True))
        assert s is not None
        self.assertTrue(28 <= s <= 31, s)

    def test_5xx_repete_com_backoff_e_lanca(self) -> None:
        self.srv.tratador = lambda req, n: json_(
            503, {"status": "ERROR", "message": "Base de CNPJ indisponível no momento", "code": "dataset_unavailable"}
        )
        t0 = time.monotonic()
        with self.assertRaises(ApipjErro) as ctx:
            self.cliente(tentativas=3, espera_base=0.04).consultar(CNPJ)
        self.assertErro(ctx, status=503, code="dataset_unavailable")
        self.assertEqual(len(self.srv.requisicoes), 3)
        self.assertGreaterEqual(time.monotonic() - t0, 0.04 + 0.08 - 0.01)

    def test_5xx_sem_json_vira_server_error(self) -> None:
        self.srv.tratador = lambda req, n: (502, "<html>bad gateway</html>", {})
        with self.assertRaises(ApipjErro) as ctx:
            self.cliente(tentativas=1).consultar(CNPJ)
        e = self.assertErro(ctx, status=502, code="server_error")
        self.assertEqual(e.corpo, "<html>bad gateway</html>")

    def test_backoff_padrao_1s_e_2s(self) -> None:
        self.srv.tratador = lambda req, n: (
            json_(500, {"status": "ERROR", "message": "x", "code": "internal"}) if n < 3 else json_(200, documento(CNPJ))
        )
        api = Apipj(chave=CHAVE, base_url=self.srv.url)
        doc = api.consultar(CNPJ)
        assert doc is not None
        self.assertEqual(doc["cnpj"], CNPJ)
        a, b, c = (r["em"] for r in self.srv.requisicoes)
        self.assertGreaterEqual(b - a, 0.95, "1º intervalo")
        self.assertGreaterEqual(c - b, 1.95, "2º intervalo")

    def test_falha_de_rede_repete_e_lanca_network_error(self) -> None:
        api = Apipj(chave=CHAVE, base_url="http://127.0.0.1:1", tentativas=2, espera_base=0.01)
        with self.assertRaises(ApipjErro) as ctx:
            api.consultar(CNPJ)
        e = self.assertErro(ctx, status=0, code="network_error")
        self.assertIsNotNone(e.__cause__)

    def test_tempo_esgotado_lanca_timeout(self) -> None:
        def lento(req: Any, n: int) -> Any:
            time.sleep(0.5)
            return json_(200, documento(CNPJ))

        self.srv.tratador = lento
        t0 = time.monotonic()
        with self.assertRaises(ApipjErro) as ctx:
            self.cliente(timeout=0.1, tentativas=2).consultar(CNPJ)
        self.assertErro(ctx, status=0, code="timeout")
        self.assertEqual(len(self.srv.requisicoes), 2, "timeout também repete")
        self.assertLess(time.monotonic() - t0, 0.9)

    def test_validar_status_e_planos_nao_mandam_a_chave(self) -> None:
        def tratar(req: Any, n: int) -> Any:
            url = req["url"]
            if url.startswith("/v1/valida/"):
                return json_(200, {"cnpj": "12ABC34501DE35", "valido": True, "formatado": "12.ABC.345/01DE-35", "alfanumerico": True, "erro": None})
            if url == "/v1/status":
                return json_(200, {"status": "OK", "dataset_month": "2026-09", "rows": 1, "version": "0.1.0", "time": "x"})
            if url == "/v1/plans":
                return json_(200, {"currency": "BRL", "plans": [{"id": "free", "rpm": 10}]})
            return json_(404, NOT_FOUND)

        self.srv.tratador = tratar
        api = self.cliente()
        self.assertTrue(api.validar("12.abc.345/01de-35")["valido"])
        self.assertEqual(api.status()["status"], "OK")
        self.assertEqual(api.planos()["plans"][0]["id"], "free")
        self.assertEqual([r["url"] for r in self.srv.requisicoes], ["/v1/valida/12ABC34501DE35", "/v1/status", "/v1/plans"])
        for r in self.srv.requisicoes:
            self.assertNotIn("authorization", r["headers"])
            self.assertEqual(r["headers"]["user-agent"], UA)
        self.assertIsNone(api.limites)

    def test_validar_vazio_responde_localmente(self) -> None:
        v = self.cliente().validar("")
        self.assertFalse(v["valido"])
        self.assertEqual(len(self.srv.requisicoes), 0)

    def test_status_repete_em_429_por_ip(self) -> None:
        self.srv.tratador = lambda req, n: rate_limited(0) if n == 1 else json_(200, {"status": "OK"})
        self.assertEqual(self.cliente().status()["status"], "OK")
        self.assertEqual(len(self.srv.requisicoes), 2)

    def test_resposta_200_que_nao_e_json(self) -> None:
        self.srv.tratador = lambda req, n: (200, "ok", {})
        with self.assertRaises(ApipjErro) as ctx:
            self.cliente().status()
        self.assertErro(ctx, code="invalid_response")

    def test_chave_nao_segue_redirecionamento(self) -> None:
        self.srv.tratador = lambda req, n: (
            (302, "", {"Location": "/outro-lugar"}) if n == 1 else json_(404, NOT_FOUND)
        )
        self.assertIsNone(self.cliente().consultar(CNPJ))
        self.assertEqual(self.srv.requisicoes[1]["url"], "/outro-lugar")
        self.assertIn("authorization", self.srv.requisicoes[0]["headers"])
        self.assertNotIn("authorization", self.srv.requisicoes[1]["headers"])

    def test_base_url_sem_barra_no_fim(self) -> None:
        self.srv.tratador = lambda req, n: json_(200, {"status": "OK"})
        api = Apipj(base_url=self.srv.url + "//")
        self.assertEqual(api.base_url, self.srv.url)
        api.status()
        self.assertEqual(self.srv.requisicoes[0]["url"], "/v1/status")


class TestErro(unittest.TestCase):
    def test_pickle_preserva_os_campos(self) -> None:
        e = ApipjErro(429, "quota_exceeded", "Cota mensal esgotada", upgrade_url="https://apipj.com.br/precos", reset=1)
        e2 = pickle.loads(pickle.dumps(e))
        self.assertEqual((e2.status, e2.code, e2.message, e2.upgrade_url, e2.reset), (429, "quota_exceeded", "Cota mensal esgotada", "https://apipj.com.br/precos", 1))
        self.assertIn("quota_exceeded", repr(e2))


if __name__ == "__main__":
    unittest.main()
