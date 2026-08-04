# YaCy Admin UI Audit (2026-08-04) — знайдені баги + план

Аудит на живій адмінці (search.newsgroup.site) через Playwright + RAG-driven grep. Пройдено 5 pages: Dashboard_p, Crawler_p, IndexBrowser_p, ConfigNetwork_p, CrawlStartExpert.

## 🔴 Найкритичніші проблеми (visible на кожній сторінці)

### 1. Мовний хаос UA + EN + RU

Кожна admin page має **3 мови одночасно**:
- **UA sidebar** (наша нова оболонка): "КРАУЛЕР", "Черги", "Моніторатор краулера"
- **EN section headers** (легасі yacy шаблони): "Web Crawler", "Crawl Results", "Processing Monitor", "Queues", "Web Visualization"
- **RU inner content** (застаряле дефолтне українське `.lng` перекладено НЕ ПОВНІСТЮ, а YaCy fallback = **російська локалізація**): "Индексатор", "Очереди индексатора", "Размер индекса", "Ход работы", "Просмотр хостов", "Скорость (страницы в минуту)", "Сохранить", "Настройка сети"

**Root cause:** у `htroot/env/base.css` та legacy шаблонах текст — англійський. `htroot/locales/uk.lng` покриває тільки частину рядків. YaCy `TemplateEngine` при відсутності UA-перекладу відкатується на `ru.lng` (RU-локалізація повніша).

**Fix:**
- Знайти всі рядки з ru.lng які **не мають** UA-паралелей → додати в uk.lng
- Форсити fallback: `en.lng` замість `ru.lng` для UA-locale
- Довгостроково: перекласти секційні заголовки (`Web Crawler`, `Crawl Results`, etc.) або замінити на .template-based (з локалізацією)

### 2. Table overflow — Crawler_p "Размер индекса"

Header rows `БАЗА ДАННЫХ | ЗНАЧЕНИЯ | СЕГ...` — третя колонка обрізається (мала бути "Сегменты"). Container має fixed width, а table має 3+ колонок з довгими headers.

**Fix:** `.yg-main table { table-layout:auto; word-break:normal; overflow-x:auto }`; wrapping-div з `overflow-x:auto` для legacy tables.

### 3. IndexBrowser_p — search input label обрізаний

Label "Хо" (мало бути "Хост:") + поле input не має нормальної ширини. Legacy `<dl>/<dt>/<dd>` не адаптовано до нової сітки.

**Fix:** переписати блок пошуку хоста на flex-based input group з властивою шириною.

### 4. Dashboard cards показують "n/a" + все "DOWN"

- "СТОРІНОК В ІНДЕКСІ n/a", "ХОСТІВ УНІКАЛЬНИХ n/a", "ЗАПИТІВ ЗА ДОБУ —", "ЗАЯВКИ НА СКАН auth"
- "Vector service DOWN", "PostgreSQL+pgvector DOWN", "Redis cache DOWN" — **всі контейнери реально healthy!**
- "vector_service недоступний" внизу
- "Увійдіть як адмін, щоб побачити чергу" — АЛЕ МИ АДМІН!

**Root cause:** `Dashboard_p.java` не звертається до vector_service `/health` правильно (мабуть використовує `localhost:8001` замість `yacy-vector-service:8001`, або cred/token не пробрасується).

**Fix:** переглянути `Dashboard_p.java` — швидко, це один Java класс.

### 5. CrawlStartExpert.html — 49KB велетень з 23 inline `float:`

Візуально — стіна форм з мікшованим RU/EN, tooltip icons ⚠️/? розкидані, fieldset вкладено у fieldset. UX жахливий.

**Fix:** розбити на 3 tab-based секції (Basic / Advanced / Robots), заміна float+fieldset на flex-based cards.

---

## 🟠 Медіум-баги (не критично але видно)

### 6. Sidebar 🔒 lock icons

"Черги", "Завантажувач", "Помилки парсера" (Crawler section), "Керування URL", "Видалення з індексу" (Content section) — мають 🔒 icon. Незрозуміло: що він означає? Заблоковано для webmaster? Тільки для admin?

**Fix:** прибрати або пояснити (`title="Тільки адмін"` + toggle показу тільки для non-admin).

### 7. Форма Crawler_p "60 PPM 0 LF : MH"

Cluster полів без label alignment. Виглядає як ребус.

**Fix:** переверстати як grid label+input pairs.

### 8. Progress bars empty/thin

Скорость 0/тонкий сірий бар, Постобработка 00:00 бар пустий. Але виглядає як розколені.

**Fix:** progress bar CSS: min-height 8px, background rounded, color-code.

### 9. Fieldset + legend змішується з h2 sections

Deux рівні заголовків (h2 Web Crawler, fieldset legend PROCESSING MONITOR). CSS reset для legend замінює на span-style.

---

## 🟡 Косметика (можна пізніше)

### 10. Duplicated CSS rules у yacy-admin.css

`grep -nE 'font-size|h1|h2|h3' htroot/env/yacy-admin.css`:
- **Line 305-307** ТА **line 406-410** — обидва блоки визначають h1/h2/h3 з різними margin values!
- Cascade вирішує (останнє виграє), але це смердить. Debt.

**Fix:** видалити перший блок (line 305-307), лишити другий.

### 11. base.css використовує застарілі em/% font-size

`2em`, `1.6em`, `1.3em`, `1.1em`, `160%`, `90%` — успадкований XHTML стиль. Мішається з px в yacy-admin.css → **непослідовна типографія**.

**Fix:** конвертувати всі em/% → рem/px до відповідності yacy-admin.css scale (11/12/13/14/15/18/24).

### 12. Inline font-size chaos у HTML

16 різних значень: 8px/9px/10px/12px/13px/14px/16px/18px/0.85em/0.95rem/1.1rem/1.2rem. Скористатись `sed` для замін на CSS-classes.

### 13. 27 legacy admin файлів (AUDIT_htroot.md) все ще з refs

Blog/Wiki/Bookmarks/Messages/etc. — 22-27 файлів помічені `видалити`, але всі мають внутрішні refs (2-9 refs кожен). Треба скоординований cleanup: видалити HTML+видалити refs+видалити Java handlers одним махом.

### 14. XHTML 1.0 у 104 файлах з 171

Кожен файл починається з `<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN">` — старий стандарт. Треба масовий batch-конвертер до `<!DOCTYPE html>`.

### 15. jQuery у 9 файлах

`ConfigSearchPage_p.html`, `Network.html`, кілька yacychat* — треба замінити на native JS (fetch, querySelector).

### 16. 38 файлів з deprecated attrs

`bgcolor=`, `align="right"`, `cellpadding=`, `cellspacing=` — деякі browsers все ще парсять, але a11y-tools/SEO страждають.

---

## Пріоритизований action plan

### Фаза A (швидкий win, 1 сесія — ~2 год)

1. **Fix Dashboard_p.java** — з'єднання з vector_service (топ пріоритет — flagship page)
2. **Fix table overflow** у yacy-admin.css (`.yg-main table { table-layout:auto; overflow-x:auto }`) — global fix для всіх сторінок з tables
3. **Прибрати дублікати h1/h2/h3** у yacy-admin.css (line 305-307)
4. **Sidebar lock icons** — прибрати або пояснити
5. **UA-локалізація hot-pages** — Crawler, IndexBrowser, ConfigNetwork (додати найкритичніші строки в uk.lng)

Комміт: `admin: dashboard-service fix + table overflow + h1/h2/h3 dedup + hot-page UA localization`

### Фаза B (типографіка, 1 сесія)

6. **Уніфікувати font-size у base.css** — конвертувати em/% → px scale (11/12/13/14/15/18/24) 
7. **Remove inline font-size** з HTML — sed за pattern
8. **Fix input+form spacing** у yacy-admin.css — form-grid classes

Комміт: `admin: unified typography — base.css font-size migration + form-grid utility classes`

### Фаза C (legacy cleanup, 1-2 сесії)

9. **XHTML → HTML5 batch** — script що replaceну DOCTYPE у 104 файлах
10. **jQuery removal** — 9 файлів, замінити на native
11. **Deprecated attrs cleanup** — sed для bgcolor/align/cellpadding

Комміт: `admin: legacy XHTML/jQuery/deprecated-attrs cleanup — HTML5 doctype, native JS, semantic attrs`

### Фаза D (структурні переписи, за AUDIT_htroot.md)

12. Переписати `CrawlStartExpert.html` (49KB → 3 tab-based)
13. Переписати `Network.html`, `ConfigSearchPage_p.html`
14. Видалити 22 legacy файли (+ їх refs та Java handlers)

### Фаза E (Dashboard-level facelift)

15. Заміна fieldset+legend на card-based UI
16. Заміна table-based layouts на flex/grid у топ-10 pages
17. Sortable/searchable tables (JS class без jQuery)

---

## Скрін-документація

- `admin-audit-01-dashboard.png` — Dashboard_p (все n/a, сервіси DOWN хибно)
- `admin-02-crawler.png` — Crawler_p (RU "Индексатор", table overflow, form chaos)
- `admin-03-indexbrowser.png` — IndexBrowser_p (RU "Просмотр хостов", label "Хо" обрізане)
- `admin-04-confignetwork.png` — ConfigNetwork_p (стіна RU-полів)
- `admin-05-crawlstartexpert.png` — CrawlStartExpert (49KB monster з inline float:)
