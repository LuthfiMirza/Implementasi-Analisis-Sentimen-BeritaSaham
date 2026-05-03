# Sentimena QA Checklist

## Pre-Deploy

- `.env` is complete: `APP_KEY`, MySQL credentials, `SESSION_DRIVER=database`, `QUEUE_CONNECTION=database`, `CACHE_STORE=database|redis|file`, `SENTIMENT_ENGINE`, `NEWS_PROVIDER`, Python endpoints, market data settings.
- `php artisan migrate --force` has run, including `sessions`, `jobs`, `cache`, `stocks`, `stock_prices`, `news_articles`, and `trades`.
- Queue worker is running for database queue jobs when `QUEUE_CONNECTION=database`.
- Scheduler is configured for news fetch, OJK fetch/backfill as needed, sentiment reanalysis, stock snapshot updates, and paper-trading snapshot.
- Python FastAPI service is reachable for `/predict` and `/rank-stocks`, or Laravel fallback behavior is explicitly accepted.
- Storage/output directories are writable: `storage/`, `bootstrap/cache/`, and `output/paper_trading/`.
- Vite assets are built for production: `npm run build`.

## Functional

- Auth: guest redirects to login for dashboard, news, watchlist, analytics, backtest, trade journal, and admin routes.
- Auth: valid login succeeds; invalid login fails with validation error.
- Roles: admin reaches admin CRUD; regular user is blocked from `/admin/*`.
- News: provider fetchers use `Http::fake()` in tests; production keys/timeouts are set; duplicate URLs/titles are rejected.
- News: ticker relevance, exclusion keyword, language, and final quality thresholds reject bad articles.
- OJK: macro articles persist with `stock_id=null` and `source_provider=ojk_rss`.
- Sentiment: rule-based handles clear positive/neutral/negative Indonesian finance text.
- Sentiment: Python outage does not crash ingestion; fallback behavior is logged and visible via method/status fields.
- Analytics: no-news and no-price cases return neutral/empty values without division-by-zero.
- DSS: status remains one of `Bullish Support`, `Wait and See`, `Warning`; confidence remains `Rendah`, `Sedang`, or `Tinggi`.
- Ranking: `/rank-stocks` unavailability returns unavailable status, not fake ranking rows.
- Paper trading: daily snapshots are created, readable, and evaluatable into CSV.
- Trade journal: create, close, delete, and listing are scoped to the current user.
- Backtest: `include_macro_news` and `macro_regulatory_signal` toggles visibly affect article set/confidence.
- API: `/api/stocks/{CODE}/quote` returns full JSON structure and falls back to snapshot when live provider fails.
- UI: dashboard/news/watchlist/analytics/backtest/trades/admin pages render without Blade/Chart.js data errors.

## Edge Cases

- Empty database: dashboard and route smoke tests should either seed bootstrap data or show controlled empty states.
- Python service down: sentiment and prediction paths should not throw; ranking should show unavailable.
- All news providers failing: commands should exit cleanly, report zero saved, and log provider failures.
- No price data: quote API should return 404 or clear unavailable JSON; analytics/backtest should show controlled empty/error states.
- Ambiguous tickers such as `GOTO` and common words such as `BUMI` must reject non-financial articles.
- Foreign-language articles should be excluded unless explicitly supported.
- Duplicate news from different providers should not inflate sentiment volume.

## Performance

- Backtest routes use cache; identical requests should not repeat full sliding-window queries.
- News listing and admin article screens should eager-load stock/source relationships to avoid N+1.
- Dashboard/watchlist analytics should pre-load latest prices/news summaries where possible.
- News fetch, sentiment reanalysis, and paper trading snapshots should run in commands/queues, not blocking web requests.
- External HTTP timeouts are bounded for Python, market data, NewsAPI, GNews, Finnhub, GDELT, RSS, and OJK.

## Security

- CSRF protection is present on all POST/PATCH/PUT/DELETE Blade forms.
- All non-public web routes use `auth`; admin routes use both `auth` and `admin`.
- Trade journal queries filter by `auth()->id()`; close/delete abort when ownership mismatches.
- Watchlist operations are scoped to the current user.
- Admin middleware returns 403 for authenticated non-admin users.
- API quote endpoint exposes only market data, not user-specific private fields.
- No raw provider payloads or API secrets are rendered into Blade views.

## Architecture Risks Found

- Admin middleware behavior was aligned to the requested `403` contract during this audit.
- Requested routes `/admin/users`, `/predictions`, `/predict`, and `/trade-journal` are not registered; current app uses `/trades` and `/evaluasi`/analytics prediction integration instead.
- `HybridSentimentAnalyzer` delegates Python failures to `python_unavailable` neutral results; it does not currently run rule-based fallback in Python mode.
- Sentiment method values use `python`/`python_unavailable`, while requested contract lists `python_api`, `hybrid`, and `fallback`.
- Analytics service now exposes both existing nested correlation keys and requested flat aliases: `correlation_same_day`, `lag_h1`, `lag_h3`, `lag_h7`.
- Paper trading writes with `File` to `base_path('output/paper_trading')`; `Storage::fake()` cannot intercept this without refactoring to Laravel disks.
- Laravel app does not expose POST `/predict` or POST `/rank-stocks`; tests cover FastAPI integration through services and `Http::fake()`.
