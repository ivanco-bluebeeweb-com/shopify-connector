# Shopify Connector — Connector Discovery

**Дата discovery:** 2026-08-20
**Статус:** Ярусы 1-3 пройдены (свежее чтение официальной документации shopify.dev, 2026-08-20). §6 (решение по объёму) НЕ требует отдельного вопроса Владу — Влад заявил объём с первого сообщения по этому коннектору ("максимальный функционал, полный максимум"), что по `CONNECTOR_DISCOVERY_STANDARD.md` Шаг 5 действует как уже данный ответ. Берём Ярус 1 + Ярус 2 + Ярус 3.

---

## 1. Целевой сервис и источники

Shopify — крупнейшая e-commerce SaaS-платформа для независимых продавцов. В отличие от iPaaS-коннекторов портфеля (n8n/Make/Workato/Tray/Pipedream/MuleSoft/Power Automate/UiPath/Automation Anywhere/Blue Prism), это прямой коннектор к бизнес-домену продавца — каталог, заказы, клиенты, инвентарь, скидки, фулфилмент.

Источники (прочитаны 2026-08-20):
- `shopify.dev/docs/api/admin-graphql/latest/full-index` — полный индекс GraphQL Admin API
- `shopify.dev/docs/api/usage/versioning`, `shopify.dev/docs/api/usage/limits` — версионирование и rate limits (cost-based leaky bucket)
- `shopify.dev/docs/apps/build/authentication-authorization/access-tokens/*` — модель авторизации custom apps
- `shopify.dev/docs/api/usage/access-scopes` — access scopes
- `shopify.dev/docs/api/webhooks/latest`, `enums/WebhookSubscriptionTopic` — webhooks
- `shopify.dev/docs/api/usage/bulk-operations/queries`, `mutations/bulkOperationRunQuery`, `mutations/bulkOperationRunMutation` — bulk operations
- Объектные/мутационные страницы: `objects/Product`, `objects/Order`, `queries/collections`, `objects/fulfillment`, `objects/DiscountCodeNode`, `mutations/discountCodeBasicCreate`, `mutations/discountAutomaticBasicCreate`, `mutations/customerCreate`, `mutations/customerUpdate`, `mutations/metafieldsSet`, `queries/inventoryItem`, `objects/inventorylevel`, `mutations/inventorySetQuantities`, `mutations/inventoryAdjustQuantities`, `mutations/fulfillmentCreate`, `objects/FulfillmentOrder`, `mutations/refundCreate`, `mutations/draftOrderCreate`
- `shopify.dev/docs/api/usage/gids` — Global ID (GID) формат идентификаторов
- `shopify.dev/changelog/expiring-offline-access-tokens-required-for-public-apps-april-1-2026` — переход публичных приложений на expiring tokens
- Community threads (`community.shopify.dev`) о создании custom app токенов через Dev Dashboard (2026-переходное состояние)

## 2. Критично по этому приложению

1. **ДВЕ API-поверхности:** Admin API (управление магазином — наш охват) и Storefront API (витрина/checkout покупателя — чужой домен, вне охвата). Discovery фиксирует: коннектор строит только Admin API.
2. **Внутри Admin API — GraphQL-first, не REST.** Shopify активно продвигает GraphQL Admin API как основной интерфейс; у REST Admin API есть отдельный ресурс "Deprecated API calls" для трекинга устаревших вызовов. Коннектор строится на GraphQL Admin API целиком (одна конечная точка `/admin/api/{version}/graphql.json`), REST не используется вообще.
3. **Модель авторизации в переходном состоянии.** Custom apps, созданные ДО 1 января 2026, используют статичный non-expiring Admin API access token (классический путь: Settings → Apps and sales channels → Develop apps → Create app → Configure Admin API scopes → Install app → получить token один раз). Новые custom/public apps создаются через **Dev Dashboard**, и по официальному changelog публичные приложения переходят на **expiring offline access tokens** (обязательно с 1 апреля 2026) — требуется периодическая ре-авторизация/refresh, а не разовый статичный секрет. Для BYOK custom-app сценария (аналог остальных коннекторов портфеля) решение: коннектор просит **shop domain + Admin API access token**, созданный пользователем через Custom App (Settings → Develop apps) в его собственном магазине — простейший путь, не требующий OAuth redirect flow (аналогично тому, как Power Automate/MuleSoft просят готовые credentials, а не гоняют пользователя через redirect).
4. **Cost-based rate limiting (leaky bucket), не count-based.** У GraphQL Admin API нет фиксированного "N запросов/сек" — каждый запрос имеет расчётную "стоимость" (query cost), у магазина есть bucket ёмкостью (обычно 2000 для Standard/Advanced Shopify, restore rate ~100/сек) — ответ включает `extensions.cost` с `requestedQueryCost`/`actualQueryCost`/`throttleStatus`. Клиент обязан учитывать это (backoff на THROTTLED-ошибку), а не наивный HTTP-статус 429.
5. **Bulk Operations API — принципиально другая механика, не синхронный запрос-ответ.** `bulkOperationRunQuery`/`bulkOperationRunMutation` запускают асинхронную фоновую job; результат — JSONL-файл по URL, который нужно опрашивать (`currentBulkOperation` query) до статуса COMPLETED. Это Ярус 3 value-add кандидат: полезно для экспорта больших каталогов/заказов, требует собственного polling-обёртки, которой нет в остальном портфеле.
6. **Global ID (GID) формат** — все сущности идентифицируются строкой вида `gid://shopify/Product/123456789`, а не голым числовым id, как в REST. Это меняет форму каждого параметра `*_id` в схемах относительно REST-based коннекторов портфеля (WordPress Hub и т.п.) — важно на этапе Дизайна.

## 3. Карта возможностей (направление на каждую)

| Домен | Возможность | Ingress/Egress/Both | Комментарий |
|---|---|---|---|
| Products | list/get/create/update/delete products, variants, media | Both | Ядро каталога |
| Collections | list/get/create/update/delete custom & smart collections | Both | Группировка товаров |
| Orders | list/get orders, update (tags/note/metafields), cancel, close/reopen | Both | Ядро продаж |
| Draft Orders | create/update/complete/delete draft orders | Both | Ручные/телефонные продажи, инвойсы |
| Refunds | create refund (preview via `refundCreate` calculated fields), list refunds на заказе | Both | Возвраты денег |
| Fulfillment | list fulfillment orders, create fulfillment, cancel fulfillment, mark as complete | Both | Отгрузка |
| Customers | list/get/create/update/delete customers, customer addresses | Both | CRM-слой магазина |
| Inventory | list inventory items/levels, set/adjust quantities, connect/activate at location | Both | Складской учёт |
| Locations | list locations | Ingress | Нужны как контекст для инвентаря/фулфилмента |
| Discounts | create/update/delete code & automatic discounts (basic amount/percentage, free shipping, BXGY) | Both | Промо |
| Metafields | set/get/delete metafields на любой сущности (`metafieldsSet`/`metafieldDelete`) | Both | Кастомные данные |
| Webhooks | list/create/delete webhook subscriptions | Both | Уведомления о событиях (Ярус 2) |
| Bulk Operations | run/poll/cancel bulk query & mutation jobs | Both | Массовый экспорт/импорт (Ярус 3 инфраструктура) |
| Shop | get shop details (currency, plan, domain) | Ingress | Контекст магазина |
| Files/Media | stage upload + attach media to product | Egress | Загрузка изображений товара |

## 4. Ярус 1 — Ключевые функции (P0)

1. `connect_shopify` / `disconnect_shopify` / `list_connections` — shop domain + Admin API access token, проверка через `shop { name }` query
2. `list_products` / `get_product` / `create_product` / `update_product` / `delete_product`
3. `list_product_variants` / `update_product_variant`
4. `list_orders` / `get_order` / `update_order`
5. `list_customers` / `get_customer` / `create_customer` / `update_customer`
6. `list_collections` / `get_collection`
7. `get_shop_details`

## 5. Ярус 2 — Полное покрытие

| Возможность | Статус | Причина/триггер |
|---|---|---|
| Product/variant/collection CRUD | included | Ярус 1 |
| Order read + update (tags/note/metafields/cancel/close/reopen) | included | Основная операционная боль продавца |
| Draft orders (create/update/complete/delete) | included | Частый сценарий телефонных/ручных продаж |
| Refunds (calculate + create) | included | Реальный операционный кейс возвратов |
| Fulfillment orders + fulfillments (list/create/cancel) | included | Отгрузка — прямое продолжение заказов |
| Customers CRUD + addresses | included | Ярус 1 расширенный |
| Inventory items/levels (list/set/adjust quantities) | included | Складской учёт — частый разговорный кейс ("сколько осталось на складе") |
| Locations (list) | included | Обязательный контекст для инвентаря/фулфилмента |
| Discounts (code + automatic basic) | included | Явная маркетинговая функция, не редкая |
| Metafields (set/get/delete на product/order/customer) | included | Кастомные данные — частый кейс для сложных каталогов |
| Webhooks (list/create/delete subscriptions) | included | Событийная интеграция — естественное расширение read/write модели |
| Media/файлы (staged upload + attach to product) | included | Без картинок карточка товара неполноценна |
| Price rules / legacy discount API (REST) | not applicable | GraphQL-first решение (см. Критично п.2); legacy REST discount API не используется |
| Marketing Activities API | deferred | Отдельный, менее востребованный домен (кампании атрибуции) — добавить по явному запросу |
| Shopify Functions (custom checkout/discount logic на Wasm) | not applicable | Требует деплоя WASM-кода в само приложение продавца — не подходит под модель "агент вызывает API", это отдельный SDK/CLI процесс разработки |
| Shopify Flow triggers/actions (custom app extensions) | not applicable | Требует полноценного Shopify App с extensions-манифестом внутри самого Shopify — вне модели BYOK Admin API токена |
| B2B (Companies, Company Locations, Catalogs) | deferred | Нишевый enterprise-сценарий (продажи B2B-покупателям), добавить по явному запросу |
| Subscriptions (selling plans) | deferred | Требует отдельного платёжного провайдера контекста, нишевый кейс |
| Markets (мультивалютность/международные настройки) | deferred | Конфигурационный слой, реже нужен в разговорном сценарии |

## 6. Ярус 3 — Функции на нашей стороне (value-add)

- **`run_bulk_export`** — запускает `bulkOperationRunQuery` и сам поллит `currentBulkOperation` до завершения, отдавая готовую ссылку на JSONL — Shopify API даёт только async-примитив, но не готовое "подожди и покажи результат"
- **`bulk_update_products`** / **`bulk_update_inventory_levels`** — обёртки над множеством `productUpdate`/`inventorySetQuantities` вызовов по explicit id-списку в одном вызове (сервис отдаёт только по одной мутации за раз для этих сущностей)
- **`get_low_stock_products`** — агрегирующий отчёт: товары с суммарным остатком по всем локациям ниже порога, одним вызовом вместо ручного обхода `list_inventory_levels`
- **`audit_store_health`** — агрегирующий отчёт: товары без изображений, без описания, с нулевым остатком, заказы без исполнителя фулфилмента — по аналогии с `run_audit`/`audit_cloudhub_environment` в других коннекторах портфеля
- **preview-стиль подтверждение перед деструктивными операциями** (delete product/customer/collection, cancel order) — у Shopify GraphQL нет собственного dry-run для этих мутаций

## 7. Решение по объёму этого захода

Влад заявил объём явно с первого сообщения по этому коннектору: **"приступай к разработке приложения Shopify. максимальный функционал, полный максимум"**. По `CONNECTOR_DISCOVERY_STANDARD.md` Шаг 5 (исключение) это действует как уже данный ответ — берём **Ярус 1 + Ярус 2 + Ярус 3** без дополнительного вопроса. Переходим сразу к Фазе 3 (Дизайн) и Фазе 4 (Разработка).
