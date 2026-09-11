# BSL MCP Analyzer

[English](README.md) · **Русский**

MCP-сервер для анализа кода 1С/BSL: диагностика по всему проекту и цикломатическая/
когнитивная сложность по методам с ранжированной триажей рефакторинга. Построен на
чисто-питоновском движке [`onec-hbk-bsl`](https://github.com/mussolene/1c_hbk_bsl) —
**без Java и без LSP-моста**. Отдаётся по Streamable HTTP за nginx с bearer-токеном,
один сервис на проект.

## Зачем

`onec-hbk-bsl` уже содержит полноценный BSL-анализатор, форматтер, индекс и свой
MCP-сервер. Проект переиспользует всё это и добавляет то, чего не хватало для работы
с большими конфигурациями 1С:

- **`complexity`** — сырые цикломатическая и когнитивная сложность по каждому методу
  (в upstream они видны только как предупреждения при превышении порога, без чисел).
- **`module_health`** — сложность, слитая с security/performance/SQL-диагностиками,
  с привязкой к методу и ранжированием «что чинить первым».
- **`workspace_diagnostics`** — линт всего проекта с агрегацией по правилам/важности/файлам.

Плюс понятные мелким моделям названия и описания для всех 25 инструментов и готовое
развёртывание через Docker Compose + nginx.

## Возможности

- **Диагностика**: 180+ правил BSL/1С (реестр onec-hbk-bsl), подавления `noqa`/`bsl-disable`,
  `select`/`ignore`, агрегация по проекту.
- **Сложность**: метрики McCabe и когнитивной сложности по методам, настраиваемые пороги
  (по умолчанию 20 / 15), флаги превышения.
- **Триаж рефакторинга**: `module_health` взвешивает security ×10, performance/sql ×4 плюс
  превышение порогов сложности и возвращает отсортированный `top_targets`.
- **Полный набор навигации** из onec-hbk-bsl: символы, определения, ссылки, вызовы,
  hover, поиск, переименование, форматирование, фиксы, метаданные 1С.
- **Мультипроект**: один контейнер на проект, монтаж путей хост↔контейнер `1:1`.
- **Дружелюбность к агентам**: у каждого инструмента есть блок что/когда/аргументы/ответ/пример.

## Архитектура

```
MCP-агенты ──HTTP──> nginx (/bsl/<proj>/mcp, Bearer) ──> bsl-<proj>:8051/mcp
                                                          └── <project> (монтаж 1:1)
                                                             движок onec-hbk-bsl (Python)
```

```
src/bsl_mcp/entrypoint.py            bootstrap env → FastMCP-приложение onec-hbk-bsl → +3 тула → HTTP
src/bsl_mcp/lsp_facade.py            единственный адаптер к внутренним API onec-hbk-bsl
src/bsl_mcp/tool_docs.py             названия/описания/инструкции для всех тулов
src/bsl_mcp/tools/complexity.py      инструмент complexity
src/bsl_mcp/tools/module_health.py   инструмент module_health
src/bsl_mcp/tools/workspace_diagnostics.py  инструмент workspace_diagnostics
docker-compose.yml                   сервисы bsl-<proj> + nginx
nginx/templates/default.conf.template  маршрутизация + bearer + SSE-friendly прокси
```

## Требования

- Linux-хост с Docker Engine 24+ и Compose v2.
- 2 ГБ RAM / ~2 CPU на проект (индексация больших конфигураций тяжела по CPU/диску).
- Свободный порт под nginx (по умолчанию `8080`).

## Быстрый старт

```bash
cp .env.example .env
# отредактируй .env: BSL_MCP_TOKEN и PROJ_A_PATH/PROJ_B_PATH/PROJ_C_PATH
docker compose up -d --build
docker compose ps
```

Проверка (ожидаем `200`; без заголовка — `401`):

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/bsl/proj-a/mcp \
  -X POST -H 'Authorization: Bearer <ТОКЕН>' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
```

### Подключение агента

opencode (`opencode.json`):

```json
{
  "mcp": {
    "bsl-trade": {
      "type": "remote",
      "url": "http://HOST:8080/bsl/proj-a/mcp",
      "headers": { "Authorization": "Bearer <ТОКЕН>" },
      "enabled": true
    }
  }
}
```

Cursor / Claude и прочие клиенты (`mcpServers`):

```json
{
  "mcpServers": {
    "bsl-trade": {
      "type": "streamable-http",
      "url": "http://HOST:8080/bsl/proj-a/mcp",
      "headers": { "Authorization": "Bearer <ТОКЕН>" }
    }
  }
}
```

## Инструменты

Добавлено этим проектом:

| Инструмент | Назначение |
|---|---|
| `complexity(file)` | Цикломатическая и когнитивная сложность по методам, пороги и флаги |
| `module_health(file)` | Сложность + security/performance/SQL-диагностики, ранжированные `top_targets` |
| `workspace_diagnostics(path, min_severity, select, ignore, top_n)` | Линт всего проекта с агрегацией по правилу/важности/файлу |

Унаследовано от onec-hbk-bsl (22 инструмента): `bsl_status`, `bsl_find_symbol`,
`bsl_file_symbols`, `bsl_definition`, `bsl_hover`, `bsl_callers`, `bsl_callees`,
`bsl_references`, `bsl_read_file`, `bsl_search`, `bsl_diagnostics`, `bsl_check_file`,
`bsl_list_rules`, `bsl_index_file`, `bsl_format`, `bsl_rename`, `bsl_fix`,
`bsl_workspace_scan`, `bsl_meta_object`, `bsl_meta_collection`, `bsl_meta_index`,
`bsl_contract_version`.

## Конфигурация

| Переменная | Обязательно | Описание |
|---|---|---|
| `BSL_MCP_TOKEN` | да | Bearer-токен, который шлют агенты |
| `NGINX_PORT` | нет | Хост-порт nginx (по умолчанию `8080`) |
| `PROJ_A_PATH`, `PROJ_B_PATH`, `PROJ_C_PATH` | да | Абсолютные пути к проектам 1С на хосте (монтаж 1:1) |

Имя сервиса обязано быть `bsl-<proj>`, тогда URL `/bsl/<proj>/...` маршрутизируется в него.
Настройки индекса (`index-mode`, `select`/`ignore`, `exclude`) берутся из
`onec-hbk-bsl.toml` в корне проекта.

## Документация

- [QUICKSTART.md](QUICKSTART.md) — полное руководство по развёртыванию
- [docs/tls-letsencrypt.md](docs/tls-letsencrypt.md) — HTTPS через Let's Encrypt, пошагово
- [docs/bsl-lsp-go-overview.md](docs/bsl-lsp-go-overview.md) — разбор прежнего Go-моста

## Благодарности

- Движок анализа, парсер, индекс и базовый MCP-слой:
  [`onec-hbk-bsl`](https://github.com/mussolene/1c_hbk_bsl) (MIT).
- Корпус диагностических правил адаптирован из
  [`BSL Language Server`](https://github.com/1c-syntax/bsl-language-server).
