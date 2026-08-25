package net.yacy.search.query;

import java.util.HashMap;
import java.util.Iterator;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import org.junit.Test;

public class QueryGoalTest {

    /**
     * Test of getIncludeString method, of class QueryGoal.
     */
    @Test
    public void testGetIncludeString() {
        HashMap<String, String[]> testdata = new HashMap<String, String[]>();
        // Prameter:  (Query, [result_term1, result_term2 ..])
        testdata.put("O'Reily's book", new String[]{"o'reily's", "book"});
        testdata.put("\"O'Reily's book\"", new String[]{"o'reily's book"}); // quoted term
        testdata.put("\"O'Reily's\" +book", new String[]{"o'reily's", "book"}); // +word
        testdata.put("Umphrey's + McGee", new String[]{"umphrey's", " mcgee"}); // !! attention extra space
        testdata.put("'The Book' library", new String[]{"the book","library"}); //single quoted term

        for (String testquery : testdata.keySet()) {
            QueryGoal qg = new QueryGoal(testquery); // get test query
            String[] singlestr = testdata.get(testquery); // get result strings

            Iterator<String> it = qg.getIncludeStrings();
            int i = 0;
            while (it.hasNext()) {
                String s = it.next();
                System.out.println(singlestr[i] + " = " + s);
                assertEquals(s, singlestr[i]);
                i++;
            }
        }
    }

    /**
     * Short queries (< LONG_QUERY_THRESHOLD includes) keep AND between terms
     * for precision; the resulting Solr query is wrapped in parens.
     */
    @Test
    public void testShortQueryUsesAnd() {
        QueryGoal qg = new QueryGoal("foo bar baz");
        assertFalse(qg.isLongQuery());
        String q = qg.collectionTextQuery().toString();
        assertTrue("expected AND in short query, got: " + q, q.contains(" AND "));
        assertTrue("expected wrapping parens in short query, got: " + q, q.startsWith("(") && q.endsWith(")"));
    }

    /**
     * Long queries (>= LONG_QUERY_THRESHOLD includes) drop AND so edismax
     * can apply min-should-match. No wrapping parens, plain space-separated
     * quoted terms.
     */
    @Test
    public void testLongQueryDropsAnd() {
        QueryGoal qg = new QueryGoal("foo bar baz qux quux");
        assertTrue(qg.isLongQuery());
        String q = qg.collectionTextQuery().toString();
        assertFalse("AND must be absent in long query, got: " + q, q.contains(" AND "));
        assertFalse("must not be paren-wrapped, got: " + q, q.startsWith("("));
        assertTrue("expected first term quoted, got: " + q, q.contains("\"foo\""));
        assertTrue("expected last term quoted, got: " + q, q.contains("\"quux\""));
    }

}
