# Test Coverage Priority Matrix

| Order | Test file | Area | Risk | Effort | Why this order |
|---:|---|---|---|---|---|
| 1 | `tests/Feature/AuthTest.php` | Auth | High | Low | Broken auth exposes protected dashboard data. |
| 2 | `tests/Feature/AdminMiddlewareTest.php` | Role | High | Low | Current middleware redirects regular users instead of returning the required 403. |
| 3 | `tests/Unit/NewsAggregationServiceTest.php` | News | High | High | Deduplication, relevance, and quality filters directly affect thesis dataset validity. |
| 4 | `tests/Unit/SentimentAnalyzerTest.php` | Sentiment | High | Medium | Sentiment labels/scores are persisted into all downstream analytics. |
| 5 | `tests/Feature/StockQuoteApiTest.php` | API | High | Medium | Quote fallback protects dashboard availability when live provider fails. |
| 6 | `tests/Unit/SentimentPriceAnalyticsServiceTest.php` | Analytics | High | Medium | Math regressions can silently corrupt DSS outputs. |
| 7 | `tests/Unit/DecisionSupportServiceTest.php` | DSS | High | Medium | User-facing recommendation labels must remain bounded and explainable. |
| 8 | `tests/Unit/ResearchRankingServiceTest.php` | Ranking | High | Medium | Must not fabricate rankings when Python is unavailable. |
| 9 | `tests/Feature/PythonApiIntegrationTest.php` | FastAPI integration | High | Medium | Documents mocked `/predict` and `/rank-stocks` contracts; Laravel has no local POST routes for them. |
| 10 | `tests/Feature/TradeJournalTest.php` | Journal | Medium | Medium | Verifies account isolation and P&L persistence. |
| 11 | `tests/Feature/BacktestDSSTest.php` | Backtest | Medium | High | Protects macro toggles and cache behavior on expensive routes. |
| 12 | `tests/Feature/PaperTradingCommandTest.php` | Paper trading | Medium | Medium | Scheduled snapshot/evaluation artifacts are easy to break via service wiring. |
| 13 | `tests/Unit/PaperTradingLogServiceTest.php` | Paper trading | Medium | Low | Validates snapshot path/payload discovery. |
| 14 | `tests/Feature/NewsFetchCommandTest.php` | Commands | Medium | Medium | Scheduler smoke tests catch broken provider command wiring. |
| 15 | `tests/Feature/AnalyticsPageTest.php` | UI | Medium | Low | Protects core analytics page load for authenticated users. |
| 16 | `tests/Feature/WatchlistPageTest.php` | UI/ranking | Medium | Low | Ensures watchlist route tolerates unavailable technical ranking. |
| 17 | `tests/Feature/EvaluationReportTest.php` | Evaluation | Medium | Low | Confirms report command emits thesis artifact keys. |
| 18 | `tests/Feature/UIRouteSmokeTest.php` | Frontend | Medium | Medium | Broad Blade smoke suite catches missing routes and broken views. |

## Factory Coverage Hints

| Factory | Status | Notes |
|---|---|---|
| `UserFactory` | Exists | Includes `admin()` state and default `role=user`. |
| `StockFactory` | Exists | Used by route, API, analytics, and ranking tests. |
| `NewsArticleFactory` | Exists | Consider adding named states: `positive()`, `negative()`, `ojkMacro()`, `lowQuality()`. |
| `StockPriceFactory` | Exists | Consider sequence helpers for deterministic price trends. |
| `TradeFactory` | Added | Supports journal create/close/list tests. |
