# How to add your site to VIR GOO

If you run a website and want it indexed by VIR GOO (and shared, via the
P2P DHT, with the rest of the YaCy `freeworld` network), you don't need
to email anyone or wait for a moderator to "discover" you. There is a
self-service flow built into the public UI.

Estimated time end-to-end: **5–10 minutes**, plus crawl time.

---

## 1. Sign up as a webmaster

Open the public site (e.g. `https://search.newsgroup.site/`) and:

1. Click **Реєстрація / Register** in the top-right.
2. Fill in your username, email and password.
3. Tick **"Я вебмайстер"** (I am a webmaster).
4. Submit.

You are now logged in (a `login` cookie is set). Your account has the
`WEBMASTER_RIGHT` flag, which unlocks the crawl-request form.

If you already had a regular account, open `/CrawlRequest.html` and use
the one-click **"Стати вебмайстром"** button — it grants the right
without making you sign up again.

---

## 2. Submit your site for crawling

Open `/CrawlRequest.html` (or click "Submit a site" in the footer).

Fill in:

| field          | what to put                                           |
|----------------|-------------------------------------------------------|
| **URL**        | The canonical home page of your site, e.g. `https://example.com/` |
| **Note** (optional) | Anything you want the operator to see — language, content focus, your role, etc. |

Submit. The form is a normal native YaCy page — no JS framework, no
SaaS in the loop. It writes a row to the `crawl_requests` WorkTable
(YaCy's own embedded key-value store) and reports back the current
indexed-page count for your host so you can see progress later.

---

## 3. The bot validator runs automatically

Each pending submission is screened by an in-process Java validator on
the server side. The check is intentionally cheap and conservative:

* **Substring blacklist** — the URL is rejected if its host or path
  contains any obvious red-flag substring (`porn`, `xxx`, `casino`,
  `gambl`, `bet`, `pornhub`, …) — same families that are listed in
  `defaults/list.black`.
* **HEAD-alive** — the validator does a 2-second `HEAD` request and
  expects a 2xx/3xx response. If your site is down, requests password,
  or returns 5xx, the validator marks the submission `blocked` with a
  reason ("HEAD timeout", "404", …).

If the validator clears your URL, an admin can press the **Run** button
on `/CrawlRequests_p.html` and the YaCy crawler will start a depth-3
crawl pinned to your domain (no following outbound links to third
parties). Default crawl scope:

```
crawlingMustMatch = ^https?://([^/]+\.)?your-host($|/.*)
crawlingDepth     = 3
range             = domain
```

---

## 4. Wait for the crawl to land

A small site (few hundred pages) finishes within an hour. Larger sites
take overnight. While the crawl is running, the YaCy admin's
`/Crawler_p.html` shows the live queue.

Two things happen as pages land:

* They are written to **Solr** (`collection1`) — that's what the
  full-text BM25 search hits use.
* The hourly `cron-sync-pages.sh` picks them up and writes 768-dim
  embeddings to `pgvector`. Once embedded, your pages also benefit from
  the 60% semantic ranker — i.e. they show up for queries that don't
  contain your exact terms.

---

## 5. Check your stats

Once you have at least one indexed page, open **`/WebmasterStats.html`**.
You'll see a per-host table:

| host           | indexed | 4xx | 5xx | last_crawl              |
|----------------|---------|-----|-----|-------------------------|
| example.com    | 142     | 3   | 0   | 2026-05-08 02:14:09 UTC |

Webmasters see only their own hosts. Admins see every host. Stats are
read live from Solr — no caching, no daily roll-up to wait for.

---

## 6. What we won't do

* **Fast-track for money.** There is no paid tier. Submission order is
  manually re-prioritised by the admin, not by anyone's wallet.
* **Honor "noindex" for already-public content** beyond the standard
  `robots.txt` and `<meta name="robots">` tags. We follow both.
* **Index private / login-walled pages.** The crawler doesn't carry
  cookies and won't fill forms.
* **Boost your site for backlinks.** PageRank is `coeff_authority = 0`
  in our `RankingProfile`. Buying links does nothing here.

---

## 7. Troubleshooting

| symptom                                              | likely cause                                              |
|------------------------------------------------------|-----------------------------------------------------------|
| `/CrawlRequest.html` shows "Authentication required" | Login cookie expired — re-login at `/User.html`.          |
| Submission marked `blocked: HEAD timeout`            | Your site was down at validation time — fix and resubmit. |
| Submission marked `blocked: substring match`         | URL contains a blacklisted token — message us if false +. |
| `WebmasterStats.html` shows zero indexed pages       | Crawl hasn't started yet, or admin hasn't pressed Run.    |
| Pages indexed but not finding via search             | Wait for `cron-sync-pages.sh` (next :05) to embed them.   |

---

## 8. Where this lives in the source

For people who want to read or fork the implementation:

| file                                                | what                                            |
|-----------------------------------------------------|-------------------------------------------------|
| `htroot/Register.html` + `Register.java`            | self-signup flow + WEBMASTER_RIGHT toggle       |
| `htroot/User.html`                                  | login form (also Tailwind, public-styled)       |
| `htroot/CrawlRequest.html` + `CrawlRequest.java`    | submission form + auth chain + WorkTable insert |
| `htroot/CrawlRequests_p.html` + `CrawlRequests_p.java` | admin queue + bot validator + Run button     |
| `htroot/WebmasterStats.html` + `WebmasterStats.java`| per-host stats from Solr                        |

It's all GPL-2.0 and hot-reloaded on every push to
`feature/remove-third-party-links`. Forks welcome.
