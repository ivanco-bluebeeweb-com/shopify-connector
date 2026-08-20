# Shopify Connector — Preparation

**Статус:** Фаза 1 (Discovery + архитектурные решения) завершена. Влад
подтвердил объём релиза с первого сообщения по этому коннектору —
«максимальный функционал, полный максимум» (Ярус 1+2+3), без отдельного
запроса подтверждения (см. `CONNECTOR_DISCOVERY.md` шапка).
**Владелец продукта:** vlad@bluebeeweb.com
**Дата подготовки:** 2026-08-20, v0.1
**Vikunja task:** #2188 (BBW Imperal Apps), [App Development].

**Почему сейчас:** Shopify — крупнейшая e-commerce SaaS-платформа для
независимых продавцов, принципиально новый класс коннектора в портфеле —
не iPaaS/RPA-инструмент, а прямой коннектор к бизнес-домену продавца
(каталог, заказы, клиенты, инвентарь, скидки, фулфилмент). Ближайший
смысловой сосед в портфеле — WordPress Hub (WooCommerce), но закрывает
непересекающийся сегмент: продавцов на выделенной SaaS-платформе, а не
на WordPress.

---

## 1. Паспорт приложения

**Название в Marketplace (display_name): «Shopify»**. Внутренний
app_id/папка: `shopify-connector`.

**Shopify Connector** — коннектор к Shopify Admin API (GraphQL-first) для
управления одним или несколькими подключёнными магазинами: продукты и
варианты, коллекции, заказы (включая draft orders и refunds), клиенты,
инвентарь (по локациям), fulfillment orders, скидки (code + automatic),
metafields, webhooks (входящая нотификация о событиях магазина), bulk
operations (массовый экспорт данных через GraphQL bulk query). BYOK:
пользователь подключает свой собственный магазин через Custom App
Admin API access token, созданный в своём Shopify admin (Settings → Apps
and sales channels → Develop apps). Imperal ничего не хостит и не
проксирует, кроме самого запроса.

---

## 2. Ключевые архитектурные решения (см. `CONNECTOR_DISCOVERY.md` §1-2)

### 2.1 GraphQL Admin API как основная поверхность, не REST

Shopify официально помечает REST Admin API как поддерживаемый, но
рекомендует GraphQL для всей новой разработки; REST-only ресурсы (e.g.
`deprecated-api-calls`) явно трекаются самим Shopify как технический
долг у любого приложения, которое их использует. Коннектор строится
GraphQL-first: единственная REST-зависимость — там, где GraphQL
эквивалента ещё нет (проверяется по ходу реализации по `full-index`).

### 2.2 Custom App Admin API access token, НЕ OAuth authorization code

В отличие от публичных Shopify Apps (которые проходят полный OAuth flow
и App Store review), **custom app** — это приложение, созданное
владельцем ОДНОГО конкретного магазина внутри своего же Shopify admin,
не требующее ревью Shopify и не публикуемое в App Store. Оно выдаёт
статичный Admin API access token (`shpat_...`) сразу после создания и
одобрения запрошенных scopes владельцем магазина — тот же паттерн
"мгновенно доступно, без курицы-и-яйца", что уже избран для MuleSoft/
Power Automate/n8n/Make (в отличие от Zapier, которому для реального
доступа нужно сначала пройти внешний маркетплейс-ревью). Токен передаётся
заголовком `X-Shopify-Access-Token` на каждый запрос к
`https://{shop}.myshopify.com/admin/api/{version}/graphql.json`.

Коннектор просит у пользователя: **shop domain** (`{shop}.myshopify.com`)
+ **Admin API access token** (`shpat_...`) + опциональный **label**.
Это форма из 2 обязательных полей — проще, чем 4-польная форма
MuleSoft/Power Automate, потому что custom app token уже несёт в себе
все разрешённые scopes (выбираются один раз при создании custom app в
самом Shopify admin, не Imperal-стороной).

### 2.3 Версионирование API — фиксированная версия с ручным апгрейдом

Shopify использует календарное версионирование API (`YYYY-MM`,
квартальные релизы, ЛТС ~12 месяцев). Коннектор фиксирует одну
поддерживаемую версию в коде (константа `API_VERSION`), а не всегда
"latest" — так поведение не меняется под ногами без explicit апдейта
кода, тот же принцип предсказуемости, что у остальных коннекторов
портфеля.

### 2.4 Multi-shop, как multi-org у MuleSoft/Power Automate

Пользователь может подключить несколько магазинов (агентство ведёт
несколько клиентских Shopify-стор) — хранится список подключений
(`shopify_connections` secret), каждый вызов принимает опциональный
`connection_id` (по умолчанию первый/единственный), тот же паттерн, что
`connection_id` в MuleSoft/Power Automate/UiPath/Blue Prism/Automation
Anywhere.

### 2.5 Rate limiting — cost-based leaky bucket, обязательная обработка

GraphQL Admin API считает "cost" каждого запроса (по сложности полей и
кол-ву запрошенных объектов), не количество запросов. При превышении
бюджета отдаёт `THROTTLED` в extensions, а не HTTP 429. Клиент обязан
читать `extensions.cost.throttleStatus` и делать backoff/retry на
`THROTTLED`, а не просто проверять HTTP статус — иначе тихие сбои под
нагрузкой (тот же класс бага, что уже пойман и задокументирован для
других коннекторов в `known-bug-patterns.md`).

### 2.6 Bulk Operations — асинхронный JSONL-экспорт, Ярус 3 value-add

`bulkOperationRunQuery`/`bulkOperationRunMutation` — официальный
механизм массовой выгрузки/правки данных: запускается асинхронно,
результат — JSONL-файл по временной URL, готовность проверяется
поллингом (`currentBulkOperation` query) или через webhook
`bulk_operations/finish`. Даёт коннектору "экспортировать весь каталог/
все заказы одним вызовом" без постраничного обхода — прямой аналог
`audit_cloudhub_environment`/`audit_folder` у RPA-коннекторов, только
здесь это нативная возможность самого Shopify API, а не наша агрегация.

---

## 3. Три яруса функций (по `CONNECTOR_DISCOVERY_STANDARD.md`)

### Ярус 1 — управление подключением + базовый CRUD по ядру домена

- `connect_shopify` / `disconnect_shopify` / `list_connections`
- Products: `list_products`, `get_product`, `create_product`,
  `update_product`, `delete_product`
- Product Variants: `list_product_variants`, `update_product_variant`
- Collections: `list_collections`, `get_collection`,
  `create_collection`, `update_collection`, `delete_collection`,
  `add_products_to_collection`, `remove_products_from_collection`
- Orders: `list_orders`, `get_order`, `update_order`, `cancel_order`,
  `close_order`
- Customers: `list_customers`, `get_customer`, `create_customer`,
  `update_customer`, `delete_customer`

### Ярус 2 — полнота охвата домена (то, что делает коннектор ПОЛНЫМ,
не только "достаточным")

- Draft Orders: `list_draft_orders`, `create_draft_order`,
  `update_draft_order`, `complete_draft_order`, `delete_draft_order`
- Fulfillment: `list_fulfillment_orders`, `create_fulfillment`,
  `cancel_fulfillment`, `update_tracking_info`
- Refunds: `create_refund`, `list_refunds` (via order)
- Inventory: `list_locations`, `get_inventory_levels`,
  `adjust_inventory_quantity`, `set_inventory_quantities`,
  `activate_inventory_at_location`, `deactivate_inventory_at_location`
- Discounts: `list_discount_codes`, `create_discount_code`,
  `create_automatic_discount`, `update_discount`, `delete_discount`
- Metafields: `list_metafields`, `set_metafields`, `delete_metafield`
  (на любом owner-типе: Product/Order/Customer/Collection)
- Webhooks: `list_webhook_subscriptions`,
  `create_webhook_subscription`, `delete_webhook_subscription`
- Product Images/Media: `add_product_media`, `delete_product_media`

### Ярус 3 — value-add поверх нативных возможностей (bulk, аудит,
агрегация — то, что Imperal добавляет от себя)

- Bulk Operations: `run_bulk_query`, `get_bulk_operation_status`,
  `cancel_bulk_operation` — экспорт всего каталога/всех заказов без
  пагинации вручную
- `bulk_update_products` / `bulk_update_variant_prices` — explicit
  батч на 1-100 ids (тот же паттерн `apply_bulk_*` у WordPress Hub)
- `get_store_summary` — агрегированная сводка магазина (заказы за
  период, выручка, топ-товары) — аналог `get_store_summary` у
  WordPress Hub/WooCommerce, но на Shopify-домене
- `audit_shop_catalog` — health-скан каталога (товары без изображений,
  без описаний, с нулевым инвентарём везде, дубли SKU) — тот же
  принцип, что `audit_cloudhub_environment`/`audit_folder`

---

## 4. Что решено НЕ включать в этот заход (явный вырез, не забывчивость)

- **Storefront API** (витрина/checkout для покупателя) — другой домен
  ответственности, не про управление магазином.
- **Shopify Functions / Shopify Scripts** (кастомная логика ценообразования/
  чекаута на Wasm) — требует деплоя кода в сам Shopify, не укладывается в
  модель "коннектор через REST/GraphQL вызовы".
  на другой сегмент клиентов (продавцы, встраивающие Imperal В СВОЙ
  Shopify app), а не продавцы, использующие Imperal напрямую — тот же
  класс решения, что embedded/white-label API у Tray.io был исключён
  из первого захода Tray-коннектора.
- **Marketing/Email (Shopify Email, Segments)** — отдельный, менее
  зрелый API-поверхностный слой, не core commerce domain.
