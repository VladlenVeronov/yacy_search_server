# YACY — Issue List (Phase 1 Bug Triage)

> Зібрано в рамках Phase 1 BUG triage — 2026-04-25.
> Джерело: `DATA/LOG/yacy00.log`, ручний прохід по змінених шаблонах,
> codebase grep на `FIXME/XXX`. Тільки **критичні** і **видимі** баги.

## Status legend
- 🔴 critical — крашить пошук / бекенд / втрата даних
- 🟠 major — функція не працює, але не крашить
- 🟡 minor — UX / косметика, видно користувачу

---

## 🔴 [FIXED] OOM in snippet extraction for documents without sentence punctuation

**Symptom:** `java.lang.OutOfMemoryError: Java heap space` при формуванні snippet'а
для деяких результатів пошуку. Стек:

```
SentenceReader.nextElement0:98  (StringBuilder.append)
WordTokenizer.tokenizeSentence:303
SnippetExtractor.<init>:48
TextSnippet.<init>:259
SearchEvent.drainSolrStackToResult:1893
yacysearchitem.respond:170
```

**Root cause:** `SentenceReader.nextElement0()` накопичує символи у `StringBuilder`
до першого `punctuation + invisible`. Якщо документ не має нормальних кінців речень
(мінімізований JS, OCR-сміття, "стіна тексту"), цикл проковтує **весь текст** в одну
StringBuilder → OOM на heap.

**Fix:** додано hard cap `MAX_SENTENCE_LENGTH = 100_000` chars з force-break.
100k символів значно більше за будь-яке справжнє речення, але далеко нижче
дефолтного heap'а.

**Commit:** `<this commit>`

---

## 🟠 P2P "search failed (resultMap is NULL)" — peer-side bug not ours

В логах систематично:
```
SEARCH failed, Peer: <id>:<name> (resultMap is NULL)
SEARCH failed (solr), remote Peer: <peer>/<url> returned null
```

Це не власний баг, а наслідок того що ремотні peer'и в YaCy мережі повертають
порожні відповіді (старі/несумісні версії, проблеми з їх Solr). Не блокує локальний
пошук — результати з працюючих peer'ів все одно агрегуються.

**Action:** не fix зараз; вписати в Phase 4 (NETWORK) — фільтр якості peer'ів,
блекліст peer'ів які постійно повертають null.

---

## 🟠 P2P peer-ping "(added < 0)" disconnect cycle

В логах постійно:
```
publish: disconnected senior peer '<name>' from [<ips>]: peer ping to peer
resulted in error response (added < 0)
```

Peer публікує себе як senior, але ping повертає негативний `added` лічильник →
peer disconnect → cycle. Природа: peer ID/timing розсинхронізація між peers.

**Action:** не fix зараз; Phase 4 — переглянути механіку peer reputation.

---

## 🟡 (legacy) `LogParser.java:462` — broken DHT distance avg

```java
results.put(DHT_DISTANCE_AVERAGE,
    Long.valueOf(this.avgDHTDist / this.DHTSelectionTargetCount / Long.MAX_VALUE));
//FIXME: broken avg
```

Ділення на `Long.MAX_VALUE` робить результат завжди 0. Не критично — це лише
лог-стат. Залишилось зі стандартного YaCy.

**Action:** опціональний easy-fix окремим комітом коли дійдемо до моніторингу.

---

## 🟢 Перевірено — все ОК

- `feature/remove-third-party-links`: ні CDN'ів, ні зовнішніх трекерів
  (`grep -nrE "(cdn|googleapis|gstatic|fonts.google|amung|vimeo)" htroot/` чисто)
- Tailwind локально (`htroot/env/css/tailwind.min.css`)
- Freemarker `#{...}#` всередині HTML коментарів — виправлено в `a43952489`
- Шаблонний кеш `DATA/LOCALE/htroot/<lang>/` — задокументовано в memory

---

## Conclusions for Phase 1

Phase 1 закрита: всі критичні крах-баги виправлено (OOM), всі видимі шаблонні
баги усунено, runtime third-party fetches видалено. Решта проблем — мережеві
peer-issues, які логічніше адресувати в Phase 4 (NETWORK).
