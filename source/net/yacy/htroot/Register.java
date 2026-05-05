package net.yacy.htroot;

import java.util.HashMap;
import java.util.Map;
import java.util.regex.Pattern;

import net.yacy.cora.protocol.RequestHeader;
import net.yacy.cora.protocol.ResponseHeader;
import net.yacy.cora.util.ConcurrentLog;
import net.yacy.data.UserDB;
import net.yacy.data.UserDB.AccessRight;
import net.yacy.search.Switchboard;
import net.yacy.search.SwitchboardConstants;
import net.yacy.server.serverObjects;
import net.yacy.server.serverSwitch;
import net.yacy.server.servletProperties;

/**
 * Public self-signup. POST creates a UserDB entry, optionally toggles
 * WEBMASTER_RIGHT when the form's "iam_webmaster" checkbox is on, and
 * auto-logs the new user in by setting the same login cookie that
 * {@code User.java} uses.
 *
 * Webmaster role is granted at signup; the bot validator (Phase 4)
 * is the abuse-control layer. This is the trade-off the user explicitly
 * asked for: easy onboarding, hard filtering of submitted domains.
 */
public class Register {

    private static final Pattern USERNAME_RE = Pattern.compile("[a-zA-Z0-9._-]{3,32}");

    public static servletProperties respond(final RequestHeader header,
                                             final serverObjects post,
                                             final serverSwitch env) {
        final servletProperties prop = new servletProperties();
        final Switchboard sb = (Switchboard) env;

        // already logged in? bounce
        final UserDB.Entry already = (sb.userDB == null) ? null : sb.userDB.proxyAuth(header);
        if (already != null) {
            prop.put(serverObjects.ACTION_LOCATION, "/index.html");
            return prop;
        }

        prop.put("submitted", 0);
        prop.put("submitted_ok", 0);
        prop.put("submitted_message", "");
        prop.putHTML("username", "");
        prop.putHTML("email", "");

        // initial render — pre-check the webmaster box if invited via ?webmaster=1
        if (post == null || !post.containsKey("username")) {
            final boolean prefill = post != null && "1".equals(post.get("webmaster", ""));
            prop.put("iam_webmaster_checked", prefill ? "checked" : "");
            return prop;
        }
        prop.put("iam_webmaster_checked", "");

        final String username = post.get("username", "").trim();
        final String pw1      = post.get("password", "");
        final String pw2      = post.get("password2", "");
        final String email    = post.get("email", "").trim();
        final boolean wantsWebmaster = "on".equals(post.get("iam_webmaster", ""));
        final String returnTo = wantsWebmaster ? "/CrawlRequest.html" : "/index.html";

        // ---- validation ----
        String error = null;
        if (!USERNAME_RE.matcher(username).matches()) {
            error = "Логін: 3-32 символи, латиниця/цифри/._-";
        } else if (username.equalsIgnoreCase(
                sb.getConfig(SwitchboardConstants.ADMIN_ACCOUNT_USER_NAME, "admin"))) {
            error = "Цей логін зарезервовано адміністратором";
        } else if (sb.userDB.getEntry(username) != null) {
            error = "Логін уже зайнято";
        } else if (pw1.length() < 6) {
            error = "Пароль має містити не менше 6 символів";
        } else if (!pw1.equals(pw2)) {
            error = "Паролі не збігаються";
        }

        if (error != null) {
            prop.put("submitted", 1);
            prop.put("submitted_ok", 0);
            prop.putHTML("submitted_message", error);
            prop.putHTML("username", username);
            prop.putHTML("email",    email);
            prop.put("iam_webmaster_checked", wantsWebmaster ? "checked" : "");
            return prop;
        }

        // ---- build entry ----
        final Map<String, String> mem = new HashMap<>();
        mem.put(UserDB.Entry.MD5ENCODED_USERPWD_STRING, sb.encodeDigestAuth(username, pw1));
        mem.put(UserDB.Entry.USER_ADDRESS, email);
        mem.put(UserDB.Entry.TIME_LIMIT, "0");
        mem.put(UserDB.Entry.TIME_USED,  "0");
        for (final AccessRight right : AccessRight.values()) {
            final boolean grant = (right == AccessRight.WEBMASTER_RIGHT && wantsWebmaster)
                                 || right == AccessRight.EXTENDED_SEARCH_RIGHT
                                 || right == AccessRight.BOOKMARK_RIGHT;
            mem.put(right.toString(), grant ? "true" : "false");
        }

        UserDB.Entry entry;
        try {
            entry = sb.userDB.createEntry(username, mem);
            sb.userDB.addEntry(entry);
        } catch (final IllegalArgumentException e) {
            ConcurrentLog.warn("Register", "createEntry failed: " + e.getMessage());
            prop.put("submitted", 1);
            prop.put("submitted_ok", 0);
            prop.putHTML("submitted_message", "Помилка створення: " + e.getMessage());
            prop.putHTML("username", username);
            prop.putHTML("email",    email);
            return prop;
        }

        // ---- auto-login: drop the same cookie User.java uses ----
        final String cookie = sb.userDB.getCookie(entry);
        final ResponseHeader outgoing = new ResponseHeader(200);
        outgoing.setCookie("login", cookie);
        prop.setOutgoingHeader(outgoing);

        prop.put(serverObjects.ACTION_LOCATION, returnTo);
        return prop;
    }
}
