package net.yacy.htroot;

import net.yacy.cora.protocol.RequestHeader;
import net.yacy.server.serverObjects;
import net.yacy.server.serverSwitch;

/**
 * Empty handler so the template engine processes Services_p.html.
 * The page calls /api/vector/services and /api/vector/admin/services
 * directly from JS using a token kept in localStorage.
 */
public class Services_p {

    public static serverObjects respond(final RequestHeader header,
                                         final serverObjects post,
                                         final serverSwitch env) {
        return new serverObjects();
    }
}
