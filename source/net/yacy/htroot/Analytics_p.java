package net.yacy.htroot;

import net.yacy.cora.protocol.RequestHeader;
import net.yacy.server.serverObjects;
import net.yacy.server.serverSwitch;

/**
 * Empty handler so the template engine processes Analytics_p.html
 * (which uses #%env/templates/...%# for the admin shell). All data
 * comes from /api/vector/* via JS.
 */
public class Analytics_p {

    public static serverObjects respond(final RequestHeader header,
                                         final serverObjects post,
                                         final serverSwitch env) {
        return new serverObjects();
    }
}
