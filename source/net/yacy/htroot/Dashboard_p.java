package net.yacy.htroot;

import net.yacy.cora.protocol.RequestHeader;
import net.yacy.server.serverObjects;
import net.yacy.server.serverSwitch;

/**
 * Empty handler: exists solely so YaCyDefaultServlet finds a `respond`
 * method and runs the FreeMarker-style template engine on Dashboard_p.html
 * (which uses #%env/templates/...%# includes for the admin shell).
 *
 * All real logic on the Dashboard is client-side JS hitting
 * /api/vector/* and /solr/select.
 */
public class Dashboard_p {

    public static serverObjects respond(final RequestHeader header,
                                         final serverObjects post,
                                         final serverSwitch env) {
        return new serverObjects();
    }
}
