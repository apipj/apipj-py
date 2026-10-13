"""apipj: cliente oficial da API de CNPJ do apipj (https://apipj.com.br).

Consulta CNPJ (dados abertos da Receita Federal), valida CNPJ numérico e alfanumérico e consulta em
lote respeitando o limite por minuto do plano. Sem dependências.

>>> from apipj import Apipj, cnpj_valido
>>> cnpj_valido("12.ABC.345/01DE-35")
True
"""

from ._versao import __version__
from .cliente import Apipj
from .cnpj import calcular_dv, cnpj_valido, formatar_cnpj, normalizar_cnpj, validar_local
from .erro import ApipjErro
from .tipos import (
    AtividadeSimplificada,
    CobrancaPlanos,
    CodigoDescricao,
    EmpresaCompleta,
    EmpresaSimplificada,
    Endereco,
    Formato,
    LimiteJanela,
    Limites,
    Municipio,
    OpcaoRegime,
    Plano,
    Planos,
    RegimeSimplificado,
    RepresentanteLegal,
    ResultadoLote,
    ResultadoLoteSimplificado,
    SituacaoCadastral,
    SituacaoEspecial,
    Socio,
    SocioSimplificado,
    Status,
    Telefone,
    Validacao,
)

__all__ = [
    "__version__",
    "Apipj",
    "ApipjErro",
    "cnpj_valido",
    "normalizar_cnpj",
    "formatar_cnpj",
    "calcular_dv",
    "validar_local",
    "AtividadeSimplificada",
    "CobrancaPlanos",
    "CodigoDescricao",
    "EmpresaCompleta",
    "EmpresaSimplificada",
    "Endereco",
    "Formato",
    "LimiteJanela",
    "Limites",
    "Municipio",
    "OpcaoRegime",
    "Plano",
    "Planos",
    "RegimeSimplificado",
    "RepresentanteLegal",
    "ResultadoLote",
    "ResultadoLoteSimplificado",
    "SituacaoCadastral",
    "SituacaoEspecial",
    "Socio",
    "SocioSimplificado",
    "Status",
    "Telefone",
    "Validacao",
]
