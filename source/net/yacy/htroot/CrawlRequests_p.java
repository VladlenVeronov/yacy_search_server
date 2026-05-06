package net.yacy.htroot;

import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

import net.yacy.cora.protocol.RequestHeader;
import net.yacy.cora.util.ConcurrentLog;
import net.yacy.cora.util.SpaceExceededException;
import net.yacy.kelondro.blob.Tables;
import net.yacy.search.Switchboard;
import net.yacy.server.serverObjects;
import net.yacy.server.serverSwitch;

/**
 * Admin queue for webmaster crawl requests.
 * - GET: paginated list of crawl_requests rows; filter via ?status=pending|approved|blocked|done
 * - POST action=approve|reject id=PK    → flips status, drops bot_decision back to admin's word
 * - POST action=run id=PK               → 302 to Crawler_p.html with crawlingURL prefilled and a
 *                                          must-match regex pinned to the requested host (no leak
 *                                          to external domains). Admin clicks "Start" once.
 * - POST action=validate                → bot pass over all pending rows (blacklist substring +
 *                                          HEAD alive). Sets bot_decision/bot_reason; admin still
 *                                          decides approve/reject. LLM porn/casino check is a
 *                                          phase-5 add-on (gated on llm_api_key in vector_service).
 *
 * Admin-protected by filename suffix `_p.html` — YaCy default servlet enforces digest auth.
 */
public class CrawlRequests_p {

    // Substring "obvious bad" hints. The crawl-time YaCy blacklist is the
    // real authority; this is just a fast pre-screen at submission time.
    private static final String[] BAD_HINTS = {
        "porn", "xxx", "xnxx", "xvideos", "xhamster", "brazzers", "onlyfans",
        "chaturbate", "redtube", "youporn", "pornhub", "spankbang",
        "casino", "gambl", "bet365", "1xbet", "pokerstars",
        "phishing", "malware",
    };

    private static final Pattern HOST_RE = Pattern.compile("[a-zA-Z0-9.-]+");

    public static serverObjects respond(final RequestHeader header,
                                         final serverObjects post,
                                         final serverSwitch env) {
        final serverObjects prop = new serverObjects();
        final Switchboard sb = (Switchboard) env;

        // ---- actions ----
        if (post != null) {
            final String action = post.get("action", "");
            final String pkStr  = post.get("pk", "");

            if ("validate".equals(action)) {
                final int n = validatePending(sb);
                prop.put("flash", 1);
                prop.putHTML("flash_message", "Бот перевірив " + n + " заявок.");
            } else if (("approve".equals(action) || "reject".equals(action)) && !pkStr.isEmpty()) {
                final String newStatus = "approve".equals(action) ? "approved" : "blocked";
                try {
                    final Tables.Row row = sb.tables.select(CrawlRequest.TABLE, pkStr.getBytes());
                    if (row != null) {
                        row.put("status", newStatus.getBytes());
                        sb.tables.update(CrawlRequest.TABLE, row);
                        prop.put("flash", 1);
                        prop.putHTML("flash_message", "Заявку #" + pkStr + " → " + newStatus);
                    }
                } catch (final IOException | SpaceExceededException e) {
                    ConcurrentLog.warn("CrawlRequests_p", "update: " + e.getMessage());
                }
            } else if ("run".equals(action) && !pkStr.isEmpty()) {
                try {
                    final Tables.Row row = sb.tables.select(CrawlRequest.TABLE, pkStr.getBytes());
                    if (row != null) {
                        final String url  = row.get("url", "");
                        final String host = row.get("host", "");
                        if (HOST_RE.matcher(host).matches()) {
                            // mark as 'crawling' for the queue view
                            row.put("status", "crawling".getBytes());
                            sb.tables.update(CrawlRequest.TABLE, row);

                            // Pin crawl to the requested host: only URLs whose host equals
                            // <host> or ends with .<host> are accepted; everything else rejected.
                            final String mustMatch = "^https?://([^/]+\\.)?"
                                + Pattern.quote(host).replace("\\Q", "").replace("\\E", "")
                                + "($|/.*)";
                            final StringBuilder qs = new StringBuilder("/CrawlStartExpert.html");
                            qs.append("?crawlingURL=").append(urlencode(url));
                            qs.append("&crawlingMustMatch=").append(urlencode(mustMatch));
                            qs.append("&crawlingDepth=3");
                            qs.append("&range=domain");
                            prop.put(serverObjects.ACTION_LOCATION, qs.toString());
                            return prop;
                        }
                    }
                } catch (final IOException | SpaceExceededException e) {
                    ConcurrentLog.warn("CrawlRequests_p", "run: " + e.getMessage());
                }
            } else if ("delete".equals(action) && !pkStr.isEmpty()) {
                try {
                    sb.tables.delete(CrawlRequest.TABLE, pkStr.getBytes());
                    prop.put("flash", 1);
                    prop.putHTML("flash_message", "Видалено #" + pkStr);
                } catch (final IOException e) {
                    ConcurrentLog.warn("CrawlRequests_p", "delete: " + e.getMessage());
                }
            }
        }

        // ---- list ----
        final String filter = (post == null) ? "" : post.get("status", "");
        int total = 0, idx = 0;
        try {
            final Iterator<Tables.Row> it = sb.tables.iterator(CrawlRequest.TABLE);
            // Collect first to count + sort newest-first by submitted_at
            final List<Tables.Row> rows = new ArrayList<>();
            while (it.hasNext()) {
                final Tables.Row row = it.next();
                if (row == null) continue;
                if (!filter.isEmpty() && !filter.equals(row.get("status", ""))) continue;
                rows.add(row);
            }
            total = rows.size();
            rows.sort((a, b) -> {
                long ax = parseLong(a.get("submitted_at", "0"));
                long bx = parseLong(b.get("submitted_at", "0"));
                return Long.compare(bx, ax);
            });
            for (final Tables.Row row : rows) {
                prop.putHTML("rows_" + idx + "_pk",                new String(row.getPK()));
                prop.putHTML("rows_" + idx + "_url",               row.get("url", ""));
                prop.putHTML("rows_" + idx + "_host",              row.get("host", ""));
                prop.putHTML("rows_" + idx + "_status",            row.get("status", ""));
                prop.putHTML("rows_" + idx + "_bot_decision",      row.get("bot_decision", ""));
                prop.putHTML("rows_" + idx + "_bot_reason",        row.get("bot_reason", ""));
                prop.putHTML("rows_" + idx + "_requested_by_user", row.get("requested_by_user", ""));
                prop.putHTML("rows_" + idx + "_contact_email",     row.get("contact_email", ""));
                prop.putHTML("rows_" + idx + "_description",       row.get("description", ""));
                prop.putHTML("rows_" + idx + "_submitted_at",      row.get("submitted_at", ""));
                idx++;
            }
        } catch (final IOException e) {
            ConcurrentLog.warn("CrawlRequests_p", "iterate: " + e.getMessage());
        }
        prop.put("rows",  idx);
        prop.put("total", total);
        prop.putHTML("filter", filter);
        prop.put("filter_empty",    filter.isEmpty()         ? 1 : 0);
        prop.put("filter_pending",  "pending".equals(filter)  ? 1 : 0);
        prop.put("filter_approved", "approved".equals(filter) ? 1 : 0);
        prop.put("filter_blocked",  "blocked".equals(filter)  ? 1 : 0);
        prop.put("filter_crawling", "crawling".equals(filter) ? 1 : 0);
        prop.put("filter_done",     "done".equals(filter)     ? 1 : 0);
        return prop;
    }

    /** Run the substring blacklist + HEAD-alive sweep over every pending row. */
    private static int validatePending(final Switchboard sb) {
        int n = 0;
        try {
            final Iterator<Tables.Row> it = sb.tables.iterator(CrawlRequest.TABLE);
            while (it.hasNext()) {
                final Tables.Row row = it.next();
                if (row == null) continue;
                if (!"pending".equals(row.get("status", ""))) continue;
                final String url  = row.get("url", "");
                final String host = row.get("host", "").toLowerCase(Locale.ROOT);
                String decision = "approved", reason = "OK: blacklist clean + URL alive";

                // 1. substring blacklist
                final String lurl = url.toLowerCase(Locale.ROOT);
                for (final String hint : BAD_HINTS) {
                    if (lurl.contains(hint) || host.contains(hint)) {
                        decision = "blocked";
                        reason   = "matches blacklist hint: " + hint;
                        break;
                    }
                }

                // 2. HEAD alive (only if not already blocked)
                if ("approved".equals(decision)) {
                    try {
                        final URL u = new URI(url).toURL();
                        final HttpURLConnection c = (HttpURLConnection) u.openConnection();
                        c.setRequestMethod("HEAD");
                        c.setConnectTimeout(8000);
                        c.setReadTimeout(8000);
                        c.setInstanceFollowRedirects(true);
                        final int code = c.getResponseCode();
                        if (code >= 400) {
                            decision = "blocked";
                            reason   = "HEAD " + url + " returned " + code;
                        }
                    } catch (final Exception e) {
                        decision = "blocked";
                        reason   = "URL not reachable: " + e.getClass().getSimpleName();
                    }
                }

                row.put("bot_decision", decision.getBytes());
                row.put("bot_reason",   reason.getBytes());
                sb.tables.update(CrawlRequest.TABLE, row);
                n++;
            }
        } catch (final IOException e) {
            ConcurrentLog.warn("CrawlRequests_p", "validate: " + e.getMessage());
        }
        return n;
    }

    private static long parseLong(final String s) {
        try { return Long.parseLong(s); } catch (final Exception e) { return 0L; }
    }

    private static String urlencode(final String s) {
        try {
            return java.net.URLEncoder.encode(s, "UTF-8");
        } catch (final Exception e) {
            return s;
        }
    }

}
