package net.yacy.htroot;

import java.io.IOException;
import java.net.URI;
import java.util.HashMap;
import java.util.Map;

import net.yacy.cora.protocol.RequestHeader;
import net.yacy.cora.util.ConcurrentLog;
import net.yacy.cora.util.SpaceExceededException;
import net.yacy.data.UserDB;
import net.yacy.data.UserDB.AccessRight;
import net.yacy.search.Switchboard;
import net.yacy.search.schema.CollectionSchema;
import net.yacy.server.serverObjects;
import net.yacy.server.serverSwitch;

/**
 * Webmaster crawl-request submission. Authenticated YaCy users with
 * WEBMASTER_RIGHT (or ADMIN_RIGHT) can submit a domain for indexing;
 * the entry lands in the WorkTable {@link #TABLE} with status=pending,
 * where the bot validator (Phase 4) and admin queue pick it up.
 *
 * Crawls are intentionally NOT auto-launched: every request needs the
 * bot's blacklist/category check plus an admin nod, since the whole
 * point of moving away from autonomous DHT-driven crawling was to keep
 * porn/casino/spam domains out of the index.
 */
public class CrawlRequest {

    public static final String TABLE = "crawl_requests";

    public static serverObjects respond(final RequestHeader header,
                                         final serverObjects post,
                                         final serverSwitch env) {
        final serverObjects prop = new serverObjects();
        final Switchboard sb = (Switchboard) env;

        // Match the auth chain User.java uses: HTTP digest → cookie → IP.
        UserDB.Entry user = (sb.userDB == null) ? null : sb.userDB.proxyAuth(header);
        if (user == null && sb.userDB != null) user = sb.userDB.cookieAuth(header.getCookies());
        if (user == null && sb.userDB != null) {
            final String ip = header.getRemoteAddr();
            if (ip != null) user = sb.userDB.ipAuth(ip);
        }

        final boolean loggedIn = user != null;
        final boolean isAdmin  = sb.verifyAuthentication(header);

        // One-click webmaster activation: any logged-in user can flip
        // their own WEBMASTER_RIGHT here. Abuse control lives downstream
        // in the bot validator, not in a manual approval gate.
        if (post != null && "1".equals(post.get("become_webmaster", "")) && loggedIn) {
            try {
                user.setProperty(AccessRight.WEBMASTER_RIGHT.toString(), "true");
            } catch (final Exception e) {
                ConcurrentLog.warn("CrawlRequest", "grant webmaster failed: " + e.getMessage());
            }
        }

        final boolean canSubmit = isAdmin
            || (loggedIn && (user.hasRight(AccessRight.WEBMASTER_RIGHT)
                            || user.hasRight(AccessRight.ADMIN_RIGHT)));

        prop.put("loggedIn", (loggedIn || isAdmin) ? 1 : 0);
        prop.put("loggedIn_canSubmit", canSubmit ? 1 : 0);

        final String username = isAdmin ? "admin" : (loggedIn ? user.getUserName() : "");
        prop.putHTML("loggedIn_canSubmit_username", username);

        // Public header auth slot (Cabinet vs Login+Register)
        prop.put("publicLoggedIn", (loggedIn || isAdmin) ? 1 : 0);
        if (!username.isEmpty()) prop.putHTML("publicLoggedIn_userName", username);

        if (post != null && post.containsKey("url") && canSubmit) {
            final String url = post.get("url", "").trim();
            final String email = post.get("email", "").trim();
            final String desc = post.get("description", "").trim();

            String host = null;
            try {
                final URI u = URI.create(url);
                host = u.getHost();
            } catch (final Exception ignored) {
                // host stays null → handled below
            }

            if (host == null || host.isEmpty()
                    || (!url.startsWith("http://") && !url.startsWith("https://"))) {
                prop.put("loggedIn_canSubmit_state", 1);
                prop.putHTML("loggedIn_canSubmit_state_message",
                             "URL некоректний (потрібен http:// або https://, з валідним хостом)");
                return prop;
            }

            final Map<String, byte[]> row = new HashMap<>();
            row.put("url",                url.getBytes());
            row.put("host",               host.getBytes());
            row.put("contact_email",      email.getBytes());
            row.put("description",        desc.getBytes());
            row.put("status",             "pending".getBytes());
            row.put("requested_by_user",  username.getBytes());
            row.put("submitted_at",       String.valueOf(System.currentTimeMillis()).getBytes());
            row.put("bot_decision",       "".getBytes());
            row.put("bot_reason",         "".getBytes());

            try {
                final byte[] pk = sb.tables.insert(TABLE, row);
                long indexed = 0L;
                try {
                    indexed = sb.index.fulltext().getDefaultConnector().getCountByQuery(
                            CollectionSchema.host_s.getSolrFieldName() + ":\"" + host + "\"");
                } catch (final IOException ignored) { /* keep 0 */ }
                prop.put("loggedIn_canSubmit_state", 2);
                prop.putHTML("loggedIn_canSubmit_state_message", new String(pk));
                prop.putHTML("loggedIn_canSubmit_state_host", host);
                prop.put("loggedIn_canSubmit_state_indexed", indexed);
            } catch (final IOException | SpaceExceededException e) {
                ConcurrentLog.warn("CrawlRequest", "insert failed: " + e.getMessage());
                prop.put("loggedIn_canSubmit_state", 1);
                prop.putHTML("loggedIn_canSubmit_state_message",
                             "помилка запису: " + e.getMessage());
            }
        }

        return prop;
    }
}
