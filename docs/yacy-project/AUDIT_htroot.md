# Аудит htroot/*.html — 134 шаблони

**Дата:** 2026-04-01  
**Всього файлів:** 134 HTML шаблони  
**XHTML (старий DOCTYPE):** 107 файлів  
**HTML5 (сучасний DOCTYPE):** 21 файл  

---

## ВИДАЛИТИ (Legacy / мертвий функціонал — 22 файли)

### P2P соціальні функції (повністю застарілі)
- `Blog.html` + `BlogComments.html` — вбудований блог, не використовується
- `Bookmarks.html` — соціальні закладки P2P
- `News.html` — P2P news monitor
- `Surftips.html` — соціальне голосування посиланнями
- `Trails.html` — CyTag Trails (P2P серфінг)
- `Wiki.html` + `WikiHelp.html` — вбудована wiki
- `User.html` — сторінка користувача P2P
- `ViewProfile.html` — профіль remote peer + vCard
- `Supporter.html` — список підтримувачів
- `Messages_p.html` + `MessageSend_p.html` — P2P повідомлення
- `TransNews_p.html` — трансляція новин перекладів

### Застарілі інтеграції
- `ContentIntegrationPHPBB3_p.html` + `Load_PHPBB3.html` — phpBB3 інтеграція
- `Load_MediawikiWiki.html` — MediaWiki пошук
- `sharedBlacklist_p.html` — спільний P2P blacklist

### Тест/debug сторінки
- `ssitest.html` + `ssitestservlet.html` — SSI тест (German comments)
- `test.html` — загальна test page
- `CookieTest_p.html` — тест cookies
- `CookieMonitorIncoming_p.html` + `CookieMonitorOutgoing_p.html` — proxy cookie monitor
- `Collage.html` — image collage, не інтегровано

### Проксі (функцію прибрано)
- `ProxyIndexingMonitor_p.html` — proxy indexing monitor
- `compare_yacy.html` — порівняння (застаріла маркетингова сторінка)

---

## ПЕРЕПИСАТИ (Застарілий XHTML → HTML5, великі/важливі шаблони — 15 файлів)

### Пріоритет HIGH (основний user flow)
- `index.html` (14KB) — головна сторінка, таблиці замість flexbox
- `yacysearch.html` (15KB) — сторінка результатів, потребує повного рефакторингу
- `yacysearchtrailer.html` (17KB) — результати пошуку — великий, складний
- `yacysearchitem.html` — картки результатів
- `yacysearchpagination.html` — пагінація

### Пріоритет MEDIUM (адмін панель)
- `CrawlStartExpert.html` (49KB) — ВЕЛИКИЙ, треба розбити
- `ConfigSearchPage_p.html` (26KB) — конфіг пошукової сторінки
- `Network.html` (22KB) — мережева інформація, старий layout
- `Crawler_p.html` (16KB) — crawler dashboard
- `IndexBrowser_p.html` (15KB) — браузер індексу
- `ConfigPortal_p.html` (17KB) — конфіг порталу
- `ConfigNetwork_p.html` (13KB) — конфіг мережі
- `Steering.html` (15KB) — steering dashboard

### Пріоритет LOW (рідко використовувані)
- `Blacklist_p.html`, `BlacklistCleaner_p.html`, `BlacklistImpExp_p.html`, `BlacklistTest_p.html`
- `DictionaryLoader_p.html`, `Vocabulary_p.html`

---

## ЗАЛИШИТИ без змін (вже HTML5 або нові файли)

- `yacychat.html` (100KB) — нещодавно оновлено з VFS
- `LLMSelection_p.html` (54KB) — новий AI функціонал
- `AILab.html`, `AIShield_p.html` — нові AI шаблони
- `VFS.html` (27KB) — нещодавно додано
- `RAGConfig_p.html` — новий
- `SkillsConfig_p.html` — новий
- `SearchAccessRate_p.html` — вже HTML5
- `Performance_p.html` та похідні — активний функціонал

---

## СТАТИСТИКА

| Категорія | Кількість |
|---|---|
| Видалити | ~22 файли |
| Переписати (HTML5 + сучасний CSS) | ~15 файлів |
| Залишити | ~97 файлів |
| З яких вже HTML5 | 21 файл |

**Наступний крок:** видалити 22 legacy файли (після перевірки що немає active Java servlets), потім mobile fix index.html + yacysearch.html
