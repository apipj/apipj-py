# apipj: API CNPJ gratuita para Python

**API para consultar CNPJ** em Python: o cliente oficial da API de CNPJ do [apipj](https://apipj.com.br), com plano gratuito de 50 mil consultas por mês, sem cartão. Consulte CNPJ e receba razão social, situação cadastral, endereço, CNAEs, Simples/MEI e sócios a partir dos dados abertos da Receita Federal, com suporte ao **CNPJ alfanumérico**.

- Python 3.9 a 3.13, **zero dependências** (usa só a biblioteca padrão) e tipado (`py.typed`, `TypedDict` para cada resposta).
- Valida o CNPJ (inclusive alfanumérico) localmente antes de chamar a API: CNPJ inválido não gasta cota.
- Repete sozinho em limite por minuto (`429` com `Retry-After`), erro `5xx`, falha de rede e tempo esgotado.
- Consulta em lote com `consultar_varios`, em paralelo e respeitando o limite por minuto do seu plano.

> **Atenção: a chave de API é secreta.** Não a escreva no código-fonte, não a envie para o Git e não a coloque em aplicativos distribuídos (desktop, mobile, front-end): qualquer pessoa conseguiria copiá-la e gastar a sua cota. Guarde-a numa variável de ambiente ou num cofre de segredos do servidor.

## Instalação

```bash
pip install apipj
```

**Para testar, não precisa de chave:** sem `APIPJ_KEY`, `consultar` usa a consulta sem chave da API, com limite de teste por IP (hoje 3 consultas por minuto e 100 por dia), e emite um aviso (`UserWarning`) uma vez. Para uso real, crie uma conta grátis em [apipj.com.br/criar-conta](https://apipj.com.br/criar-conta?origem=api-lib-pypi-apipj) (10 consultas por minuto e 50 mil por mês, sem cartão), gere a chave no painel e exporte-a:

```bash
export APIPJ_KEY=apipj_live_...
```

## Consultar CNPJ

```python
from apipj import Apipj, ApipjErro, cnpj_valido, normalizar_cnpj, formatar_cnpj

api = Apipj(
    chave=None,                       # padrão: lê APIPJ_KEY só na hora de consultar
    base_url="https://apipj.com.br",
    timeout=10,                       # segundos, por tentativa
    tentativas=3,                     # contando a primeira
)

# Documento completo, ou None se o CNPJ não está na base da Receita (404)
empresa = api.consultar("11.378.117/0001-20")
if empresa:
    print(empresa["razao_social"])                          # razão social
    print(empresa["situacao_cadastral"]["descricao"])       # ATIVA, BAIXADA, INAPTA...
    print(empresa["endereco"]["municipio"]["nome"], empresa["endereco"]["uf"])
    print(empresa["cnae_principal"])                        # {'codigo': ..., 'descricao': ...}

# Formato simplificado: plano, com datas DD/MM/AAAA e CNPJ, CEP e telefone já formatados
simples = api.consultar("11378117000120", formato="simplificado")
if simples:
    print(simples["cnpj"], simples["nome"], simples["abertura"])

# Status do serviço e mês do lote da Receita carregado (sem chave e sem cota)
print(api.status()["dataset_month"])

# Planos, preços e limites (sem chave e sem cota)
for plano in api.planos()["plans"]:
    print(plano["name"], plano["rpm"], plano["monthly_quota"], plano["price"])
```

O retorno é um `dict` comum, tipado com `TypedDict` (`EmpresaCompleta` ou `EmpresaSimplificada`, conforme o `formato`): o editor completa os campos e o mypy/pyright conferem o acesso. No formato completo, campo ausente na base da Receita vem como `None`; nenhuma chave some.

## Validar CNPJ (inclusive alfanumérico)

Offline, sem chamar a API:

```python
from apipj import cnpj_valido, normalizar_cnpj, formatar_cnpj

print(cnpj_valido("12.ABC.345/01DE-35"))      # True  (alfanumérico)
print(cnpj_valido("12ABC34501DE36"))          # False (dígito verificador errado)
print(cnpj_valido("00.000.000/0000-00"))      # False (zerado)
print(normalizar_cnpj("12.abc.345/01de-35"))  # 12ABC34501DE35
print(formatar_cnpj("11378117000120"))        # 11.378.117/0001-20
```

`cnpj_valido` confere formato e dígitos verificadores do CNPJ numérico e do alfanumérico (IN RFB 2.229/2024: cada caractere vale o código ASCII menos 48, módulo 11); não diz se o CNPJ existe. Também são exportados `validar_local` (mesmo formato de resposta de `api.validar`) e `calcular_dv`.

Pela API (sem chave e sem consumo de cota):

```python
print(api.validar("12.ABC.345/01DE-35"))
# {'cnpj': '12ABC34501DE35', 'valido': True, 'formatado': '12.ABC.345/01DE-35', 'alfanumerico': True, 'erro': None}
```

## Consultar CNPJ em lote

```python
lista = ["11.378.117/0001-20", "00.000.000/0001-91", "11378117000120", "123"]

for r in api.consultar_varios(lista, simultaneas=4):
    # r = {"cnpj": ..., "documento": ... ou None, "erro": ApipjErro ou None}, na ordem de conclusão
    if r["erro"]:
        print(r["cnpj"], r["erro"].code, r["erro"].message)
    elif r["documento"] is None:
        print(r["cnpj"], "não encontrado")
    else:
        print(r["cnpj"], r["documento"]["razao_social"])
```

- Lê o limite por minuto do seu plano dos cabeçalhos `X-RateLimit-Limit`/`Remaining`/`Reset` e **nunca passa dele** (a primeira consulta sai sozinha para descobrir o limite). Use `rpm=` para ficar abaixo do plano, por exemplo para dividir a chave com outro processo.
- CNPJs repetidos (mesmo com máscaras diferentes) são consultados uma vez só.
- CNPJs inválidos **não chamam a API**: saem com `documento` `None` e `erro.code == "invalid_cnpj"`.
- Erro de um CNPJ (por exemplo `5xx` depois das tentativas) sai no próprio item e o lote continua.
- `401` (chave inválida) e cota mensal esgotada (`quota_exceeded`) interrompem o lote lançando `ApipjErro`, depois de entregar os resultados já prontos.
- Aceita lista, gerador ou qualquer iterável (por exemplo, as linhas de um arquivo). Um `break` no laço para de chamar a API.
- Opções: `simultaneas` (padrão 4, threads), `formato`, `rpm`.

## Tratamento de erros

Todos os erros da API viram `ApipjErro`, com `status` (HTTP, ou `0` para rede/tempo esgotado), `code` (estável, em snake_case) e `message` (em português).

```python
def buscar(cnpj: str) -> str:
    try:
        empresa = api.consultar(cnpj)
    except ApipjErro as e:
        if e.code == "invalid_cnpj":      # 400: formato ou dígito inválido (verificado antes de chamar a API)
            return f"CNPJ inválido: {e.message}"
        if e.code == "unauthorized":      # 401: chave inválida ou revogada (ou consulta sem chave fechada; e.signup_url)
            return "Confira a variável APIPJ_KEY"
        if e.code == "quota_exceeded":    # 429: cota mensal esgotada (e.upgrade_url, e.reset) ou, sem chave, limite do dia (e.signup_url)
            return f"Cota do mês esgotada; planos em {e.upgrade_url}"
        if e.code == "rate_limited":      # 429: limite por minuto mesmo depois de esperar Retry-After
            return f"Tente de novo em {e.retry_after} s"
        raise                             # 5xx (dataset_unavailable, server_error), network_error, timeout
    if empresa is None:
        return "CNPJ não encontrado na base da Receita"
    return empresa["razao_social"]


print(buscar("11.378.117/0001-21"))   # CNPJ inválido: Dígitos verificadores inválidos
```

| Situação | O que o cliente faz |
|---|---|
| CNPJ inválido | lança `ApipjErro(400, "invalid_cnpj")` **sem chamar a API** |
| `404` (CNPJ válido, fora da base) | devolve `None` |
| `400`, `401` | lança na hora |
| `429 quota_exceeded` | lança na hora, com `upgrade_url` e `reset` |
| `429 rate_limited` | espera `Retry-After` e repete, até `tentativas`; depois lança com `retry_after` |
| `5xx`, falha de rede, tempo esgotado | repete com espera de 1 s, 2 s...; depois lança |

Depois de cada consulta, `api.limites` traz o que a API informou nos cabeçalhos `X-RateLimit-*` e `X-Quota-*`:

```python
print(api.limites)
# {'por_minuto': {'limite': 10, 'restante': 9, 'reset': 60}, 'mensal': {'limite': 50000, 'restante': 49990, 'reset': 1793502000}}
```

## Limites e plano gratuito

Cada consulta respondida (inclusive `404`) conta 1 na cota mensal; também vale um limite de consultas por minuto por chave. `validar`, `status` e `planos` não consomem cota.

| Plano | Consultas por minuto | Consultas por mês | Preço |
|---|---|---|---|
| Gratuito | 10 | 50.000 | R$ 0 |
| Dev | 30 | 200.000 | R$ 12,90/mês |
| Pro | 200 | 600.000 | R$ 59,90/mês |

Valores atuais em [apipj.com.br/precos](https://apipj.com.br/precos) (ou, no código, `api.planos()`). Para assinar o Pro direto: [apipj.com.br/painel?assinar=pro](https://apipj.com.br/painel?assinar=pro).

## Links

- Documentação da API: [apipj.com.br/docs](https://apipj.com.br/docs)
- Guia passo a passo: [como consultar CNPJ em Python](https://apipj.com.br/guias/consultar-cnpj-python)
- OpenAPI: [apipj.com.br/openapi-publica.json](https://apipj.com.br/openapi-publica.json)
- Em JavaScript/TypeScript: pacote npm [`apipj`](https://www.npmjs.com/package/apipj)
- Consultar CNPJ por IA (servidor MCP): [apipj.com.br/guias/consultar-cnpj-ia-mcp](https://apipj.com.br/guias/consultar-cnpj-ia-mcp)
- Preços: [apipj.com.br/precos](https://apipj.com.br/precos)
- Código-fonte e changelog: [github.com/apipj/apipj-py](https://github.com/apipj/apipj-py)

## Licença

[MIT](https://github.com/apipj/apipj-py/blob/main/LICENSE). Os dados vêm dos dados abertos do CNPJ publicados pela Receita Federal.
