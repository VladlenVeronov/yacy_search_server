# search.newsgroup.site — Google Indexing Audit (2026-08-04)

## TL;DR

Сайт **crawlable, вміє віддавати правильні мета+JSON-LD**, але Google **не індексує ЖОДЕН URL**. Причина не технічна на нашому боці — це **domain-wide проблема `newsgroup.site`** (post-sitemap.xml 1001 URL / 0 indexed, тобто **вся materinsky домен не індексується**).

Ймовірна першопричина: Google Indexing API misuse (28.07.2026, задокументовано в memory) призвів до тимчасового зниження crawl-budget або soft-penalty на sc-domain.

---

## Що працює (не потребує фіксів)

| Перевірка | Статус | Деталі |
|---|---|---|
| `robots.txt` | ✅ | `ALLOWED` для Googlebot; `Sitemap:` + `Host:` директиви; CF managed OFF |
| `sitemap.xml` | ✅ | 8 URL, xhtml:link hreflang, valid XML |
| `<title>`, `<meta description>`, `og:*` | ✅ | UA-локалізовано, унікально per-page |
| `<link rel="canonical">` | ✅ | Self-referential на кожній сторінці |
| `<link rel="alternate" hreflang="uk" href="…">` + `x-default` | ✅ | Один і той же URL (uk-only сайт) |
| JSON-LD | ✅ | 2 блоки: `WebSite+SearchAction+Organization+SoftwareApplication` + `FAQPage` — валідні |
| CF security | ✅ | `security_level=medium`, `browser_check=off`, `bot_management.fight_mode=false`, `ai_bots_protection=block` (не блокує Googlebot) |
| Fetch as Googlebot | ✅ | HTTP 200, повний UA-HTML з мета/canonical/JSON-LD |
| GSC `robotsTxtState` | ✅ | ALLOWED |
| GSC `indexingState` | ✅ | INDEXING_ALLOWED |
| GSC `pageFetchState` | ✅ | SUCCESSFUL |
| GSC `googleCanonical` | ✅ | `https://search.newsgroup.site/` (правильно) |

## Що НЕ працює

### 1. `coverageState=Crawled - currently not indexed` для `/`

Google **бачив** сторінку (`lastCrawlTime=2026-03-27`), fetch пройшов, але вирішив **не індексувати**. Це не помилка, це **якісне рішення** Google. Причини цього verdict'у зазвичай:
- Низька якість/оригінальність контенту (на нашій головній — коротка hero+search box, мало тексту)
- Дублікат чи мала цінність для юзера в очах Google
- Global demote за domain-level інциденти

### 2. `lastCrawlTime=2026-03-27` — Google не заходив ~5 місяців

Це критично. Тобто:
- Останній краул був у березні (тобто ще до нашого SEO overhaul 19.07)
- Всі наші фікси (UA-мета, JSON-LD, 4 landing pages, sitemap) — Google **ще не бачив**
- `lastDownloaded` sitemap = 2026-07-19 (тільки ми його submittили, після цього Google не забирав)

### 3. Інші URL (`/About.html`, `/sitemap.xml`, landings): `URL is unknown to Google`

Крім `/`, Google просто **не знає про існування** цих URL. Sitemap submitted 19.07, але Google не пішов краулити його URLs (тільки перевірив факт існування самого sitemap).

### 4. `userCanonical=None` у GSC

Наш `<link rel="canonical" href="…">` є в HTML, але GSC показує `userCanonical=None` для головної. Це вказує на можливу проблему з парсингом (можливо `href` без trailing slash inconsistency, або Google не встиг парсити після 27.03 crawl).

### 5. Весь домен sc-domain:newsgroup.site — indexed=0

| Sitemap | submitted | indexed |
|---|---:|---:|
| post-sitemap.xml | 1001 | **0** |
| post-sitemap2.xml | 710 | **0** |
| sitemap_index.xml | 1019 | **0** |
| category-sitemap.xml | 6 | **0** |
| sitemap-news.xml | 6 | **0** |
| search.newsgroup.site/sitemap.xml | 8 | **0** |

Це загальна проблема ~newsgroup.site~ домену, не тільки search-піддомену. Ймовірно — наслідок Google Indexing API misuse (див. [[newsgroup_indexing_api_misuse]]).

---

## Що робити зараз (пріоритизовано)

### Ready-to-execute (без ризику)

1. **✅ ЗРОБЛЕНО**: `PUT /sitemaps` для `https://search.newsgroup.site/sitemap.xml` (2026-08-04 12:00 UTC — Google має пере-завантажити протягом кількох годин)
2. **⏳ Чекати**: 2-4 тижні на GSC "URL Inspection" щоб побачити чи стан змінився після нашого 19.07 SEO раунду
3. **⏳ IndexNow key**: `853fbf78b9954799abc51a1f0f6b400c.txt` вже сервиться, ping'и до api.indexnow.org+bing+yandex працюють

### Наступні кроки (потрібне узгодження)

4. **URL prefix property**: Зареєструвати `https://search.newsgroup.site/` як окремий property у GSC (не тільки як частину sc-domain). Дає:
   - Окремі метрики (impressions/clicks/CTR для search-піддомену)
   - Окрему verification
   - Кращий контроль sitemap-ів
   - Верифікація через DNS TXT або HTML meta (`google-site-verification=…`)

5. **Content depth** для `/`: наша головна сторінка коротка (hero + search box + мінімум тексту). Додати:
   - Секцію "Про VIR GOO" (~300 слів під hero)
   - Список нещодавніх популярних запитів
   - Секцію "Партнери" з внутрішньою перелінковкою
   - Це підвищить якість в очах Google для боротьби з "Crawled - not indexed"

6. **Внутрішні backlinks**: 
   - **Вже є**: newsgroup.site footer widget (WP) + vir.group hero "Екосистема" col
   - **Додати**: mail.vir.group + pro.vir.group + social.vir.group footer/nav — VIR GOO там ще не лінкований
   - Cross-linking piggybacks на любий чужий crawl-budget

7. **Newsgroup.site санація перш ніж рятувати search-піддомен**: 
   - `sc-domain:newsgroup.site` 0/1001 = domain-wide penalty
   - Треба виясняти окремо: чи GSC не має manual actions? Чи є Core Web Vitals проблеми? Чи є soft-404 масово?
   - Це окремий issue, більший ніж search-піддомен

### НЕ робити

- **❌ Google Indexing API** для звичайних сторінок — вже отримали покарання за це (memory: `newsgroup_indexing_api_misuse`). Використовується тільки для JobPosting/BroadcastEvent за Google policy.
- **❌ Bot spam** — cheap SEO-services які "надсилають ping": Google це ігнорує.
- **❌ Purchased backlinks** — миттєвий manual action penalty.

---

## Файли/скрипти

- Ping-скрипт: `/home/vir/newsgroup_seo/search_seo_push.py` (запуск під vir, Google Indexing API disabled; лишились IndexNow + Sitemap PUT)
- GSC SA: `/home/vir/.config/gcloud/newsagent-gsc.json` (email `oauth-client-id@newsagent-gsc.iam.gserviceaccount.com`, project `newsagent-gsc`)
- CF creds (local): `~/.config/cloudflare/credentials` (chmod 600)
- Zone ID: `d609530a59451a12e2bd149b571aed81`

---

## Наступний моніторинг

Одиничний тест через тиждень:
```bash
sudo -u vir python3 /home/vir/newsgroup_seo/scripts/gsc_inspect_search.py
```
Слідкувати за:
- `lastCrawlTime` — має оновитись після наступного Google візиту
- `coverageState` для лендінгів — має перейти з `URL is unknown` → `Crawled`
- `indexed` у sitemap → зростати
