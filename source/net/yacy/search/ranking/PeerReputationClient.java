// PeerReputationClient.java
// Async fire-and-forget reporter that tells the vector_service which remote
// peers contributed to a search. Used by yacysearch.java after each global
// search to populate the peer_reputation table.
//
// On any failure (service down, timeout) the call is silently dropped.

package net.yacy.search.ranking;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class PeerReputationClient {

    private static final HttpClient HTTP = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .build();

    private PeerReputationClient() {}

    /**
     * Fire-and-forget: POST peer hit data to the vector_service /track-peer-hit endpoint.
     * Does not block the calling thread.
     *
     * @param peerHash  the remote peer's hash (12-char base64)
     * @param peerName  the remote peer's display name
     * @param hits      number of results this peer contributed
     */
    public static void trackAsync(final String peerHash, final String peerName, final int hits) {
        final String baseUrl = System.getenv("VECTOR_CLASSIFY_URL");
        if (baseUrl == null || baseUrl.isEmpty()) return;
        final String trackUrl = baseUrl.replace("/classify-submission", "/track-peer-hit");

        // Sanitise strings for inline JSON.
        final String safeHash = peerHash == null ? "" : peerHash.replace("\"", "").replace("\\", "");
        final String safeName = peerName == null ? "" : peerName.replace("\"", "").replace("\\", "");
        final String body = "{\"peer_hash\":\"" + safeHash + "\",\"peer_name\":\"" + safeName + "\",\"hits\":" + hits + "}";

        Thread.ofVirtual()
              .name("peer-repute-" + safeHash.substring(0, Math.min(6, safeHash.length())))
              .start(() -> {
                  try {
                      HTTP.send(
                          HttpRequest.newBuilder()
                              .uri(URI.create(trackUrl))
                              .timeout(Duration.ofSeconds(3))
                              .header("Content-Type", "application/json")
                              .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
                              .build(),
                          HttpResponse.BodyHandlers.discarding()
                      );
                  } catch (final Exception ignored) {}
              });
    }
}
