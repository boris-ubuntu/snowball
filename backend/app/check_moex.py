import httpx, json

r = httpx.get("https://iss.moex.com/iss/securities/RU000A10ASC6/bondization.json?iss.meta=off")
print("STATUS", r.status_code)
d = r.json()
for k in d:
    cols = d[k].get("columns", [])
    rows = d[k].get("data", [])
    print(f"BLOCK {k}: cols={cols}")
    for row in rows[:20]:
        print(f"  {row}")