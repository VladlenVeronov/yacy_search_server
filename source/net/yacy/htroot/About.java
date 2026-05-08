package net.yacy.htroot;

import net.yacy.cora.protocol.RequestHeader;
import net.yacy.data.UserDB;
import net.yacy.search.Switchboard;
import net.yacy.server.serverObjects;
import net.yacy.server.serverSwitch;

/**
 * Empty handler so the template engine processes About.html and
 * expands the #%env/templates/...%# header include with the same
 * shell every other public page uses.
 *
 * Also sets `publicLoggedIn` so the public header shows the
 * Cabinet button for authenticated users.
 */
public class About {

    public static serverObjects respond(final RequestHeader header,
                                         final serverObjects post,
                                         final serverSwitch env) {
        final serverObjects prop = new serverObjects();
        final Switchboard sb = (Switchboard) env;
        final boolean admin = sb.verifyAuthentication(header);
        UserDB.Entry user = (sb.userDB != null) ? sb.userDB.getUser(header) : null;
        prop.put("publicLoggedIn", (admin || user != null) ? 1 : 0);
        if (user != null) prop.putHTML("publicLoggedIn_userName", user.getUserName());
        else if (admin) prop.put("publicLoggedIn_userName", "admin");
        return prop;
    }
}
