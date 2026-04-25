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

- [~] VECTORS: PostgreSQL + pgvector — локально на Mac ✅ (DB `yacy_pages`, HNSW cosine). Прод `168.231.108.21` — ще не розгорнуто
- [x] VECTORS: Python мікросервіс (FastAPI) — `vector_service/` на порту 8001. Endpoints `/health`, `/index`, `/search`, `/doc/{id}`. Модель `intfloat/multilingual-e5-base` (768d, multilingual, локально). Idempotency через content_hash. Cross-lingual перевірено (UA query → EN doc)
- [x] VECTORS: Sync-скрипт `docs/yacy-project/scripts/sync_pages.py` — cursor-mark пагінація по Solr `collection1`, state-file у `docs/yacy-project/.sync_pages.state` (gitignored), `load_date_dt` як watermark. Готове під cron nightly
- [x] RANKING: Реалізувати hybrid scoring = 60% semantic similarity + 25% freshness + 15% domain quality — `/rank` endpoint у `vector_service/main.py`. Ваги в `config.py` (`weight_semantic` / `weight_freshness` / `weight_quality`), freshness через exp decay (half-life 365 днів). Кандидати без embedding не випадають — лишаються з semantic=0
- [~] RANKING: Domain quality score — не кількість беклінків, а: HTTPS + швидкість + без реклами/трекерів — поточна версія в `_quality_score()` рахує лише HTTPS (1.0 vs 0.3). Швидкість + ads/трекери чекають crawl-time сигналів з боку YaCy
- [ ] RANKING: Видалити або мінімізувати вплив PageRank/backlinks на ранжування
- [~] SEARCH: Інтеграція векторного пошуку в YaCy — Python сервіс як додатковий ранкер. Зроблено: `VectorRankClient` (нова клас `source/net/yacy/search/ranking/VectorRankClient.java`), хук у `SearchEvent.addNodes()` робить один `/rank` POST на батч Solr-кандидатів, `addResult()` застосовує hybrid score замість легасі `score*128 + postRanking`. Конфіг через env (`VECTOR_RANK_ENABLED`/`URL`/`TIMEOUT_MS`) з fallback на `vector_rank.*` у `yacy.init`. Default OFF. Локальна латентність ~20ms після прогріву. Залишилось: RWI-результати поки лишаються з оригінальним ranking — потребує hook у `drainRWIStackToResult` (Solr-результати домінують у топі тож вплив незначний)
- [ ] SEARCH: Підтримка довгих запитів (зараз обрізає) — збільшити ліміт, semantic chunking
- [ ] SEARCH: Автодоповнення пошуку — на базі популярних запитів з БД
- [ ] AI UNSATISFIED: Трекінг кліків — якщо 0 кліків на результати → запит незадоволений
- [ ] AI UNSATISFIED: Логування незадоволених запитів в PostgreSQL
- [ ] AI UNSATISFIED: Крон: аналіз незадоволених запитів → пошук відповідних ресурсів → черга краулера

---

## ФАЗА 3 — ПЛАТФОРМА (Тижні 8-12)
*Мета: екосистема навколо пошуку*

- [ ] AUTH: Встановити Authentik на сервері (Docker) — open-source SSO
- [ ] AUTH: Інтегрувати Authentik з YaCy для авторизації
- [ ] WEBMASTER: Кабінет вебмастера — сторінка для подачі сайту на індексування
- [ ] WEBMASTER: Форма: URL + контакт email → запис в PostgreSQL → перевірка роботом
- [ ] WEBMASTER: Фільтр перевірки сайтів — автоматична перевірка на: спам, порно, казино, пропаганда
- [ ] WEBMASTER: Статистика для вебмастера — скільки разів знайдено, позиція в пошуку
- [ ] USER CABINET: Реєстрація/вхід через Authentik
- [ ] USER CABINET: Особистий пошуковий профіль — збережені запити, закладки
- [ ] USER CABINET: Сповіщення — підписка на пошуковий запит (нові результати → повідомлення)
- [ ] ADMIN: Панель адміна — список ресурсів для меню сервісів
- [ ] ADMIN: CRUD для ресурсів: назва + URL + іконка (upload) → зберігається в PostgreSQL
- [ ] ADMIN: AI-чат для адміна — "нам не вистачає контенту про X" → завдання краулеру
- [ ] ADMIN: Черга краулера з пріоритетами — виконується в години низького трафіку

---

## ФАЗА 4 — МЕРЕЖА (Тижні 13-20)
*Мета: справжня децентралізація*

- [ ] NETWORK: Аудит існуючого P2P механізму YaCy — що залишити, що переписати
- [ ] NETWORK: Фільтр якості для шерингу індексів — не ділимось сміттям з мережею
- [ ] NETWORK: Чорний список контенту для шерингу (порно, казино, пропаганда, спам)
- [ ] NETWORK: API для підключення нових вузлів до мережі
- [ ] NETWORK: Документація для операторів вузлів — як запустити свій вузол
- [ ] NETWORK: Механіка репутації вузла — вузли які дають якісні індекси отримують більше запитів
- [ ] PROMO: README оновлення — чітке пояснення чим відрізняємось від Google
- [ ] PROMO: Підготовка до публікації на Hacker News / Reddit r/privacy
- [ ] PROMO: Product Hunt сторінка

---

## ФАЗА 5 — МАСШТАБУВАННЯ (Місяці 5-6)
*Мета: стабільність і ріст*

- [ ] PERF: Load testing — знайти вузькі місця при 1000+ одночасних запитів
- [ ] PERF: Кешування результатів популярних запитів (Redis або in-memory)
- [ ] PERF: CDN для статики (CloudFlare free tier)
- [ ] MONITORING: Grafana + Prometheus на сервері — метрики пошуку, краулера, БД
- [ ] DOCS: Документація API для розробників
- [ ] DOCS: Гайд "Як додати свій сайт"
- [ ] MOBILE APP: Розглянути PWA або легкий мобільний клієнт

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
