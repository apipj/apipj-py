# Changelog

Todas as mudanças relevantes deste pacote. Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/); versões seguem [SemVer](https://semver.org/lang/pt-BR/).

## [0.2.0] - 2026-10-14

### Adicionado

- Consulta sem chave: sem `chave` nem `APIPJ_KEY`, `consultar` chama a API sem autenticação (limite de teste por IP) em vez de lançar 401 local, e emite um `UserWarning` uma vez com o link da chave grátis (`avisos=False` desliga).
- `ApipjErro.signup_url` (link de cadastro no 429 da consulta sem chave) e `limites["sem_chave"]` e `limites["diario"]` (cabeçalhos `X-Apipj-Acesso` e `X-Daily-*`).

## [0.1.0] - 2026-10-13

Primeira versão.

### Adicionado

- `Apipj` com `consultar` (formatos `completo` e `simplificado`; `404` vira `None`), `validar`, `status`, `planos` e `consultar_varios` (lote em threads com limite por minuto lido de `X-RateLimit-*`, deduplicação e CNPJs inválidos pulados sem chamar a API).
- Repetição automática: `429 rate_limited` espera `Retry-After`; `5xx`, falha de rede e tempo esgotado com espera de 1 s, 2 s...
- `ApipjErro` com `status`, `code`, `message`, `retry_after`, `upgrade_url` e `reset`.
- `api.limites` com os últimos cabeçalhos `X-RateLimit-*` e `X-Quota-*`.
- Utilitários offline: `cnpj_valido`, `normalizar_cnpj`, `formatar_cnpj`, `validar_local`, `calcular_dv` (inclusive CNPJ alfanumérico).
- Tipos (`py.typed`) das respostas: `EmpresaCompleta`, `EmpresaSimplificada`, `Validacao`, `Status`, `Plano`, `Planos`, `ResultadoLote`, `Limites`.
- Zero dependências em tempo de execução (só a biblioteca padrão).

[0.1.0]: https://github.com/apipj/apipj-py/releases/tag/v0.1.0
