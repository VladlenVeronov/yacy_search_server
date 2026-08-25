package net.yacy.htroot;

import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

import org.apache.solr.common.SolrDocument;
import org.apache.solr.common.SolrDocumentList;

import net.yacy.cora.protocol.RequestHeader;
import net.yacy.cora.util.ConcurrentLog;
import net.yacy.data.UserDB;
import net.yacy.data.UserDB.AccessRight;
import net.yacy.kelondro.blob.Tables;
import net.yacy.search.Switchboard;
import net.yacy.search.schema.CollectionSchema;
import net.yacy.server.serverObjects;
import net.yacy.server.serverSwitch;

/**
 * Per-webmaster index statistics for the host(s) the user has submitted.
 * Reads CrawlRequest WorkTable for "their" hosts, then queries Solr for
 * count + 4xx/5xx errors + most recent crawl. Admin sees everything.
 */
public class WebmasterStats {

    public static serverObjects respond(final RequestHeader header,
                                         final serverObjects post,
                                         final serverSwitch env) {
        final serverObjects prop = new serverObjects();
        final Switchboard sb = (Switchboard) env;

        UserDB.Entry user = (sb.userDB == null) ? null : sb.userDB.proxyAuth(header);
        if (user == null && sb.userDB != null) user = sb.userDB.cookieAuth(header.getCookies());
        if (user == null && sb.userDB != null) {
            final String ip = header.getRemoteAddr();
            if (ip != null) user = sb.userDB.ipAuth(ip);
        }
        final boolean isAdmin = sb.verifyAuthentication(header);
        final boolean loggedIn = user != null || isAdmin;
        prop.put("loggedIn", loggedIn ? 1 : 0);
        if (!loggedIn) return prop;

        final String username = isAdmin ? "admin" : user.getUserName();
        prop.putHTML("loggedIn_username", username);

        final List<Map<String, String>> hosts = new ArrayList<>();
        try {
            final Iterator<Tables.Row> it = sb.tables.iterator(CrawlRequest.TABLE);
            while (it.hasNext()) {
                final Tables.Row row = it.next();
                if (row == null) continue;
                final String requester = row.get("requested_by_user", "");
                if (!isAdmin && !username.equals(requester)) continue;
                final String host = row.get("host", "");
                final String status = row.get("status", "");
                final String botDecision = row.get("bot_decision", "");
                final String url = row.get("url", "");
                if (host.isEmpty()) continue;

                long total = 0, err4 = 0, err5 = 0;
                String lastCrawl = "—";
                try {
                    final var conn = sb.index.fulltext().getDefaultConnector();
                    final String hostQ = CollectionSchema.host_s.getSolrFieldName() + ":\"" + host + "\"";
                    total = conn.getCountByQuery(hostQ);
                    err4 = conn.getCountByQuery(hostQ + " AND " +
                            CollectionSchema.httpstatus_i.getSolrFieldName() + ":[400 TO 499]");
                    err5 = conn.getCountByQuery(hostQ + " AND " +
                            CollectionSchema.httpstatus_i.getSolrFieldName() + ":[500 TO 599]");
                    final SolrDocumentList docs = conn.getDocumentListByQuery(
                            hostQ,
                            CollectionSchema.load_date_dt.getSolrFieldName() + " desc",
                            0, 1,
                            CollectionSchema.load_date_dt.getSolrFieldName());
                    if (docs != null && !docs.isEmpty()) {
                        final SolrDocument d = docs.get(0);
                        final Object dt = d.getFieldValue(CollectionSchema.load_date_dt.getSolrFieldName());
                        if (dt != null) lastCrawl = dt.toString();
                    }
                } catch (final IOException e) {
                    ConcurrentLog.warn("WebmasterStats", "solr query: " + e.getMessage());
                }

                final Map<String, String> h = new HashMap<>();
                h.put("host", host);
                h.put("url", url);
                h.put("status", status);
                h.put("bot_decision", botDecision);
                h.put("count_total", String.valueOf(total));
                h.put("count_4xx", String.valueOf(err4));
                h.put("count_5xx", String.valueOf(err5));
                h.put("last_crawl", lastCrawl);
                hosts.add(h);
            }
        } catch (final IOException e) {
            ConcurrentLog.warn("WebmasterStats", "iterate: " + e.getMessage());
        }

        prop.put("loggedIn_hostsCount", hosts.size());
        for (int i = 0; i < hosts.size(); i++) {
            final Map<String, String> h = hosts.get(i);
            prop.putHTML("loggedIn_hosts_" + i + "_host",         h.get("host"));
            prop.putHTML("loggedIn_hosts_" + i + "_url",          h.get("url"));
            prop.putHTML("loggedIn_hosts_" + i + "_status",       h.get("status"));
            prop.putHTML("loggedIn_hosts_" + i + "_bot_decision", h.get("bot_decision"));
            prop.put     ("loggedIn_hosts_" + i + "_count_total", h.get("count_total"));
            prop.put     ("loggedIn_hosts_" + i + "_count_4xx",   h.get("count_4xx"));
            prop.put     ("loggedIn_hosts_" + i + "_count_5xx",   h.get("count_5xx"));
            prop.putHTML("loggedIn_hosts_" + i + "_last_crawl",   h.get("last_crawl"));
        }
        prop.put("loggedIn_hosts", hosts.size());

        return prop;
    }
}
