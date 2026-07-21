# Graph Report - .  (2026-07-21)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 388 nodes · 796 edges · 27 communities (13 shown, 14 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 14 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `3b37774f`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- get_cached_data
- portfolio.py
- crud.py
- main.py
- get_current_price
- securities.py
- schemas.py
- app/auth.py
- lqdt_service.py
- manifest.json
- create_icon
- app.js
- api.js
- chart.js
- dividends.js
- dividendsHistogram.js
- modal.js
- positions.js
- securities.js
- summary.js
- transactions.js
- config.js
- utils.js
- sw.js

## God Nodes (most connected - your core abstractions)
1. `get_cached_data()` - 22 edges
2. `set_cached_data()` - 20 edges
3. `check_and_process_accruals()` - 16 edges
4. `get_dohod_dividends_for_portfolio()` - 15 edges
5. `get_current_price()` - 15 edges
6. `get_dashboard()` - 13 edges
7. `get_portfolio()` - 13 edges
8. `Security` - 12 edges
9. `get_portfolio_securities()` - 10 edges
10. `get_portfolio_dividends_all()` - 10 edges

## Surprising Connections (you probably didn't know these)
- `login()` --calls--> `authenticate_user()`  [INFERRED]
  backend/app/routers/auth.py → backend/app/auth.py
- `login()` --calls--> `create_access_token()`  [INFERRED]
  backend/app/routers/auth.py → backend/app/auth.py
- `create_dividend()` --calls--> `get_security()`  [EXTRACTED]
  backend/app/routers/dividends.py → backend/app/crud.py
- `create_position()` --calls--> `get_security()`  [EXTRACTED]
  backend/app/routers/portfolio.py → backend/app/crud.py
- `create_transaction()` --calls--> `get_security()`  [EXTRACTED]
  backend/app/routers/portfolio.py → backend/app/crud.py

## Import Cycles
- None detected.

## Communities (27 total, 14 thin omitted)

### Community 0 - "get_cached_data"
Cohesion: 0.06
Nodes (52): get_economy_indicators(), Session, Get current CBR key rate and inflation (cache-first), Session, Background updater service. Runs periodic tasks to refresh cached data from MOE, Refresh coupons for a single ticker., Refresh coupons for all bonds/OFZ in portfolio (background)., Refresh CBR exchange rates (background). Skip if cache is fresh (24h TTL). (+44 more)

### Community 1 - "portfolio.py"
Cohesion: 0.08
Nodes (46): _auto_accrue(), create_portfolio(), create_position(), create_transaction(), delete_position(), delete_transaction(), delete_transactions_by_security(), get_dashboard() (+38 more)

### Community 2 - "crud.py"
Cohesion: 0.10
Nodes (45): create_dividend(), create_portfolio(), create_position(), create_security(), create_transaction(), delete_position(), delete_security(), delete_transaction() (+37 more)

### Community 3 - "main.py"
Cohesion: 0.06
Nodes (35): get_password_hash(), Script to check and load missing securities from MOEX. Run inside container: py, Search for specific known tickers that might be missing from standard boards., search_missing_securities(), check_db_connection(), get_db(), init_db(), Check if database is connected (+27 more)

### Community 4 - "get_current_price"
Cohesion: 0.09
Nodes (29): Any, get_cbr_rates(), Exchange rates router - CBR currency rates, Get current CBR exchange rates, Force refresh CBR exchange rates (always hits the CBR API directly, no local cac, refresh_cbr_rates(), convert_from_rub(), fetch_cbr_rates() (+21 more)

### Community 5 - "securities.py"
Cohesion: 0.11
Nodes (26): create_security(), delete_security(), get_security(), list_securities(), load_all_securities_endpoint(), load_ofz(), Session, Refresh price for a single security from MOEX (+18 more)

### Community 6 - "schemas.py"
Cohesion: 0.15
Nodes (26): Config, DashboardPosition, DashboardResponse, DividendBase, DividendCreate, DividendResponse, PortfolioBase, PortfolioCreate (+18 more)

### Community 7 - "app/auth.py"
Cohesion: 0.11
Nodes (18): authenticate_user(), create_access_token(), get_current_user(), JWT Authentication module, Dependency to get current user from token. Returns None if no token., Dependency that requires authentication., require_user(), Get database URL: DATABASE_URL env takes priority, fall back to individual param (+10 more)

### Community 8 - "lqdt_service.py"
Cohesion: 0.14
Nodes (22): get_security_by_ticker(), calculate_lqdt_accruals(), get_existing_lqdt_accruals(), get_lqdt_projection(), get_lqdt_quantity_and_avg_price(), get_lqdt_transactions(), get_rusfar_rate(), process_lqdt_accruals() (+14 more)

### Community 9 - "manifest.json"
Cohesion: 0.11
Nodes (18): background_color, categories, description, dir, display, icons, lang, name (+10 more)

## Knowledge Gaps
- **31 isolated node(s):** `API`, `App`, `ConfirmDialog`, `ChartComponent`, `DividendsComponent` (+26 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **14 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_cached_data()` connect `get_cached_data` to `lqdt_service.py`, `portfolio.py`, `crud.py`, `get_current_price`?**
  _High betweenness centrality (0.041) - this node is a cross-community bridge._
- **Why does `fetch_cbr_rates()` connect `get_current_price` to `get_cached_data`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **What connects `API`, `App`, `ConfirmDialog` to the rest of the system?**
  _31 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `get_cached_data` be split into smaller, more focused modules?**
  _Cohesion score 0.05989110707803993 - nodes in this community are weakly interconnected._
- **Should `portfolio.py` be split into smaller, more focused modules?**
  _Cohesion score 0.08418367346938775 - nodes in this community are weakly interconnected._
- **Should `crud.py` be split into smaller, more focused modules?**
  _Cohesion score 0.10083256244218317 - nodes in this community are weakly interconnected._
- **Should `main.py` be split into smaller, more focused modules?**
  _Cohesion score 0.0647342995169082 - nodes in this community are weakly interconnected._