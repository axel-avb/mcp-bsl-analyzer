# MCP BSL LSP Bridge (Go) — разбор слоя вызовов BSL Language Server

Саммари Go-реализации [SteelMorgan/mcp-bsl-lsp-bridge](https://github.com/SteelMorgan/mcp-bsl-lsp-bridge).
Назначение документа — зафиксировать, как был устроен вызов `bsl-language-server`, какие
костыли понадобились и что из этого не стоит тащить в Python-переписку.

Клон-источник разбора: `/tmp/opencode/mcp-bsl-lsp-bridge` (upstream `rockerBOO/mcp-lsp-bridge`).

## Общая картина: три процесса, две «шины»

```
MCP-клиент (Cursor) ──stdio JSON-RPC──> mcp-lsp-bridge (Go, короткоживущий)
                                              │  TCP :9999, newline-delimited JSON
                                              │  (НЕ LSP framing)
                                              ▼
                                     lsp-session-manager (Go daemon, s6)
                                              │  stdio, LSP Content-Length framing
                                              ▼
                                     bsl-language-server (Java/lsp4j, single-threaded)
```

Ключевое: `docker exec -i ... mcp-lsp-bridge` создаёт новый процесс на каждый запрос.
BSL LS живёт постоянно в демоне `lsp-session-manager`. Весь проект — костыль вокруг того,
что MCP stdio форкает процесс, а Java-LS индексирует проект минуты.

## Слой вызовов BSL LS по файлам

### 1. Демон держит BSL LS — `cmd/lsp-session-manager/main.go` (1467 строк)
- `Start()` (:362) поднимает `java -jar bsl-language-server.jar lsp`, читает stdout
  `readResponses()` (:867), пишет с Content-Length header (`writeMessage` :842).
- `initialize()` (:655) сам собирает initialize-параметры (capabilities, workspaceFolders,
  rootUri; в multi-project rootUri=null). `initialization_options` из `lsp_config.json`
  тут игнорируются.
- `handleAPIRequest()` (:1184) — whitelist методов. Реально проброшены: hover, definition,
  references, documentSymbol, diagnostic, implementation, codeAction, formatting, rename,
  prepareRename, prepareCallHierarchy, incomingCalls, outgoingCalls, signatureHelp,
  completion, selectionRange, inlayHint, codeLens, semanticTokens(range/full),
  workspace/symbol, workspace/diagnostic, didChangeWatchedFiles, плюс `session/*`, `project/*`.
- `sendRequest()` (:795) — самодельный JSON-RPC: `requestID int64`, `pending map[int64]chan`,
  таймауты по методу (90с дефолт, workspace/diagnostic — 10 мин, diagnostic/formatting —
  5 мин, rename — 2 мин).

### 2. Клиент демона — `lsp/session_client.go` (560 строк)
- TCP + newline-delimited JSON (`Call()` :371), не LSP-фрейминг. Reconnect с backoff (:523),
  fail-all-pending (:508). Типизированные обёртки кладут params в `map[string]interface{}`.

### 3. Адаптер под интерфейс — `lsp/session_adapter.go` (888 строк)
- Реализует `LanguageClientInterface`, чтобы bridge не знал про session-режим.
- Половина методов — заглушки: `DidChange`, `DidSave`, `CodeActions`, `SemanticTokens`(full),
  `FoldingRange`, `DocumentLink`, `DocumentColor`, `ColorPresentation`, `ExecuteCommand`,
  `RangeFormatting`. `Implementation` фейкует через `References`.
- Дублирует таймауты поверх демона.

### 4. Bridge-политика — `bridge/bridge.go` (1821 строк)
- `validateAndConnectClient()` (:107) — выбор режима tcp / websocket / session / stdio.
  В session создаёт `SessionAdapter` и пропускает init (демон уже инициализирован).
- `ensureDocumentOpen()` (:698) — перед каждым запросом читает файл с диска, маппит
  host↔container, шлёт `textDocument/didOpen`. Кэш по `URI + mtime` (`openedDocs`),
  иначе повторный didOpen вешает однопоточный BSL LS.
- `GetClientForLanguage()` (:348) — кэш клиентов + пересоздание unhealthy.

### 5. LSP-примитивы — `lsp/methods.go` (734 строк)
- Только для stdio/tcp. Quirks: `DocumentSymbols` делает два запроса (DocumentSymbol[] →
  fallback SymbolInformation[]); completion парсит и `[]`, и `CompletionList`, и `null`.

## BSL-специфичные костыли

- **Capability gate** — `methodProvider()` (`main.go:1134`). BSL LS (lsp4j) на необъявленный
  метод бросает `UnsupportedOperationException`, убивает единственный `StreamMessageProducer.listen()`,
  и вся сессия виснет навсегда. Поэтому демон парсит `*Provider` из initialize result и
  отказывает. Отсюда же BSL LS прибит к `1.0.0-rc.1` в Dockerfile.
- **Однопоточность BSL LS** — причина гигантских таймаутов на 3 уровнях и mtime-кэша didOpen.
- **Прогресс индексации** — `handleNotification` `$/progress` (:915) парсит русское
  `"N/M файлов"` через `fmt.Sscanf` (:1023).
- **Multi-project** — init с `rootUri=null`, проекты через `workspace/didChangeWorkspaceFolders`;
  `detectConfigurationRoot()` (:283) ищет главный `Configuration.xml` (не extension) до глубины 5.
- **File watcher** — fsnotify/polling, debounce 500мс, шлёт `workspace/didChangeWatchedFiles`.
- **Пути** — `utils/pathmap.go`: host↔container, Windows drive letters, `file://`.

## Мусор / дубли

- `cmd/lsp-proxy/main.go` — легаси stdio↔TCP прокси; Docker его не использует.
- `docker/start.sh` мёртв.
- Два трекера прогресса, две копии JSON-RPC структур, `JSONRPCID`-полиморфизм.
- Generic-мультиязыковой слой (gopls/pyright/… 20+ серверов) — наследие upstream.
- `validateAndConnectClient` session-ветка кладёт клиент в `b.clients[language]`, а
  `GetClientForLanguage` ищет по имени сервера — запись бесполезна.
- `interfaces`/`types`/`mocks` — в Python не нужны.

## Вывод для Python-переписки

Минимально нужен один процесс, который держит `bsl-language-server` **один раз** и говорит
LSP через Content-Length framing, применяет capability gate и mtime-кэш didOpen, парсит
`$/progress`. Всё остальное — тонкие обёртки. На практике выбран другой путь: чистый
Python-анализатор `onec-hbk-bsl` (MIT) без Java, а этот документ сохраняется как референс
по поведению BSL LS.
