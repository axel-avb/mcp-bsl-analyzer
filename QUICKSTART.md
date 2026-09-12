# BSL MCP — руководство по развёртыванию

MCP-сервер для анализа кода 1С/BSL: диагностика по всему проекту и цикломатическая/
когнитивная сложность по методам. Построен на чистом Python поверх
[`onec-hbk-bsl`](https://github.com/mussolene/1c_hbk_bsl) (MIT), без Java и LSP-моста.
Готовый `onec-hbk-bsl` MCP переиспользуется целиком; сверху добавлены только два
инструмента: `complexity` и `workspace_diagnostics`.

Схема: **один проект = один сервис**, транспорт — Streamable HTTP, вход — nginx с
bearer-токеном. Память и индекс изолированы по проектам.

```
агенты/машины ──HTTP──> nginx (/bsl/<proj>/mcp, Bearer) ──> bsl-<proj>:8051/mcp
                                                             └── <project> (mounted 1:1)
```

## 1. Требования

- Linux-хост с Docker Engine 24+ и Compose v2 (`docker compose`).
- Свободный порт под nginx (по умолчанию `8080`).
- 2 ГБ RAM и ~2 CPU на проект (индексация крупных выгрузок — CPU/диск-тяжёлая).
- Код 1С лежит на хосте и **монтируется 1:1** (путь внутри контейнера = путь на хосте).

## 2. Быстрый старт

```bash
git clone <repo> bsl-mcp && cd bsl-mcp
cp .env.example .env
# отредактируй .env: токен и пути к проектам
docker compose up -d --build
docker compose ps
```

Проверка (подставь свой хост и порт):

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/bsl/proj-a/mcp \
  -X POST -H 'Authorization: Bearer <ТОКЕН>' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
# ожидаем 200; без заголовка Authorization — 401
```

## 3. Конфигурация (`.env`)

| Переменная | Обязательно | Описание |
|---|---|---|
| `BSL_MCP_TOKEN` | да | Bearer-токен. Агенты шлют `Authorization: Bearer <токен>`. |
| `NGINX_PORT` | нет | Хост-порт nginx (по умолчанию `8080`). |
| `PROJ_A_PATH`, `PROJ_B_PATH`, `PROJ_C_PATH` | да | Абсолютные пути к проектам на хосте. |

Пример:

```env
BSL_MCP_TOKEN=super-secret-token
NGINX_PORT=8080
PROJ_A_PATH=/srv/1c/trade
PROJ_B_PATH=/srv/1c/buh
PROJ_C_PATH=/srv/1c/ut
```

## 4. Как устроены сервисы и URL

Имя сервиса обязано быть `bsl-<proj>`, тогда URL `/bsl/<proj>/mcp` маршрутизируется
в него (шаблон nginx: `bsl-${proj}:8051`). Примеры из `docker-compose.yml`:

| Сервис | URL для агента |
|---|---|
| `bsl-proj-a` | `http://<host>:8080/bsl/proj-a/mcp` |
| `bsl-proj-b` | `http://<host>:8080/bsl/proj-b/mcp` |
| `bsl-proj-c` | `http://<host>:8080/bsl/proj-c/mcp` |

### Добавить n-й проект

Роутинг полностью динамический: nginx берёт имя проекта из URL `/bsl/<proj>/mcp`,
резолвит сервис `bsl-<proj>` через Docker DNS (`resolver 127.0.0.11`) и проксирует
на `bsl-<proj>:8051/mcp`. Править nginx при добавлении проекта **не нужно** — нужен
только сам сервис в `docker-compose.yml`.

Полный конфиг nginx (`nginx/templates/default.conf.template`, менять при добавлении
проекта не требуется):

```nginx
map $http_authorization $bsl_authed {
    default 0;
    "Bearer ${BSL_MCP_TOKEN}" 1;
}

server {
    listen 80;
    server_name _;

    resolver 127.0.0.11 valid=30s ipv6=off;

    location ~ ^/bsl/(?<proj>[a-zA-Z0-9_-]+)/mcp/?$ {
        if ($bsl_authed = 0) {
            return 401;
        }

        rewrite ^/bsl/[a-zA-Z0-9_-]+/mcp/?$ /mcp break;
        proxy_pass http://bsl-${proj}:8051;
        proxy_http_version 1.1;
        proxy_set_header Host $http_host;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    location = /healthz {
        return 200 "ok\n";
    }
}
```

Важные детали конфига:

- `"Bearer ${BSL_MCP_TOKEN}"` в `map` — envsubst образа nginx подставляет сюда
  значение `BSL_MCP_TOKEN` из `.env` (в `docker-compose.yml` он передаётся в
  environment nginx-сервиса).
- `resolver 127.0.0.11` обязателен: без него nginx не резолвит `bsl-${proj}` в
  переменной `proxy_pass` и возвращает `502`.
- Слеш в конце URL (`/mcp/`) срезается `rewrite`: бэкенд на `/mcp/` отвечает
  `307`-редиректом на `/mcp`.
- `proxy_buffering off` обязателен для SSE — не убирать.

Условия, чтобы n-й проект заработал:

1. Сервис называется `bsl-<proj>` (имя контейнера при этом неважно).
2. Бэкенд слушает порт `8051` — он зашит в шаблон; в compose задаётся
   `MCP_PORT: "8051"`.
3. Имя проекта матчится `[a-zA-Z0-9_-]+` (дефис ок, остальные спецсимволы — нет).
4. Токен один на всё развёртывание — `BSL_MCP_TOKEN` в `.env` (auth глобальный,
   отдельный токен на проект не предусмотрен).

Шаги:

1. В `.env` добавь `PROJ_D_PATH=/srv/1c/erp`.
2. В `docker-compose.yml` добавь сервис по образцу и допиши его в `depends_on` у `nginx`:

```yaml
  bsl-proj-d:
    <<: *bsl-service
    environment:
      WORKSPACE_ROOT: "${PROJ_D_PATH:?set PROJ_D_PATH in .env}"
      MCP_PORT: "8051"
    volumes:
      - "${PROJ_D_PATH}:${PROJ_D_PATH}"
```

3. `docker compose up -d`. URL: `/bsl/proj-d/mcp`.

### Удалить проект

Удали сервис из `docker-compose.yml` и переменную из `.env`, затем `docker compose up -d --remove-orphans`.

## 5. Подключение агента

Токен передаётся заголовком на **каждый** запрос, включая долгоживущий SSE-GET.

### opencode (`opencode.json`)

```json
{
  "mcp": {
    "bsl-trade": {
      "type": "remote",
      "url": "http://HOST:8080/bsl/proj-a/mcp",
      "headers": { "Authorization": "Bearer super-secret-token" },
      "enabled": true
    }
  }
}
```

### Cursor / Claude / прочие (формат `mcpServers`)

```json
{
  "mcpServers": {
    "bsl-trade": {
      "type": "streamable-http",
      "url": "http://HOST:8080/bsl/proj-a/mcp",
      "headers": { "Authorization": "Bearer super-secret-token" }
    }
  }
}
```

На каждый проект — своя запись в MCP-клиенте.

## 6. Доступные инструменты

Всё, что даёт `onec-hbk-bsl` (диагностика файла `bsl_diagnostics`/`bsl_check_file`,
поиск/навигация `bsl_find_symbol`/`bsl_definition`/`bsl_callers`/`bsl_callees`/
`bsl_references`/`bsl_hover`, `bsl_rename`, `bsl_format`, `bsl_fix`, метаданные 1С —
итого ~22), плюс наши:

- **`complexity(file)`** — цикломатическая и когнитивная сложность по методам.
  Пороги по умолчанию: cognitive > 15, cyclomatic > 20 (берутся из `onec-hbk-bsl.toml`).
  Возвращает `methods[]` с `name/kind/line/cognitive/mccabe` и флагами.
- **`module_health(file)`** — combo: complexity + security/performance/SQL-диагностики,
  привязанные к методу-владельцу и проранжированные по приоритету рефакторинга
  (`top_targets`). Веса: security ×10, performance ×4, sql ×4 + превышение порогов.
- **`workspace_diagnostics(path=".", min_severity="WARNING", select, ignore, top_n, max_files, include_items)`**
  — диагностика по всему каталогу с агрегацией: `by_severity`, `top_rules`, `top_files`.

Пути в аргументах — абсолютные или относительно `WORKSPACE_ROOT` (в контейнере это
тот же путь, что на хосте). Выход за пределы воркспейса отклоняется.

## 7. Индекс символов

`onec-hbk-bsl` держит SQLite-индекс для навигации и metadata-aware правил.

- Расположение: `<project>/.git/onec-hbk-bsl_index.sqlite`, если проект под git,
  иначе `~/.cache/onec-hbk-bsl/<hash>/...` **внутри контейнера**.
- При пустом индексе сервер запускает фоновую индексацию при старте.
- Режим индекса берётся из `onec-hbk-bsl.toml` в корне проекта (`off`/`symbols`/`full`,
  по умолчанию `full`). Файл `onec-hbk-bsl.toml` также задаёт `select`/`ignore`/`exclude`.
- **Watcher в MCP не работает** (он только в LSP-режиме): после правок файлов индекс
  не обновляется сам. Провоцируй инструмент `bsl_index_file` или перезапусти сервис.
  `complexity`/`workspace_diagnostics` индекс не используют и всегда читают с диска.
- Чтобы индекс переживал пересоздание контейнера для не-git проектов, задай
  `INDEX_DB_PATH` на смонтированный том (например `/var/lib/bsl/index.sqlite`)
  и примонтируй том.

## 8. Эксплуатация

```bash
docker compose up -d --build          # собрать/поднять/обновить все сервисы
docker compose ps
docker compose logs -f bsl-proj-a     # логи конкретного проекта
docker compose logs -f nginx
docker compose restart bsl-proj-a     # перезапуск одного проекта
docker compose down                   # остановить всё
```

Сборка образа — один раз на все сервисы: `docker build -t bsl-mcp:local .` (или через compose).

## 9. Проверка и отладка

Полный цикл инициализации и список инструментов (изнутри docker-сети или с хоста):

```bash
# 1) initialize -> 200 + заголовок mcp-session-id (ответ в формате SSE)
curl -s -D - http://HOST:8080/bsl/proj-a/mcp \
  -X POST -H 'Authorization: Bearer <ТОКЕН>' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
```

Типовые симптомы:

| Симптом | Причина / решение |
|---|---|
| `401` | Нет/неверный `Authorization: Bearer`. |
| `404` на `/bsl/<proj>/mcp` | Нет сервиса `bsl-<proj>` или опечатка в URL. |
| Пустые результаты навигации | Индекс не построен/устарел → `bsl_index_file` или рестарт. |
| Ответы «висят»/рвутся | Прокси буферизует SSE. В нашем шаблоне `proxy_buffering off;` — не убирать. |
| `path outside workspace` | Аргумент вне `WORKSPACE_ROOT`; передавай путь внутри воркспейса. |
| Долгая первая реакция | Идёт фоновая индексация крупного проекта. |

## 10. Безопасность

- Порт `8051` у сервисов не публикуется наружу — только `expose` в docker-сети.
- Наружу торчит только nginx. Для продакшена терминируй **TLS** перед ним:
  пошаговое руководство с примерами compose/nginx/certbot —
  [`docs/tls-letsencrypt.md`](docs/tls-letsencrypt.md).
- Токен один на развёртывание. Для ротации: обнови `BSL_MCP_TOKEN` в `.env` и
  `docker compose up -d nginx` (перегенерирует конфиг через envsubst).
- Проверка доступа к `/healthz` — без токена (для liveness-проб).

## 11. Обновление зависимости

Версия `onec-hbk-bsl` зафиксирована в `pyproject.toml`
(`onec-hbk-bsl-core[mcp]==0.8.50`). Внутренности этой библиотеки трогает только
`src/bsl_mcp/lsp_facade.py` — это единственная точка, которую проверять при апгрейде.

```bash
# поменять версию в pyproject.toml, затем
python -m pytest -q                    # локально (нужен Python 3.12)
docker compose build && docker compose up -d
```

Дымовой тест после апгрейда — тот же `initialize` + `tools/list` (ожидаем наличие
`complexity` и `workspace_diagnostics`) и вызов `complexity` на любом модуле.

## 12. Структура репозитория

```
src/bsl_mcp/entrypoint.py            точка входа: env → create_mcp_app() → +2 tool → HTTP
src/bsl_mcp/lsp_facade.py            адаптер к внутренним API onec-hbk-bsl (пин версии)
src/bsl_mcp/tools/complexity.py      инструмент complexity
src/bsl_mcp/tools/module_health.py   инструмент module_health
src/bsl_mcp/tools/workspace_diagnostics.py  инструмент workspace_diagnostics
Dockerfile                           python:3.12-slim + onec-hbk-bsl
docker-compose.yml                   bsl-<proj> сервисы + nginx
nginx/templates/default.conf.template  маршрутизация /bsl/<proj>/mcp + bearer + SSE
docs/bsl-lsp-go-overview.md          разбор старого Go-моста (референс)
tests/                               юнит-тесты
```
