def get_account_summary(self) -> Dict[str, float]:
    payload = self.client.safe_get_balance()
    rows = payload.get("data", [])

    if not rows:
        return {"equity": 0.0, "available": 0.0, "used_margin": 0.0}

    row = rows[0]

    try:
        # 🔥 優先抓 details（合約帳戶）
        details = row.get("details", [])

        usdt_detail = next(
            (d for d in details if d.get("ccy") == "USDT"),
            None
        )

        if usdt_detail:
            equity = float(usdt_detail.get("eq", 0))
            available = float(usdt_detail.get("availBal", 0))
        else:
            # fallback（舊版帳戶）
            equity = float(row.get("totalEq", 0))
            available = float(row.get("adjEq", 0))

    except Exception:
        equity, available = 0.0, 0.0

    return {
        "equity": equity,
        "available": available,
        "used_margin": max(equity - available, 0.0),
    }
