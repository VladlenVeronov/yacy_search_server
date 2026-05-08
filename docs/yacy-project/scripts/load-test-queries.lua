-- wrk script: randomly pick a query from a fixed pool that mirrors real
-- traffic (sampled from query_logs on prod) so the load test exercises
-- realistic Solr/edismax paths.
--
-- Mix: short (1-3 terms) + long (>=5 terms) so both code paths get hit.

local queries = {
  -- short, real
  "newsgroup",
  "новини",
  "новини сьогодні",
  "vir",
  "osmand",
  "вір груп",
  "linux",
  "ubuntu server",
  "search engine",
  -- long, exercise mm=50%
  "how to install ubuntu linux server desktop",
  "how to set up wireguard vpn on home router",
  "best open source decentralized search engine alternative",
  "як налаштувати власний поштовий сервер на домашньому linux",
  "site reliability engineering best practices for small teams",
  "self hosted privacy focused federated social network",
  -- with modifier (also real)
  "newsgroup /language/uk",
  "newsgroup /language/uk /date",
}

-- wrk callbacks
math.randomseed(os.time())

request = function()
  local q = queries[math.random(#queries)]
  -- url-encode spaces and non-ASCII chars
  local enc = q:gsub("([^%w%-%.%_%~])", function(c)
    return string.format("%%%02X", string.byte(c))
  end)
  local path = "/yacysearch.json?query=" .. enc .. "&maximumRecords=10"
  return wrk.format("GET", path)
end

-- track non-2xx
errors_5xx = 0
errors_4xx = 0
errors_other = 0

response = function(status, headers, body)
  if status >= 500 then
    errors_5xx = errors_5xx + 1
  elseif status >= 400 then
    errors_4xx = errors_4xx + 1
  elseif status >= 300 then
    errors_other = errors_other + 1
  end
end

done = function(summary, latency, requests)
  io.write("\n=== custom summary ===\n")
  io.write(string.format("4xx errors: %d\n", errors_4xx))
  io.write(string.format("5xx errors: %d\n", errors_5xx))
  io.write(string.format("3xx/other:  %d\n", errors_other))
  io.write(string.format("p50: %.0f ms\n", latency:percentile(50)/1000))
  io.write(string.format("p95: %.0f ms\n", latency:percentile(95)/1000))
  io.write(string.format("p99: %.0f ms\n", latency:percentile(99)/1000))
  io.write(string.format("max: %.0f ms\n", latency.max/1000))
end
