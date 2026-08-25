// VectorRankClient.java
// Bridges YaCy's Java search pipeline to the external Python vector_service
// for hybrid (semantic + freshness + quality) re-ranking.
//
// Configuration is read in this priority order, so the same code works on
// Mac (localhost) and on the production server (internal service URL):
//   1. Environment variable (VECTOR_RANK_ENABLED / _URL / _TIMEOUT_MS)
//   2. yacy.init key (vector_rank.enabled / .url / .timeout_ms)
//   3. Hardcoded fallback (disabled, localhost:8001, 1500 ms)
//
// On any failure (service down, timeout, malformed response) the client
// returns an empty map. The caller treats "no override" as "use the
// existing YaCy ranking" so the search degrades gracefully.

package net.yacy.search.ranking;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Collections;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import net.yacy.cora.document.encoding.ASCII;
import net.yacy.cora.util.ConcurrentLog;
import net.yacy.kelondro.data.meta.URIMetadataNode;
import net.yacy.search.Switchboard;

public final class VectorRankClient {

    private static final String LOG = "VECTOR_RANK";

    // Hybrid scores arrive in [0..1]; YaCy's existing rankings sit in the
    // hundreds-of-millions range (Solr score * 1e6 in addNodes, then
    // multiplied again in addResult). Scaling by 1e9 puts the override in
    // the same order of magnitude so it actually decides the order.
    private static final long SCORE_SCALE = 1_000_000_000L;

    // ISO 8601 with milliseconds + Z, what the Python service expects.
    private static final DateTimeFormatter ISO =
            DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'").withZone(ZoneOffset.UTC);

    private VectorRankClient() {}

    public static boolean isEnabled() {
        return Boolean.parseBoolean(resolve("VECTOR_RANK_ENABLED", "vector_rank.enabled", "false"));
    }

    /**
     * POST {query, candidates: [{id, url, last_modified}]} to the rank
     * service and return id → scaled-long score for every candidate the
     * service ranked. Empty map on any failure.
     */
    public static Map<String, Long> rank(final String query, final List<URIMetadataNode> candidates) {
        if (!isEnabled() || candidates == null || candidates.isEmpty() || query == null || query.isEmpty()) {
            return Collections.emptyMap();
        }
        final String url = resolve("VECTOR_RANK_URL", "vector_rank.url", "http://127.0.0.1:8001/rank");
        final long timeoutMs = parseLongOr(resolve("VECTOR_RANK_TIMEOUT_MS", "vector_rank.timeout_ms", "1500"), 1500L);

        final String body;
        try {
            body = buildRequestBody(query, candidates);
        } catch (final Throwable t) {
            ConcurrentLog.warn(LOG, "failed to build request body: " + t.getMessage());
            return Collections.emptyMap();
        }

        final long started = System.currentTimeMillis();
        try {
            // Force HTTP/1.1 — Java's default HttpClient sends an HTTP/2
            // upgrade header that uvicorn rejects, with the side effect that
            // the request body is dropped before reaching FastAPI (Pydantic
            // sees null and 422s). HTTP/1.1 is fine for our local-network
            // call volume.
            final HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofMillis(Math.max(500L, timeoutMs / 3)))
                    .build();
            final HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .timeout(Duration.ofMillis(timeoutMs))
                    .header("content-type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
                    .build();
            final HttpResponse<String> resp = client.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (resp.statusCode() != 200) {
                ConcurrentLog.warn(LOG, "non-200 response: " + resp.statusCode() + " body=" + abbreviate(resp.body(), 200));
                return Collections.emptyMap();
            }
            final Map<String, Long> result = parseResponse(resp.body());
            ConcurrentLog.info(LOG, "ranked " + result.size() + "/" + candidates.size()
                    + " candidates in " + (System.currentTimeMillis() - started) + " ms");
            return result;
        } catch (final Throwable t) {
            ConcurrentLog.warn(LOG, "rank request failed after "
                    + (System.currentTimeMillis() - started) + " ms: " + t.getClass().getSimpleName()
                    + ": " + t.getMessage());
            return Collections.emptyMap();
        }
    }

    private static String buildRequestBody(final String query, final List<URIMetadataNode> candidates) throws JSONException {
        final JSONArray arr = new JSONArray();
        for (final URIMetadataNode node : candidates) {
            if (node == null || node.url() == null) continue;
            final JSONObject c = new JSONObject();
            c.put("id", ASCII.String(node.url().hash()));
            c.put("url", node.url().toNormalform(true));
            final Date mod = node.moddate();
            if (mod != null) {
                c.put("last_modified", ISO.format(Instant.ofEpochMilli(mod.getTime())));
            }
            arr.put(c);
        }
        final JSONObject root = new JSONObject();
        root.put("query", query);
        root.put("candidates", arr);
        return root.toString();
    }

    private static Map<String, Long> parseResponse(final String body) throws JSONException {
        final Map<String, Long> out = new HashMap<>();
        if (body == null || body.isEmpty()) return out;
        final JSONArray arr = new JSONArray(body);
        for (int i = 0; i < arr.length(); i++) {
            final JSONObject hit = arr.getJSONObject(i);
            final String id = hit.optString("id", null);
            if (id == null) continue;
            final double score = hit.optDouble("score", 0.0);
            // clamp so a malformed response can't push us into negative-long territory
            final double clamped = Math.max(0.0, Math.min(1.0, score));
            out.put(id, (long) (clamped * SCORE_SCALE));
        }
        return out;
    }

    /** env > yacy.init > default. Empty/blank values fall through. */
    private static String resolve(final String envKey, final String configKey, final String defaultValue) {
        final String env = System.getenv(envKey);
        if (env != null && !env.isBlank()) return env.trim();
        try {
            final Switchboard sb = Switchboard.getSwitchboard();
            if (sb != null) {
                final String v = sb.getConfig(configKey, "");
                if (v != null && !v.isBlank()) return v.trim();
            }
        } catch (final Throwable t) {
            // Switchboard not initialized (e.g. in unit tests) — fall through.
        }
        return defaultValue;
    }

    private static long parseLongOr(final String s, final long fallback) {
        try { return Long.parseLong(s); } catch (final Throwable t) { return fallback; }
    }

    private static String abbreviate(final String s, final int max) {
        if (s == null) return "";
        return s.length() <= max ? s : s.substring(0, max) + "…";
    }
}
