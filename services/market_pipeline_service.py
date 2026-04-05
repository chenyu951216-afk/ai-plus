import time
import logging

logger = logging.getLogger("MarketPipelineService")


class MarketPipelineService:
    def __init__(self, client, settings):
        self.client = client
        self.settings = settings

    def scan(self, symbols):
        results = []

        timeframe = self.settings.primary_timeframe
        limit = self.settings.candle_limit

        for symbol in symbols:
            try:
                # ✅ 正確呼叫（修復你爆炸的地方）
                raw = self.client.safe_get_candles(symbol, timeframe, limit)

                if not raw or len(raw) < 20:
                    logger.warning(f"[SCAN] {symbol} insufficient data")
                    continue

                # ✅ 轉換 K線
                candles = self._parse_candles(raw)

                # ✅ 計算簡單指標（讓 AI 有東西吃）
                signal = self._analyze(symbol, candles)

                if signal:
                    results.append(signal)

                time.sleep(0.02)  # 防爆 API

            except Exception as e:
                logger.error(f"[SCAN ERROR] {symbol} {str(e)}")
                continue

        return results

    # =========================
    # 🔧 K線轉換
    # =========================
    def _parse_candles(self, raw):
        parsed = []

        for c in raw:
            try:
                parsed.append({
                    "ts": int(c[0]),
                    "open": float(c[1]),
                    "high": float(c[2]),
                    "low": float(c[3]),
                    "close": float(c[4]),
                    "volume": float(c[5])
                })
            except:
                continue

        return parsed

    # =========================
    # 🧠 AI前處理分析（不鎖死）
    # =========================
    def _analyze(self, symbol, candles):
        closes = [c["close"] for c in candles]

        if len(closes) < 20:
            return None

        # ===== 趨勢（非常輕量，避免限制AI）
        ema_short = sum(closes[-5:]) / 5
        ema_long = sum(closes[-20:]) / 20

        trend = "long" if ema_short > ema_long else "short"

        # ===== 波動（簡單 ATR）
        ranges = [(c["high"] - c["low"]) for c in candles[-14:]]
        atr = sum(ranges) / len(ranges)

        confidence = min(1.0, abs(ema_short - ema_long) / (atr + 1e-6))

        return {
            "symbol": symbol,
            "trend": trend,
            "confidence": round(confidence, 4),
            "price": closes[-1],
            "atr": atr
        }
