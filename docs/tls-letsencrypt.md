# TLS для BSL MCP через Let's Encrypt

Как терминировать HTTPS перед nginx и получить бесплатный сертификат Let's Encrypt
для `https://<host>/bsl/<proj>/mcp`.

Схема после включения TLS:

```
агенты ──HTTPS 443──> nginx (TLS, Bearer) ──> bsl-<proj>:8051/mcp
                        │
                        └─ /.well-known/acme-challenge/ → certbot webroot (порт 80)
```

Подход: **HTTP-01 challenge через webroot**. nginx отдаёт `/.well-known/acme-challenge/`
на порту 80, certbot кладёт туда токен-файл и выпускает сертификат, nginx забирает его
из общего тома. Всё в compose, без внешних утилит. Токен-файлы хранятся в named volume.

---

## 0. Предусловия

- Домен (например `bsl.example.com`), для которого сделана **A-запись на этот хост**.
  Проверка: `dig +short bsl.example.com`.
- Из интернета доступны порты **80 и 443** этого хоста (Let's Encrypt валидирует снаружи).
- На хосте не занят порт 80 другим процессом.
- Email для уведомлений Let's Encrypt (об истечении).

## 1. Изменения в `.env`

```env
# существующие ключи не трогаем
DOMAIN=bsl.example.com
TLS_EMAIL=admin@example.com
```

## 2. Изменения в `docker-compose.yml`

Добавляем named volumes, тома nginx и сервис `certbot` (запускается только вручную,
`profiles` не даёт ему стартовать в `docker compose up`):

```yaml
volumes:
  certbot-etc:
  certbot-www:

services:
  nginx:
    # ...существующие поля...
    ports:
      - "${NGINX_PORT_HTTP:-80}:80"
      - "${NGINX_PORT_HTTPS:-443}:443"
    volumes:
      - ./nginx/templates:/etc/nginx/templates:ro
      - certbot-etc:/etc/letsencrypt:ro
      - certbot-www:/var/www/certbot:ro

  certbot:
    image: certbot/certbot:latest
    profiles: ["tls"]
    volumes:
      - certbot-etc:/etc/letsencrypt
      - certbot-www:/var/www/certbot
```

> Порты 80/443 публикуются только через nginx. Сервисы `bsl-*` по-прежнему `expose`,
> наружу не смотрят.

## 3. Конфиг nginx — два этапа

Let's Encrypt валидирует домен, пока nginx уже отдаёт webroot, но nginx не стартует,
если `ssl_certificate` ссылается на ещё не существующий файл. Поэтому делаем два шаблона.

### Шаг 3.1 — bootstrap (HTTP, выпуск сертификата)

`nginx/templates/default.conf.template` (на время выпуска):

```nginx
map $http_authorization $bsl_authed {
    default 0;
    "Bearer ${BSL_MCP_TOKEN}" 1;
}

server {
    listen 80;
    server_name _;

    # challenge-точка для Let's Encrypt
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location ~ ^/bsl/(?<proj>[a-zA-Z0-9_-]+)/(?<rest>.*)$ {
        if ($bsl_authed = 0) {
            return 401;
        }
        resolver 127.0.0.11 valid=30s ipv6=off;
        set $upstream "bsl-${proj}:8051";
        proxy_pass http://$upstream/$rest$is_args$args;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
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

### Шаг 3.2 — финальный (HTTPS + редирект)

Тот же файл, но с двумя server-блоками:

```nginx
map $http_authorization $bsl_authed {
    default 0;
    "Bearer ${BSL_MCP_TOKEN}" 1;
}

# HTTP: только challenge и редирект на HTTPS
server {
    listen 80;
    server_name _;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS: сам MCP
server {
    listen 443 ssl;
    server_name _;

    ssl_certificate     /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:SSL:10m;

    location ~ ^/bsl/(?<proj>[a-zA-Z0-9_-]+)/(?<rest>.*)$ {
        if ($bsl_authed = 0) {
            return 401;
        }
        resolver 127.0.0.11 valid=30s ipv6=off;
        set $upstream "bsl-${proj}:8051";
        proxy_pass http://$upstream/$rest$is_args$args;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
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

> `${DOMAIN}` и `${BSL_MCP_TOKEN}` подставляются envsubst'ом образа nginx из `.env`.

## 4. Пошаговый план выполнения

### Шаг 1 — DNS
Создай A-запись `bsl.example.com → <IP хоста>`. Дождись распространения:
```bash
dig +short bsl.example.com
```

### Шаг 2 — bootstrap-конфиг
Положи **Шаг 3.1** в `nginx/templates/default.conf.template`, затем:
```bash
docker compose up -d nginx
docker compose ps nginx
# проверить, что 80 отвечает:
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1/.well-known/acme-challenge/ping || true
```

### Шаг 3 — выпустить сертификат
```bash
docker compose --profile tls run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  -d bsl.example.com \
  --email admin@example.com \
  --agree-tos --no-eff-email
```
Успех: `Successfully received certificate.` Файлы появятся в томе `certbot-etc`
(`/etc/letsencrypt/live/bsl.example.com/{fullchain,privkey}.pem`).

### Шаг 4 — включить HTTPS
Замени шаблон на **Шаг 3.2**, перезапусти nginx:
```bash
docker compose up -d nginx
docker compose exec -T nginx nginx -t && docker compose exec -T nginx nginx -s reload
```

### Шаг 5 — проверка
```bash
# HTTP → 301
curl -s -o /dev/null -w '%{http_code}\n' http://bsl.example.com/bsl/proj-a/mcp

# HTTPS без токена → 401
curl -sk -o /dev/null -w '%{http_code}\n' https://bsl.example.com/bsl/proj-a/mcp

# HTTPS с токеном → 200 (initialize)
curl -sk -o /dev/null -w '%{http_code}\n' https://bsl.example.com/bsl/proj-a/mcp \
  -X POST -H 'Authorization: Bearer <ТОКЕН>' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
```

URL для агентов меняется на `https://bsl.example.com/bsl/<proj>/mcp`.

### Шаг 6 — автопродление
Сертификаты Let's Encrypt живут 90 дней. Продление раз в 2 месяца через cron хоста:

```bash
crontab -e
```
```cron
# обновить сертификат и перечитать его nginx'ом (04:15 ночи, 1-го числа)
15 4 1 * * cd /path/to/bsl-mcp && docker compose --profile tls run --rm certbot renew --quiet && docker compose exec -T nginx nginx -s reload
```

> `renew` продлевает только те сертификаты, где до истечения < 30 дней, и не перезапускает
> ничего сам — reload делает внешняя команда.

### Шаг 7 — dry-run продления (разово)
```bash
docker compose --profile tls run --rm certbot renew --dry-run
```
Ожидаем: `Congratulations, all simulated renewals succeeded`.

---

## 5. Откат

- Вернуть шаблон с HTTP (без ssl), убрать ssl-строки: `docker compose up -d nginx`.
- Удалить сервис `certbot`, `certbot-etc`, `certbot-www` и доп. порты из compose.
- (Опционально) удалить сам сертификат: `docker compose run --rm certbot delete --cert-name bsl.example.com`.

## 6. Частые проблемы

| Симптом | Причина / решение |
|---|---|
| `Certbot` ошибка `No valid IP addresses found for...` | DNS не распространился; проверь `dig`, подожди. |
| `Timeout during connect` на 80 | Порт 80 не открыт наружу / занят; webroot-путь не в том конфиге. |
| nginx не стартует: `cannot load certificate` | Перезапущен до Шага 3 (серт ещё нет); верни bootstrap-конфиг, выпусти сертификат, потом переключай. |
| После продления серт «старый» | nginx не перечитан; выполни reload (Шаг 6). |
| Агент не подключается по `https` | Используй `https://`, проверь, что в конфиге агента заголовок `Authorization` уходит на каждый запрос. |

## 7. Итог

- nginx: 80 (challenge + редирект), 443 (MCP + Bearer).
- Сертификаты и ключи живут в `certbot-etc` и **не** попадают в образ.
- Продление — cron на хосте, ничего в контейнерах править не нужно.
