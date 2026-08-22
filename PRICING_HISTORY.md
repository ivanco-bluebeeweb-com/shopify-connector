# Pricing History — Shopify Connector

## 2026-08-22 — повторное подтверждение цены и отправка на ревью

При `update_pricing` с полной картой из `tool-prices.json` первый вызов
вернул `'connect_shopify'/'disconnect_shopify'/'list_connections'
unexpectedly still priced` — тот же паттерн, что пойман в этот день на
Salesforce/Klaviyo/HubSpot/Webflow/MuleSoft (задача #2275 в трекере
Imperal Cloud: транзиентное расхождение именно по `free_tools`,
устраняется немедленным повтором идентичного payload). В отличие от тех
пяти приложений, `shopify-connector` НЕ вернул ошибку "is live, pricing
can't change mid-flight" — значит на момент этой попытки он ещё не был
live, `suspend_app` не потребовался. Второй вызов прошёл без ошибки, цена
подтверждена сохранённой. `deploy_app` → 20/21 (commit ddaa9ec7) →
`submit_for_review` → статус `pending_review`.


Обязательный журнал: каждое выставление или изменение цен на функции этого
приложения фиксируется здесь — что изменилось, почему, и на основании
чего. Не переписывать прошлые записи — только дописывать новые сверху.

---

## 2026-08-20 — первичное выставление цены (до submit_for_review)

Прайсинг выставлен **до** `submit_for_review`, по порядку, закреплённому в
каноническом `PRICING_POLICY.md` §1 (правило, переформулированное именно
из-за инцидента с MuleSoft Connector — см. его собственный
`PRICING_HISTORY.md`). Никакого нарушения тут не было: код готов → чистый
`imperal validate` (0 ошибок, 0 предупреждений) → `deploy_app` →
`update_pricing` → только потом `submit_for_review`.

**Модель:** `per_action`, шкала строго по канонической таблице
`{0, 8, 16, 20, 40, 60}` (раздел 2 `PRICING_POLICY.md`). Shopify Admin API
не относится к Google Cloud/Workspace — маркап ×1.8 (раздел 5) не
применяется.

**Логика категоризации 50 функций:**
- `0` — подключение/список соединений (`connect_shopify`,
  `disconnect_shopify`, `list_connections`) — тот же паттерн, что у
  MuleSoft/Power Automate/n8n.
- `8` — простые чтения (list/get: products, collections, orders,
  fulfillment orders, customers, locations, inventory levels, discounts,
  metafields, webhooks, bulk operation status).
- `16` — обычные записи одного ресурса (create/update/delete product,
  variant, collection membership, customer, inventory set/adjust,
  discount create/delete, metafield set/delete, webhook create/delete,
  order note update, cancel_bulk_operation).
- `20` — более рискованные/составные операции над заказами (cancel_order,
  create/complete draft order, refund_order, create/cancel fulfillment).
- `40` — Tier 3 value-add отчёты, требующие нескольких композированных
  чтений (`get_low_stock_report`, `get_store_summary`) — тот же уровень,
  что `audit_cloudhub_environment`/`get_stale_applications` у MuleSoft.
- `60` — тяжёлая асинхронная операция большого объёма
  (`run_bulk_query` — Shopify Bulk Operations API, экспорт всего каталога/
  всех заказов) — тот же уровень, что bulk_* операции у MuleSoft.

**Метод применения — `developer.update_pricing`** (подтверждённо рабочий
метод по прецеденту n8n Connector 2026-08-19 и MuleSoft Connector
2026-08-20). `pricing_config` передан как настоящий JSON-объект (не
экранированная строка), `revenue_split_dev=95` передан ЯВНЫМ параметром
вызова (не только внутри `pricing_config`), по тому же обязательному
правилу.
