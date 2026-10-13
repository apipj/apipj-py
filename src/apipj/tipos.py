"""Tipos das respostas da API (``TypedDict``), conferidos com https://apipj.com.br/openapi-publica.json.

Em tempo de execução as respostas são ``dict`` comuns; os tipos servem ao editor e ao mypy/pyright.
No formato ``completo``, campos ausentes na base da Receita vêm como ``None``: nenhuma chave some.
"""

from typing import Any, Dict, List, Literal, Optional, TypedDict

from .erro import ApipjErro

__all__ = [
    "Formato",
    "CodigoDescricao",
    "Telefone",
    "OpcaoRegime",
    "RepresentanteLegal",
    "Socio",
    "Municipio",
    "Endereco",
    "SituacaoCadastral",
    "SituacaoEspecial",
    "EmpresaCompleta",
    "AtividadeSimplificada",
    "SocioSimplificado",
    "RegimeSimplificado",
    "EmpresaSimplificada",
    "Validacao",
    "Status",
    "Plano",
    "CobrancaPlanos",
    "Planos",
    "LimiteJanela",
    "Limites",
    "ResultadoLote",
    "ResultadoLoteSimplificado",
]

Formato = Literal["completo", "simplificado"]
"""Formato da resposta de ``consultar``: ``completo`` (padrão) ou ``simplificado``."""


# ------------------------------------------------------------------ formato completo


class CodigoDescricao(TypedDict):
    """Par código/descrição da Receita Federal."""

    codigo: Optional[str]
    descricao: Optional[str]


class Telefone(TypedDict):
    ddd: Optional[str]
    numero: Optional[str]
    """Número, só dígitos."""


class OpcaoRegime(TypedDict):
    """Opção pelo Simples Nacional ou pelo MEI."""

    optante: bool
    data_opcao: Optional[str]
    """AAAA-MM-DD"""
    data_exclusao: Optional[str]
    """AAAA-MM-DD"""


class RepresentanteLegal(TypedDict):
    cpf: Optional[str]
    """CPF mascarado."""
    nome: Optional[str]
    qualificacao: Optional[CodigoDescricao]


class Socio(TypedDict):
    nome: Optional[str]
    tipo: Optional[str]
    """PESSOA FISICA, PESSOA JURIDICA ou ESTRANGEIRO."""
    cpf_cnpj: Optional[str]
    """CPF já mascarado pela Receita (***123456**) ou raiz de 8 caracteres do CNPJ do sócio pessoa jurídica."""
    qualificacao: Optional[CodigoDescricao]
    data_entrada: Optional[str]
    """Entrada na sociedade (AAAA-MM-DD)."""
    faixa_etaria: Optional[str]
    pais: Optional[str]
    """País (sócio estrangeiro)."""
    representante_legal: Optional[RepresentanteLegal]


class Municipio(TypedDict):
    codigo_rfb: Optional[str]
    """Código do município na Receita Federal."""
    codigo_ibge: Optional[str]
    """Código IBGE (7 dígitos)."""
    nome: Optional[str]


class Endereco(TypedDict):
    tipo_logradouro: Optional[str]
    """RUA, AVENIDA..."""
    logradouro: Optional[str]
    numero: Optional[str]
    complemento: Optional[str]
    bairro: Optional[str]
    cep: Optional[str]
    """CEP, só dígitos."""
    municipio: Municipio
    uf: Optional[str]
    pais: Optional[str]
    """País (endereço no exterior)."""
    cidade_exterior: Optional[str]


class SituacaoCadastral(TypedDict):
    codigo: Optional[str]
    descricao: Optional[str]
    """ATIVA, BAIXADA, INAPTA, SUSPENSA ou NULA."""
    data: Optional[str]
    """Data da situação (AAAA-MM-DD)."""
    motivo: Optional[CodigoDescricao]


class SituacaoEspecial(TypedDict):
    descricao: Optional[str]
    data: Optional[str]
    """AAAA-MM-DD"""


class EmpresaCompleta(TypedDict):
    """Documento no formato ``completo`` (padrão)."""

    cnpj: str
    """14 caracteres, sem pontuação."""
    cnpj_formatado: str
    """AA.AAA.AAA/AAAA-DD"""
    razao_social: str
    nome_fantasia: Optional[str]
    matriz_filial: str
    """MATRIZ ou FILIAL."""
    situacao_cadastral: SituacaoCadastral
    situacao_especial: SituacaoEspecial
    data_inicio_atividade: Optional[str]
    """Início da atividade (AAAA-MM-DD)."""
    natureza_juridica: Optional[CodigoDescricao]
    qualificacao_responsavel: Optional[CodigoDescricao]
    porte: Optional[CodigoDescricao]
    capital_social: Optional[float]
    """Capital social em reais."""
    cnae_principal: Optional[CodigoDescricao]
    cnaes_secundarios: List[CodigoDescricao]
    endereco: Endereco
    telefones: List[Telefone]
    fax: Optional[Telefone]
    email: Optional[str]
    ente_federativo_responsavel: Optional[str]
    """Ente federativo responsável (administração pública)."""
    simples: OpcaoRegime
    mei: OpcaoRegime
    socios: List[Socio]
    atualizado_em: str
    """Mês do lote da Receita Federal (AAAA-MM)."""


# ------------------------------------------------------------------ formato simplificado


class AtividadeSimplificada(TypedDict):
    code: str
    """CNAE com máscara, por exemplo 62.01-5-01."""
    text: str


class SocioSimplificado(TypedDict):
    nome: str
    qual: str
    """Código e descrição da qualificação, por exemplo ``10-Diretor``."""
    pais_origem: str
    nome_rep_legal: str
    qual_rep_legal: str


class RegimeSimplificado(TypedDict):
    optante: bool
    data_opcao: Optional[str]
    """DD/MM/AAAA"""
    data_exclusao: Optional[str]
    """DD/MM/AAAA"""
    ultima_atualizacao: str
    """ISO 8601"""


class EmpresaSimplificada(TypedDict):
    """Documento no formato ``simplificado``: plano, com datas DD/MM/AAAA, CNPJ, CEP e telefone
    já formatados e vazios como ``""``."""

    abertura: str
    """DD/MM/AAAA"""
    situacao: str
    tipo: str
    """MATRIZ ou FILIAL."""
    nome: str
    fantasia: str
    porte: str
    natureza_juridica: str
    """Por exemplo ``206-2 - Sociedade Empresária Limitada``."""
    atividade_principal: List[AtividadeSimplificada]
    atividades_secundarias: List[AtividadeSimplificada]
    qsa: List[SocioSimplificado]
    logradouro: str
    numero: str
    complemento: str
    municipio: str
    bairro: str
    uf: str
    cep: str
    """00.000-000"""
    email: str
    telefone: str
    """Telefones com máscara separados por " / "."""
    data_situacao: str
    """DD/MM/AAAA"""
    cnpj: str
    """AA.AAA.AAA/AAAA-DD"""
    ultima_atualizacao: str
    """ISO 8601"""
    status: str
    efr: str
    """Ente federativo responsável."""
    motivo_situacao: str
    situacao_especial: str
    data_situacao_especial: str
    capital_social: str
    """Com duas casas decimais, por exemplo ``"218878.00"``."""
    simples: RegimeSimplificado
    simei: RegimeSimplificado
    extra: Dict[str, Any]
    billing: Dict[str, Any]


# ------------------------------------------------------------------ validação, status e planos


class Validacao(TypedDict):
    """Resposta de ``GET /v1/valida/{cnpj}`` (e de ``validar_local``)."""

    cnpj: str
    """Entrada normalizada (sem pontuação, maiúsculas)."""
    valido: bool
    formatado: Optional[str]
    """AA.AAA.AAA/AAAA-DD quando válido."""
    alfanumerico: bool
    """``True`` se a raiz ou a ordem têm letras."""
    erro: Optional[str]
    """Motivo quando inválido."""


class _StatusObrigatorio(TypedDict):
    status: Literal["OK", "DEGRADED"]
    """DEGRADED: base indisponível (a consulta responde 503)."""
    dataset_month: Optional[str]
    """Mês do lote da Receita Federal (AAAA-MM)."""
    rows: Optional[int]
    """Quantidade de CNPJs na base."""
    version: str
    """Versão da API."""
    time: str
    """Hora do servidor (ISO 8601)."""


class Status(_StatusObrigatorio, total=False):
    """Resposta de ``GET /v1/status``."""

    dataset_generated_at: Optional[str]
    """Quando a base foi gerada (ISO 8601)."""


class Plano(TypedDict):
    id: str
    """free, dev, pro..."""
    name: str
    price: float
    """Preço mensal (BRL)."""
    rpm: int
    """Consultas por minuto."""
    monthly_quota: int
    """Consultas por mês."""
    description: Optional[str]


class CobrancaPlanos(TypedDict):
    provider: str
    test_mode: bool
    available: bool
    """Assinaturas abertas."""
    requires_document: bool
    """Checkout pede CPF/CNPJ."""


class Planos(TypedDict):
    """Resposta de ``GET /v1/plans``."""

    tos_version: str
    """Versão vigente dos termos de uso."""
    currency: str
    plans: List[Plano]
    billing: CobrancaPlanos


# ------------------------------------------------------------------ cliente


class LimiteJanela(TypedDict):
    limite: Optional[int]
    restante: Optional[int]
    reset: Optional[int]
    """Por minuto: segundos até a janela zerar. Mensal: epoch Unix (segundos) em que a cota zera."""


class Limites(TypedDict):
    """Cabeçalhos ``X-RateLimit-*`` (``por_minuto``) e ``X-Quota-*`` (``mensal``) da última consulta."""

    por_minuto: LimiteJanela
    mensal: LimiteJanela


class ResultadoLote(TypedDict):
    """Item entregue por ``consultar_varios`` (formato ``completo``)."""

    cnpj: str
    """CNPJ normalizado (sem pontuação, maiúsculas)."""
    documento: Optional[EmpresaCompleta]
    """Documento, ou ``None`` se não está na base (404), é inválido ou deu erro."""
    erro: Optional[ApipjErro]
    """``invalid_cnpj`` ou a falha depois das tentativas; ``None`` quando deu certo (inclusive 404)."""


class ResultadoLoteSimplificado(TypedDict):
    """Item entregue por ``consultar_varios(..., formato="simplificado")``."""

    cnpj: str
    documento: Optional[EmpresaSimplificada]
    erro: Optional[ApipjErro]
