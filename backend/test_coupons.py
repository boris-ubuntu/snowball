"""Test script to check coupon data and portfolio state"""
import httpx
import asyncio
import json
from datetime import date, datetime

async def main():
    # Test OFZ coupons
    async with httpx.AsyncClient(timeout=10.0) as client:
        url = "https://iss.moex.com/iss/securities/SU26245RMFS9/bondization.json"
        resp = await client.get(url, params={"iss.meta": "off"})
        data = resp.json()
        coupons = data.get("coupons", {})
        cols = coupons.get("columns", [])
        rows = coupons.get("data", [])
        
        today = date.today()
        print(f"Today: {today}")
        print(f"Total coupon rows: {len(rows)}")
        
        upcoming = []
        for row in rows:
            row_dict = dict(zip(cols, row))
            coupon_date_str = row_dict.get("coupondate", "")
            try:
                coupon_date = datetime.strptime(coupon_date_str, "%Y-%m-%d").date()
            except:
                continue
            
            row_dict["coupon_date_obj"] = coupon_date
            if coupon_date >= today:
                upcoming.append(row_dict)
        
        print(f"Upcoming coupons: {len(upcoming)}")
        for u in upcoming:
            print(f"  {u['coupondate']}: value={u['value_rub']} RUB, facevalue={u['facevalue']}")
        
        # Show all future dates from the last known coupon to extrapolate
        if rows:
            last = dict(zip(cols, rows[-1]))
            print(f"\nLast known coupon: {last.get('coupondate')} value={last.get('value_rub')}")
            
            # OFZ 26245 pays semi-annually (Oct/Apr), extrapolate
            from datetime import timedelta
            last_date = datetime.strptime(last["coupondate"], "%Y-%m-%d").date()
            value = float(last.get("value_rub", 0))
            
            print(f"\nExtrapolated future coupons (next 2 years):")
            d = last_date
            for _ in range(4):
                d = d + timedelta(days=183)  # ~6 months
                if d >= today:
                    print(f"  {d}: ~{value} RUB")

if __name__ == "__main__":
    asyncio.run(main())