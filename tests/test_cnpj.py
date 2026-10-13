import re
import unittest
from pathlib import Path

import apipj
from apipj import calcular_dv, cnpj_valido, formatar_cnpj, normalizar_cnpj, validar_local


def dv_independente(base: str) -> str:
    """Cálculo à mão, separado da implementação, para conferir o DV."""
    pesos = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    def um(s: str, p: list) -> int:
        resto = sum((ord(ch) - 48) * p[i] for i, ch in enumerate(s)) % 11
        return 0 if resto < 2 else 11 - resto

    d1 = um(base, pesos[1:])
    d2 = um(base + str(d1), pesos)
    return f"{d1}{d2}"


class TestCnpj(unittest.TestCase):
    def test_numericos_validos(self) -> None:
        for c in ["11378117000120", "11.378.117/0001-20", "00.000.000/0001-91", "11.222.333/0001-81", " 11 222 333 0001 81 "]:
            self.assertTrue(cnpj_valido(c), c)

    def test_numericos_invalidos(self) -> None:
        for c in ["11378117000121", "11.378.117/0001-02", "00000000000000", "00.000.000/0000-00", "", "1137811700012", "113781170001200"]:
            self.assertFalse(cnpj_valido(c), c)
        self.assertFalse(cnpj_valido(None))

    def test_alfanumerico_35_valido_36_invalido(self) -> None:
        self.assertEqual(calcular_dv("12ABC34501DE"), "35")
        self.assertTrue(cnpj_valido("12ABC34501DE35"))
        self.assertTrue(cnpj_valido("12.ABC.345/01DE-35"))
        self.assertTrue(cnpj_valido("12.abc.345/01de-35"), "minúsculas são aceitas")
        self.assertFalse(cnpj_valido("12ABC34501DE36"))
        self.assertFalse(cnpj_valido("12.ABC.345/01DE-36"))

    def test_alfanumerico_valor_ascii_menos_48(self) -> None:
        for base in ["12ABC34501DE", "AAAAAAAAAAAA", "ZZZZZZZZ0001", "0000000A0001", "X1Y2Z3W40001", "112223330001", "000000000001"]:
            self.assertEqual(calcular_dv(base), dv_independente(base), base)
            self.assertTrue(cnpj_valido(base + dv_independente(base)), base)

    def test_zerado_letra_no_dv_caractere_e_tamanho(self) -> None:
        casos = {
            "12ABC34501DE3A": "Os dois últimos caracteres (dígitos verificadores) devem ser numéricos",
            "12ABC34501DEAB": "Os dois últimos caracteres (dígitos verificadores) devem ser numéricos",
            "12ABC34501D$35": "CNPJ contém caracteres inválidos (permitidos: letras A-Z e dígitos)",
            "12ABC34501DÉ35": "CNPJ contém caracteres inválidos (permitidos: letras A-Z e dígitos)",
            "12ABC34501DE3": "CNPJ deve ter 14 caracteres (recebido 13)",
            "12ABC34501DE355": "CNPJ deve ter 14 caracteres (recebido 15)",
            "": "CNPJ vazio",
            "00000000000000": "CNPJ zerado é inválido",
            "00.000.000/0000-00": "CNPJ zerado é inválido",
            "12ABC34501DE36": "Dígitos verificadores inválidos",
        }
        for entrada, erro in casos.items():
            v = validar_local(entrada)
            self.assertFalse(v["valido"], entrada)
            self.assertEqual(v["erro"], erro, entrada)
            self.assertIsNone(v["formatado"])
            self.assertFalse(v["alfanumerico"])

    def test_validar_local_mesmo_formato_da_api(self) -> None:
        self.assertEqual(
            validar_local("12.abc.345/01de-35"),
            {"cnpj": "12ABC34501DE35", "valido": True, "formatado": "12.ABC.345/01DE-35", "alfanumerico": True, "erro": None},
        )
        self.assertEqual(
            validar_local("11378117000120"),
            {"cnpj": "11378117000120", "valido": True, "formatado": "11.378.117/0001-20", "alfanumerico": False, "erro": None},
        )

    def test_normalizar_e_formatar(self) -> None:
        self.assertEqual(normalizar_cnpj("12.abc.345/01de-35"), "12ABC34501DE35")
        self.assertEqual(normalizar_cnpj(" 11.378.117/0001-20 "), "11378117000120")
        self.assertEqual(normalizar_cnpj(None), "")
        self.assertEqual(formatar_cnpj("11378117000120"), "11.378.117/0001-20")
        self.assertEqual(formatar_cnpj("12abc34501de35"), "12.ABC.345/01DE-35")
        self.assertEqual(formatar_cnpj("123"), "123")

    def test_calcular_dv_recusa_base_errada(self) -> None:
        for base in ["12ABC34501D", "12ABC34501D$", ""]:
            with self.assertRaises(ValueError):
                calcular_dv(base)

    def test_versao_acompanha_pyproject(self) -> None:
        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"), re.M)
        assert m is not None
        self.assertEqual(apipj.__version__, m.group(1))


if __name__ == "__main__":
    unittest.main()
