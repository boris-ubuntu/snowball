"""Populate MOEX coupon cache from host (MOEX unreachable from Docker).
Run in two steps:
  Step 1 (host): python -m backend.app.populate_cache fetch
  Step 2 (Docker): docker compose cp moex_dump.json backend:/app/moex_dump.json
                   docker compose exec backend python -m app.populate_cache load
"""
import urllib.request, json, sys, os
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        try:
            return super().default(obj)
        except:
            return str(obj)


def fetch_bondization(ticker):
    url = f'https://iss.moex.com/iss/securities/{ticker}/bondization.json?iss.meta=off'
    return json.loads(urllib.request.urlopen(url, timeout=15).read())


def process_ticker(ticker, d):
    """Process bondization data, return list of cache entries (with extrapolation)."""
    result = []
    today = date.today()

    # Coupons
    if 'coupons' in d and d['coupons'].get('data'):
        cols = d['coupons']['columns']
        for row in d['coupons']['data']:
            entry = {col.lower(): row[i] for i, col in enumerate(cols) if i < len(row)}
            cd = entry.get('coupondate', '') or ''
            if not cd or cd == 'None':
                continue
            cd = str(cd)
            val = float(entry.get('value_rub') or entry.get('value') or 0)
            if val == 0:
                continue
            fv = float(entry.get('facevalue') or 1000)
            result.append({
                'ticker': ticker,
                'isin': str(entry.get('isin', '')),
                'name': str(entry.get('name', '') or entry.get('shortname', '')),
                'coupon_date': cd[:10],
                'record_date': str(entry.get('recorddate', '')),
                'value': val,
                'value_rub': val,
                'facevalue': fv,
                'is_amortization': False,
            })

    # Amortizations
    if 'amortizations' in d and d['amortizations'].get('data'):
        cols = d['amortizations']['columns']
        for row in d['amortizations']['data']:
            entry = {col.lower(): row[i] for i, col in enumerate(cols) if i < len(row)}
            ad = entry.get('amortdate', '') or ''
            if not ad or ad == 'None':
                continue
            ad = str(ad)
            val = float(entry.get('value_rub') or entry.get('value') or 0)
            if val == 0:
                continue
            result.append({
                'ticker': ticker,
                'isin': str(entry.get('isin', '')),
                'name': str(entry.get('name', '') or ''),
                'coupon_date': ad[:10],
                'record_date': ad[:10],
                'value': val,
                'value_rub': val,
                'facevalue': float(entry.get('facevalue', 0) or 0),
                'is_amortization': True,
            })

    # Extrapolate future coupons
    coups = [r for r in result if not r.get('is_amortization')]
    past = sorted([r for r in coups if datetime.strptime(r['coupon_date'], '%Y-%m-%d').date() < today],
                  key=lambda x: x['coupon_date'])
    future = [r for r in coups if datetime.strptime(r['coupon_date'], '%Y-%m-%d').date() >= today]

    if not future and len(past) >= 2:
        last = past[-1]
        prev = past[-2]
        ld = datetime.strptime(last['coupon_date'], '%Y-%m-%d').date()
        pd = datetime.strptime(prev['coupon_date'], '%Y-%m-%d').date()
        period = (ld - pd).days

        amor_tl = {}
        for am in result:
            if am.get('is_amortization'):
                try:
                    ad = datetime.strptime(am['coupon_date'], '%Y-%m-%d').date()
                    fv = float(am.get('facevalue', 0))
                    if fv > 0:
                        amor_tl[ad] = fv
                except:
                    pass

        nxt = ld
        limit = today + timedelta(days=365 * 2)
        cfv = float(last.get('facevalue', 1000))
        cv = float(last.get('value_rub') or last.get('value', 0))

        while nxt <= limit:
            nxt += timedelta(days=period)
            if nxt >= today:
                for ad, nfv in sorted(amor_tl.items()):
                    if ad <= nxt:
                        cv = cv * (nfv / cfv) if cfv > 0 else cv
                        cfv = nfv
                amor_tl = {k: v for k, v in amor_tl.items() if k > nxt}
                if cv <= 0:
                    break
                result.append({
                    'ticker': ticker,
                    'isin': last.get('isin', ''),
                    'name': last.get('name', ''),
                    'coupon_date': nxt.strftime('%Y-%m-%d'),
                    'record_date': (nxt - timedelta(days=1)).strftime('%Y-%m-%d'),
                    'value': round(cv, 2),
                    'value_rub': round(cv, 2),
                    'facevalue': cfv,
                    'is_amortization': False,
                    'is_extrapolated': True,
                })

    return result


def get_portfolio_bond_tickers():
    """Get bond tickers from portfolio."""
    from app.database import SessionLocal
    from sqlalchemy import text
    os.environ.setdefault('DB_HOST', 'localhost')
    os.environ.setdefault('DB_PORT', '5432')
    os.environ.setdefault('DB_NAME', 'snowball')
    os.environ.setdefault('DB_USER', 'snowball')
    os.environ.setdefault('DB_PASS', 'snowball')
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT DISTINCT s.ticker FROM portfolio_securities ps
            JOIN securities s ON s.id = ps.security_id
            WHERE ps.portfolio_id = 1 AND s.security_type IN ('bond', 'ofz')
        """)).fetchall()
        return [r[0] for r in rows]
    finally:
        db.close()


def cmd_fetch():
    """Fetch all bond data from MOEX and save to JSON."""
    tickers = get_portfolio_bond_tickers()
    print(f"Bonds: {tickers}")
    all_data = {}
    for t in tickers:
        try:
            d = fetch_bondization(t)
            all_data[t] = d
            c = len(d.get('coupons', {}).get('data', []))
            a = len(d.get('amortizations', {}).get('data', []))
            print(f"  {t}: coupons={c} amorts={a}")
        except Exception as e:
            print(f"  {t}: ERROR {e}")
            all_data[t] = None
    with open('moex_dump.json', 'w') as f:
        json.dump(all_data, f, cls=DateTimeEncoder)
    print(f"Saved moex_dump.json ({len(all_data)} tickers)")


def cmd_load():
    """Load data from moex_dump.json into cache."""
    from app.database import SessionLocal
    from app.services.cache_service import set_cached_data

    with open('moex_dump.json') as f:
        all_data = json.load(f)

    db = SessionLocal()
    try:
        for ticker, d in all_data.items():
            if d is None:
                print(f"  Skipping {ticker} (no data)")
                continue
            result = process_ticker(ticker, d)
            if result:
                set_cached_data(db, ticker, 'coupons', result, ttl_minutes=60)
                print(f"  {ticker}: saved {len(result)} entries")
                for r in sorted(result, key=lambda x: x['coupon_date']):
                    print(f"    {r['coupon_date']}: val={r['value']} face={r['facevalue']} amort={r.get('is_amortization',False)} ext={r.get('is_extrapolated',False)}")
            else:
                print(f"  {ticker}: no data")
    finally:
        db.close()


def cmd_fetch_no_db():
    """Fetch with hardcoded tickers (no DB connection needed)."""
    tickers = ['RU000A10ASC6', 'RU000A1010K0', 'RU000A1010V3', 'RU000A1010J5', 'RU000A1010P9',
               'SU26238RMFS4', 'SU26248RMFS2', 'SU26249RMFS0', 'SU26239RMFS2',
               'RU000A105ZJ0', 'RU000A1010N7', 'RU000A1020A5', 'RU000A1037R2',
               'RU000A1038V1', 'RU000A1026G5', 'RU000A1026N9', 'RU000A1038Z2', 'RU000A1010D0']
    print(f"Bonds: {tickers}")
    all_data = {}
    for t in tickers:
        try:
            d = fetch_bondization(t)
            all_data[t] = d
            c = len(d.get('coupons', {}).get('data', []))
            a = len(d.get('amortizations', {}).get('data', []))
            print(f"  {t}: coupons={c} amorts={a}")
        except Exception as e:
            print(f"  {t}: ERROR {e}")
            all_data[t] = None
    with open('moex_dump.json', 'w') as f:
        json.dump(all_data, f, cls=DateTimeEncoder)
    print(f"Saved moex_dump.json ({len(all_data)} tickers)")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python -m app.populate_cache [fetch|fetch-nodb|load]")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == 'fetch':
        cmd_fetch()
    elif cmd == 'fetch-nodb':
        cmd_fetch_no_db()
    elif cmd == 'load':
        cmd_load()
    else:
        print(f"Unknown command: {cmd}")