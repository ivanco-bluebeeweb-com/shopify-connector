# Shopify Connector — UI component plan

Источники: `ui-primitives-reference.md`, `UI_INTERFACE_STANDARD.md`, `concepts/panels.md`.
Основано на `POST_CONNECT_EXPERIENCE.md` этого приложения.

## 1. Компоненты

| Экран | Примитивы | Почему именно эти |
|---|---|---|
| Sidebar (left) | `ui.Column`(align="start") + `ui.Text`(shop domain) + `ui.Divider` + navigation `ui.ListItem`(Orders/Products/Customers/Inventory) + `ui.Button`("App settings") | Без карточек по стандарту; домен магазина как контекстная метка наверху. |
| Orders Dashboard (center, `center_overlay=True`) | `ui.Stats`(Sales today/Open orders/Fulfillment rate) + `ui.DataTable`(order#, customer, total, status Badge, date; sortable, filterable через `ui.Select` над таблицей) | `DataTable` с сортировкой/фильтром — стандартный способ работы с потоком заказов. |
| Order Detail | Back-button + `ui.KeyValue`(customer/shipping/payment) + `ui.DataTable`(read-only line items: product/qty/price, columns без editable) + `ui.Timeline`(placed→paid→fulfilled→delivered) + `ui.Row`(Button "Fulfill", "Refund", "Cancel") | `DataTable` без editable-колонок — стандартный способ показать переменное число позиций заказа (в SDK нет отдельного read-only repeater, см. `UI_COMPONENT_VOCABULARY.md` §4); `Timeline` — естественная репрезентация жизненного цикла заказа. |
| Product Catalog | `ui.DataTable`(image thumb via `ui.Image` в ячейке, title, price, inventory qty, status) + `ui.Button`("Добавить товар") | Наглядный каталог с превью — обязателен `Image` в колонке. |
| Product Editor | `ui.Form`(action="update_product") + `ui.Input`(title) + `ui.TextArea`(description) + `ui.Input`(type="number", price) + `ui.Input`(type="number", inventory_qty) + `ui.MultiSelect`(collections) + `ui.FileUpload`(accept="image/*", multiple=True — product photos) | Полный набор полей товара; `FileUpload` с `accept="image/*"` — это и есть загрузка изображений в SDK (нет отдельного ImageUpload, см. `UI_COMPONENT_VOCABULARY.md` §4). |
| Inventory Alert Panel | `ui.List`(low-stock items) + `ui.Badge`("Low stock"/"Out of stock") | Явный список товаров, требующих внимания, с цветовым статусом. |
| Customer Detail | `ui.KeyValue`(contact/address) + `ui.Stats`(lifetime value/orders count) + `ui.Timeline`(order history) | LTV и история заказов — ключевые данные для сегментации клиента. |
| Discount/Promo Builder | `ui.Form`(action="create_discount") + `ui.Select`(param_name="discount_type", options=[percentage,fixed_amount]) + `ui.Input`(type="number", value) + `ui.DatePicker`(starts_at) + `ui.DatePicker`(ends_at) | `Select` с двумя опциями заменяет несуществующий RadioGroup; период действия — два отдельных `DatePicker` (в SDK нет DateRangePicker), см. `UI_COMPONENT_VOCABULARY.md` §4. |
| App Settings | `ui.Accordion`([Connections+Disconnect, Webhooks CRUD, Default Fulfillment Location]) | Централизованные настройки по стандарту. |

## 2. User flow

1. **SESSION INIT** → `__panel__shopify_sidebar` рендерит домен магазина + разделы,
   `auto_action` открывает Orders Dashboard по умолчанию (самый частый первый вопрос —
   "что с заказами сегодня").
2. Orders Dashboard: Stats + отфильтрованный (Select "Статус заказа", плейсхолдер
   "Все статусы") DataTable → клик на строку → `ui.Call(order_id=...)` на тот же
   center handler → Order Detail.
3. На Order Detail: кнопка "Fulfill" → `ui.Dialog` подтверждения (не деструктивно, но
   необратимо для клиента — письмо о доставке уйдёт) → `ui.Call` →
   `refresh_panels=["shopify_orders"]`.
   Кнопка "Refund"/"Cancel" — обязательный `ui.Dialog` (деструктивно/финансово).
4. Раздел "Products" → DataTable каталога → клик "Добавить товар" открывает Product
   Editor как center overlay поверх текущего списка → submit → `refresh_panels`
   каталога, форма закрывается.
5. Раздел "Inventory" (или встроенная секция внутри Products) → List low-stock item'ов
   → клик на товар переоткрывает Product Editor с предзаполненным `inventory` полем.
6. Раздел "Customers" → DataTable → клик → Customer Detail (Stats LTV + Timeline
   заказов).
7. "App settings" → Accordion: Connections (rotate/disconnect с подтверждением),
   Webhooks, Default Fulfillment Location (Select).

## 3. Конкретные экраны (screens)

### Screen: Orders Dashboard (`shopify_orders`, default)
- Stats row: `Sales today`, `Open orders`, `Fulfillment rate`.
- Select "Статус заказа" (placeholder "Все статусы") над DataTable.
- DataTable: order#, customer, total, status Badge, date — row-click → Order Detail.

### Screen: Order Detail (`shopify_orders` + `order_id`)
- Back-button "← К заказам".
- KeyValue: customer name/email, shipping address, payment method.
- Repeater (read-only): line items с qty/price/product thumb.
- Timeline: placed → paid → fulfilled → delivered.
- Row of Buttons: Fulfill / Refund / Cancel (последние два через Dialog-подтверждение).

### Screen: Product Catalog (`shopify_products`)
- Button "Добавить товар" вверху справа.
- DataTable: Image thumb, title, price, inventory (с Badge low-stock), status.
- Row-click → Product Editor (та же center-панель, параметризована `product_id`).

### Screen: Product Editor (`shopify_products` + `product_id` или новый)
- Form: TextInput "Название товара" (placeholder "Например, Футболка хлопковая"),
  TextArea "Описание" (placeholder "Опишите товар для покупателей"),
  NumberInput "Цена" (placeholder "0.00"), NumberInput "Остаток на складе"
  (placeholder "0"), MultiSelect "Коллекции" (placeholder "Выберите коллекции"),
  ImageUpload "Фотографии товара".
- Button "Сохранить" внизу формы.

### Screen: Customers (`shopify_customers`)
- DataTable: name, email, orders count, LTV, last order date.
- Row-click → Customer Detail: KeyValue контактов + Stats (LTV/orders) + Timeline
  истории заказов.

### Screen: App settings (`shopify_settings`)
- Accordion "Подключение": статус магазина, Rotate/Disconnect (Dialog-подтверждение).
- Accordion "Webhooks": List + Button "Добавить" → Dialog с TextInput URL + чекбоксы
  событий (order created/updated/fulfilled).
- Accordion "Локация по умолчанию": Select для fulfillment location.
