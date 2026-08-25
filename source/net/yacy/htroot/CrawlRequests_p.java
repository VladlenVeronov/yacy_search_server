package net.yacy.htroot;

import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

import org.json.JSONException;
import org.json.JSONObject;

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
 * - POST action=validate                → bot pass over all pending rows. Three layers in order,
 *                                          each one only runs if the previous accepted:
 *                                            1. substring blacklist over url+host (fast).
 *                                            2. HEAD alive (skips dead/4xx/5xx URLs).
 *                                            3. POST to vector_service /classify-submission for an
 *                                               LLM zero-shot pass over (url, description). Blocks
 *                                               on porn/casino/spam/malware/phishing. Skipped/no-op
 *                                               when the vector_service or its LLM key are unset.
 *                                          Sets bot_decision/bot_reason; admin still decides
 *                                          approve/reject.
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
        // Two distinct keys so the template never confuses alternative vs multi:
        //   #(hasRows)# empty :: table-with-#{rows}# #(/hasRows)#
        //   #{rows}# … #{/rows}#  iterates `rows` times via prop.put("rows", idx)
        prop.put("hasRows", idx == 0 ? 0 : 1);
        prop.put("rows",    idx);
        prop.put("total",   total);
        prop.putHTML("filter", filter);
        prop.put("filter_empty",    filter.isEmpty()         ? 1 : 0);
        prop.put("filter_pending",  "pending".equals(filter)  ? 1 : 0);
        prop.put("filter_approved", "approved".equals(filter) ? 1 : 0);
        prop.put("filter_blocked",  "blocked".equals(filter)  ? 1 : 0);
        prop.put("filter_crawling", "crawling".equals(filter) ? 1 : 0);
        prop.put("filter_done",     "done".equals(filter)     ? 1 : 0);
        return prop;
    }

    /** Run blacklist → HEAD-alive → LLM zero-shot classifier over every pending row. */
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
                final String desc = row.get("description", "");
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

                // 3. LLM zero-shot via vector_service. Soft signal: "blocked" overrides
                //    only if the service confidently named a bad category. Network/LLM
                //    failures keep the row approved-from-blacklist.
                if ("approved".equals(decision)) {
                    final ClassifyVerdict v = classifyViaVectorService(url, host, desc);
                    if (v != null) {
                        if ("blocked".equals(v.decision)) {
                            decision = "blocked";
                            reason   = v.reason;
                        } else {
                            // Append LLM verdict so admin sees both layers.
                            reason = reason + " | " + v.reason;
                        }
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

    /** Verdict from vector_service /classify-submission. Null on transport/parse error. */
    private static final class ClassifyVerdict {
        final String decision; // "approved" | "blocked"
        final String reason;   // human-readable, prefixed with category
        ClassifyVerdict(final String d, final String r) { this.decision = d; this.reason = r; }
    }

    /**
     * POST {url,host,description} to vector_service classifier; return null on
     * any failure so the caller treats the row as already-approved by the
     * blacklist+HEAD layers. Disabled/missing service → null (no override).
     */
    private static ClassifyVerdict classifyViaVectorService(final String url,
                                                             final String host,
                                                             final String description) {
        final String endpoint = resolveEnv("VECTOR_CLASSIFY_URL", "");
        if (endpoint == null || endpoint.isBlank()) return null;
        final long timeoutMs = parseLongOr(resolveEnv("VECTOR_CLASSIFY_TIMEOUT_MS", "12000"), 12000L);

        final String body;
        try {
            final JSONObject req = new JSONObject();
            req.put("url", url);
            if (host != null && !host.isEmpty())                req.put("host", host);
            if (description != null && !description.isEmpty()) req.put("description", description);
            body = req.toString();
        } catch (final JSONException e) {
            return null;
        }

        try {
            final HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofMillis(Math.max(1000L, timeoutMs / 4)))
                    .build();
            final HttpRequest httpReq = HttpRequest.newBuilder()
                    .uri(URI.create(endpoint))
                    .timeout(Duration.ofMillis(timeoutMs))
                    .header("content-type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
                    .build();
            final HttpResponse<String> resp = client.send(httpReq, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (resp.statusCode() != 200) {
                ConcurrentLog.warn("CrawlRequests_p", "classify non-200: " + resp.statusCode());
                return null;
            }
            final JSONObject obj = new JSONObject(resp.body());
            final String decision = obj.optString("decision", "");
            final String category = obj.optString("category", "unsure");
            final String reasonText = obj.optString("reason", category);
            if (decision.isEmpty()) return null;
            return new ClassifyVerdict(decision, "LLM[" + category + "]: " + reasonText);
        } catch (final Exception e) {
            ConcurrentLog.warn("CrawlRequests_p", "classify failed: " + e.getClass().getSimpleName()
                    + ": " + e.getMessage());
            return null;
        }
    }

    private static String resolveEnv(final String key, final String defaultValue) {
        final String v = System.getenv(key);
        return (v == null || v.isBlank()) ? defaultValue : v.trim();
    }

    private static long parseLongOr(final String s, final long fallback) {
        try { return Long.parseLong(s); } catch (final Exception e) { return fallback; }
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
