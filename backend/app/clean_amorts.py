import asyncio
from app.database import SessionLocal
from app import models, crud
from app.services.moex_coupons import get_portfolio_coupons

async def clean():
    db = SessionLocal()
    try:
        coupons = await get_portfolio_coupons(1, upcoming_only=False)
        amort_dates = set()
        for c in coupons:
            if c.get("is_amortization") and c["coupon_date"] <= "2026-07-21":
                amort_dates.add((c["ticker"], c["coupon_date"], c["total_expected"]))
        print(f"Found {len(amort_dates)} amortization entries to delete")

        amort_txns = db.query(models.Transaction).filter(
            models.Transaction.portfolio_id == 1,
            models.Transaction.transaction_type == "accrual"
        ).all()
        print(f"Total accrual txns: {len(amort_txns)}")

        deleted = 0
        for tx in amort_txns:
            sec = db.query(models.Security).filter(models.Security.id == tx.security_id).first()
            if not sec:
                continue
            key = (sec.ticker, str(tx.transaction_date), tx.total_amount)
            if key in amort_dates:
                db.delete(tx)
                deleted += 1
                print(f"  Delete {sec.ticker} {tx.transaction_date} amount={tx.total_amount}")

        if deleted > 0:
            db.commit()
            print(f"Deleted {deleted} amortization accrual transactions")
            for p in db.query(models.PortfolioPosition).filter(
                models.PortfolioPosition.portfolio_id == 1
            ).all():
                crud.recalculate_position(db, 1, p.security_id)
            print("Positions recalculated")
        else:
            print("No amortization accruals found")
    finally:
        db.close()

asyncio.run(clean())