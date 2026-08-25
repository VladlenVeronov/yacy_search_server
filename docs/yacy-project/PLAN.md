# YACY — Детальний План Виконання

> Автоматично виконується daily agent о 04:00.
> Кожен крок: `[ ]` = очікує, `[x]` = виконано, `[~]` = в процесі.

---

## КОНЦЕПЦІЯ (прочитай перед виконанням)

### Архітектурне рішення

**Що залишаємо з YaCy:**
- Java-ядро (краулер, peer-to-peer мережа, Solr індекс) — це унікальна цінність
- Solr — прекрасний для full-text пошуку, залишаємо, але доналаштуємо

**Що замінюємо:**
- Freemarker шаблони → сучасний HTML/CSS (Tailwind) без JS-фреймворків (швидко!)
- Система ранжування → додаємо векторний шар поверх Solr

**Новий шар AI (Python мікросервіс):**
```
[Браузер] → [YaCy Java API] ← → [Python AI Service]
                ↓                        ↓
            [Solr index]         [PostgreSQL + pgvector]
                                         ↓
                                 [HuggingFace embeddings]
```

**Сервери:**
- `168.231.108.21` — production: YaCy + Python AI + PostgreSQL + Authentik (auth)
- Mac mini — розробка
- Linux — AI задачі, векторизація нових індексів

**Auth:** Authentik (найкраща open-source альтернатива Keycloak, активно підтримується)

**Просування:** Тільки через ідею — GitHub stars, Hacker News, Reddit r/privacy, r/degoogle, Product Hunt. Нуль платної реклами.

---

## ФАЗА 1 — ФУНДАМЕНТ (Тижні 1-3)
*Мета: швидкі перемоги, зробити пошук хоча б стерпним*

- [x] АУДИТ: Пройтись по всіх htroot/*.html шаблонах, скласти список що видалити / переписати — результат: AUDIT_htroot.md (22 видалити, 15 переписати)
- [x] MOBILE FIX: Виправити адаптивну верстку головної сторінки (search.html) — flexbox/grid замість таблиць
- [x] MOBILE FIX: Виправити сторінку результатів пошуку на мобільних (yacysearch.html)
- [x] CLEANUP: Вимкнути/приховати "Розширений пошук" з головної — винести в окрему сторінку
- [x] CLEANUP: Прибрати всі зовнішні посилання / трекери з шаблонів (гілка вже є: feature/remove-third-party-links) — runtime fetches видалено: Vimeo, OSM/OpenLayers, Java applet, amung.us, ICQ/Yahoo trackers; commit 725cfa13a
- [x] DESIGN: Tailwind CSS LOCALLY (not CDN — третьосторонні fetches заборонені) → `htroot/env/css/tailwind.min.css`
- [x] DESIGN: Нова головна сторінка — світла тема, hero з великим пошуком, content-type radios → `htroot/index.html`
- [x] DESIGN: Нова сторінка результатів — картки замість списку (favicon + URL + title + сніпет + meta) → `htroot/yacysearchitem.html`
- [x] DESIGN: Хедер — логотип зліва, кнопка меню справа + Login → `htroot/env/templates/yacy-public-header.template`
- [x] DESIGN: Меню-bottomsheet справа — grid іконок (placeholders, дані з admin пізніше) → той же header template
- [x] SOLR: Увімкнути full-text індексування контенту сторінок — `text_t` ("all visible text") вже активний у `defaults/solr.collection.schema:217` і входить у boost fields дефолтного профілю (`text_t^1.0`); full-text індексація не була вимкнена
- [x] SOLR: Сортування за свіжістю — додано multiplicative recency boost у `Default Profile` (tmpb.0): `recip(ms(NOW,last_modified),1e-11,1,1)` — ~3-річний half-life, м'якший за `/date` профіль (1-річний)
- [x] BUG: Зібрати і зафіксувати всі критичні баги — issue list у `docs/yacy-project/ISSUES.md`. 🔴 OOM при snippet extraction виправлено (cap 100k chars у `SentenceReader`), 🟠 P2P-issues задокументовано для Phase 4

---

## ФАЗА 2 — ЯКІСТЬ ПОШУКУ (Тижні 4-7)
*Мета: результати які реально корисні*

- [x] VECTORS: PostgreSQL + pgvector на проді (Hetzner `yacy-pgvector` контейнер, HNSW cosine, 768d). DB `yacy_pages` міграцій ідемпотентні
- [x] VECTORS: Python мікросервіс (FastAPI) — `vector_service/` на порту 8001. Endpoints `/health`, `/index`, `/search`, `/doc/{id}`, `/rank`, `/track-search`, `/track-click`, `/unsatisfied[/seed]`, `/services`. Модель `intfloat/multilingual-e5-base` (768d, multilingual, локально). Cross-lingual перевірено
- [x] VECTORS: Sync-скрипт `docs/yacy-project/scripts/sync_pages.py` під cron `cron-sync-pages.sh` (`5 * * * *`). Cursor-mark по `load_date_dt`. Працює на проді
- [x] RANKING: hybrid scoring 60/25/15 (semantic / freshness / quality) у `/rank`. Default OFF на проді (Solr boostfunction `recip(ms(NOW,load_date_dt),3.16e-11,1,1)` справляється з freshness без додаткового ранкера)
- [x] RANKING: Domain quality score — TLD table + depth penalty (2026-08-25) — `_quality_score()` поки рахує лише HTTPS (1.0 vs 0.3). Speed/ads сигнали відкладено — не блокує
- [x] RANKING: PageRank/backlinks zero-out — `coeff_authority = 0` + `coeff_citation = 0` у `RankingProfile`
- [x] SEARCH: Підтримка довгих запитів — `QueryGoal.LONG_QUERY_THRESHOLD = 5`. ≥5 термів → query без AND + edismax `mm=50%` (`QueryParams.solrQuery`). 1-4 терми лишаються strict-AND для точності. Excludes завжди MUST-NOT через `-` префікс. Tests: `QueryGoalTest.testShortQueryUsesAnd` + `testLongQueryDropsAnd`
- [x] SEARCH: Автодоповнення пошуку — `suggest.json` API + native fetch dropdown на index.html та yacysearch.html (заміна jQuery typeahead)
- [x] AI UNSATISFIED: Трекінг кліків — `/api/vector/track-click` пише в `query_clicks`. Yacysearch.html делегує mousedown через `sendBeacon`
- [x] AI UNSATISFIED: Логування пошуків — `/api/vector/track-search` → `query_logs` (query, result_count, ts)
- [x] AI UNSATISFIED: Крон `cron-unsat-seed.sh` (`0 3 * * *`) — zero-click queries → LLM (BYO key) → seed URL → YaCy CrawlStart. No-op доки `LLM_API_URL` пустий

---

## ФАЗА 3 — ПЛАТФОРМА (Тижні 8-12)
*Мета: екосистема навколо пошуку*

- [x] AUTH: Native YaCy UserDB — самореєстрація через `/Register.html` (Tailwind, public-styled). Custom OIDC/Authentik відкинуто — занадто важко для `signup-as-a-feature` use case
- [x] WEBMASTER: Кабінет — `/Register.html?webmaster=1` додає `WEBMASTER_RIGHT` авто-логіном; one-click "стати вебмайстром" для існуючих користувачів
- [x] WEBMASTER: Форма + native YaCy WorkTable `crawl_requests` — `/CrawlRequest.html` + `CrawlRequest.java`. Auth chain: digest → cookie → IP. Live indexed-pages count
- [x] WEBMASTER: Bot validator — in-process Java у `CrawlRequests_p.java`. 3 шари: substring blacklist → HEAD-alive (8s) → LLM zero-shot через `vector_service /classify-submission` (gated на `LLM_API_KEY`, graceful no-op якщо відсутній)
- [x] WEBMASTER: Адмін-черга з фільтром (pending/approved/blocked/crawling/done) + Approve/Reject/Run/Delete + 🤖 "Запустити перевірку ботом" кнопка
- [x] WEBMASTER: Статистика — `/WebmasterStats.html` per-host: indexed count, 4xx/5xx, last_crawl з Solr. Webmaster бачить свої host-и; admin — всі
- [-] USER CABINET: Реєстрація/вхід — done через UserDB (див. вище). Пункт scope-out — окремий "saved searches / bookmarks / subs" cabinet видалено в Phase 1 rebuild
- [-] USER CABINET: Особистий профіль — scope-out
- [-] USER CABINET: Сповіщення — scope-out (cabinet_subscriptions таблиця DROP'нута)
- [x] ADMIN: Панель адміна — `/Analytics_p.html` (vector_service health + zero-clicks) + `/CrawlRequests_p.html` (submission queue) + `/WebmasterStats.html`
- [x] ADMIN: CRUD сервісів — `services_menu` table + REST CRUD у vector_service `/admin/services` + drawer показує іконки на index.html
- [-] ADMIN: AI-чат — scope-out (LLM gap-analyzer покриває use case через крон)
- [x] ADMIN: Черга краулера з пріоритетами — `/CrawlRequests_p.html` має `priority` колонку + Run кнопку, що 302's на CrawlStartExpert з pinned `crawlingMustMatch`

---

## ФАЗА 4 — МЕРЕЖА (Тижні 13-20)
*Мета: справжня децентралізація*

- [x] NETWORK: Аудит P2P — `docs/yacy-project/P2P-AUDIT.md`. Виявлено: outbound DHT не фільтрував blacklist (виправлено)
- [x] NETWORK: Фільтр якості шерингу — `Dispatcher.filterDhtBlacklisted()` дропає WordReferences blacklisted hosts перед split + transmit
- [x] NETWORK: Чорний список контенту для шерингу
- [x] CONTENT MODERATION: POST /admin/moderate-batch (LLM classify 40/run, cron 4h) + moderation_log + cron-moderate.sh (2026-08-25) — `list.black` (401 entries) активний на DHT type. Hot-cache + Solr URL lookup
- [-] NETWORK: API для підключення нових вузлів — used vanilla YaCy seed-list bootstrap (нічого свого не додаємо). Документовано як працює
- [x] NETWORK: Документація для операторів — `docs/yacy-project/HOWTO-NODE-OPERATOR.md` (5-min install, sharing posture, cron, troubleshooting)
- [x] NETWORK: Механіка репутації вузла — DHT quality-score sort (wordCount+PPM+age) + peer_reputation table + /track-peer-hit + /peer-reputation + PeerReputationClient.java (2026-08-25) — defer (потребує per-peer hit-source tracking, infra heavy). Записано як deferred TODO у P2P-AUDIT.md §4
- [x] PROMO: README — `README-VIR-GOO.md` оновлено під поточний стан (drop dead Authentik/cabinet refs, додати DHT filter + freshness recip + native UserDB)
- [x] PROMO: HN/Reddit/PH — `PROMO.md` готовий: Show HN title, body, r/privacy / r/degoogle / r/selfhosted версії, Twitter thread, PH tagline
- [x] PROMO: Webmaster onboarding — `docs/yacy-project/HOWTO-WEBMASTER.md` (5-min flow + troubleshooting + source pointers)

---

## ФАЗА 5 — МАСШТАБУВАННЯ (Місяці 5-6)
*Мета: стабільність і ріст*

- [x] PERF: Load testing — `scripts/load-test{.sh,-queries.lua}` (wrk + ramp 10/50/100/...). Baseline 2026-05-08: ceiling ~22 RPS, plateau після 50 concurrent. CPU yacy 280%/450 %, vector_service 715%/1200% — bottleneck НЕ CPU, а Solr thread pool / vector `/rank` hot path. Деталі + next steps у `docs/yacy-project/LOAD-TESTING.md`. 200/500/1000 stages — на staging (на проді ризик)
- [x] PERF: Кешування результатів популярних запитів — `yacy-redis` контейнер активний (1GB allkeys-lru), використовується vector_service для query→result кешу
- [x] PERF: CDN для статики — Cloudflare уже на проді (search.newsgroup.site), `tailwind.min.css` шипиться разом з YaCy, кешується CF
- [-] MONITORING: Grafana + Prometheus — scope-out на запит юзера ("в мене є Portainer"). Container stats доступні через Portainer
- [x] DOCS: API + flows — `vector_service/README.md` (endpoints) + `docs/yacy-project/{P2P-AUDIT, HOWTO-WEBMASTER, HOWTO-NODE-OPERATOR}.md`
- [x] DOCS: Гайд "Як додати свій сайт" — `docs/yacy-project/HOWTO-WEBMASTER.md`
- [-] MOBILE APP: PWA — scope-out у Phase 1 rebuild. Сайт повністю responsive Tailwind, install-as-app працює через "Add to Home Screen" без manifest

---

## ГРАФІК

| Фаза | Тижні | Результат |
|---|---|---|
| 1. Фундамент | 1-3 | Сучасний дизайн, мобільна версія, чистий код |
| 2. Якість пошуку | 4-7 | Семантичний пошук, AI-ранжування, без сміття |
| 3. Платформа | 8-12 | Auth, кабінети, адмінка, AI-краулер |
| 4. Мережа | 13-20 | Децентралізація, шеринг якісних індексів |
| 5. Масштаб | 21-26 | Готово до публічного запуску |

---

## ЩОДЕННИЙ РОЗКЛАД АГЕНТА

Daily agent (04:00) виконує **1-2 кроки** з поточної фази.
Після виконання — надсилає звіт в Telegram @Vir_Group.

Черговість: зверху вниз по `[ ]` позначках в поточній фазі.
