import httpx, asyncio, json
async def main():
    async with httpx.AsyncClient() as client:
        url = "https://iss.moex.com/iss/securities/SU26245RMFS9/bondization.json"
        r = await client.get(url, params={"iss.meta": "off"})
        d = r.json()
        coupons = d.get("coupons", {})
        cols = coupons["columns"]
        for i, row in enumerate(coupons["data"]):
            rd = dict(zip(cols, row))
            print(f"{i}: {rd['coupondate']} val={rd['value_rub']}")
        print(f"\nTotal: {len(coupons['data'])}")
asyncio.run(main())