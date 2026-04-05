import base64
import hmac
import json
import logging
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

from config.settings import settings


class OKXClient:
    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.session = requests.Session()
        self.base_url = settings.okx_base_url.rstrip("/")

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def _sign(self, timestamp: str, method: str, request_path: str, body: str) -> str:
        message = f"{timestamp}{method.upper()}{request_path}{body}"
        mac = hmac.new(settings.okx_api_secret.encode("utf-8"), message.encode("utf-8"), sha256)
        return base64.b64encode(mac.digest()).decode()

    def _private_headers(self, method: str, signed_path: str, body: str = "") -> Dict[str, str]:
        ts = self._timestamp()
        headers = {
            "OK-ACCESS-KEY": settings.okx_api_key,
            "OK-ACCESS-SIGN": self._sign(ts, method, signed_path, body),
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": settings.okx_api_passphrase,
            "Content-Type": "application/json",
        }
        if settings.okx_is_demo:
            headers["x-simulated-trading"] = "1"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        private: bool = False,
    ) -> Dict[str, Any]:
        params = params or {}
        method_upper = method.upper()
        url = f"{self.base_url}{path}"

        if method_upper == "GET":
            query_string = urlencode(params, doseq=True)
            signed_path = f"{path}?{query_string}" if query_string else path
            headers = self._private_headers(method_upper, signed_path) if private else {}

            response = self.session.get(
                url,
                params=params,
                headers=headers,
                timeout=20,
            )
        else:
            body = json.dumps(params, separators=(",", ":")) if params else ""
            headers = self._private_headers(method_upper, path, body) if private else {"Content-Type": "application/json"}

            response = self.session.post(
                url,
                data=body,
                headers=headers,
                timeout=20,
            )

        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("code") not in (None, "0", 0):
            raise RuntimeError(payload)
        return payload

    def _should_suppress_error_log(self, fn_name: str, exc: Exception) -> bool:
        text = str(exc)
        # OKX 51010 on max-avail-size under current account mode is expected in your setup.
        if fn_name == "get_max_avail_size" and "51010" in text and "current account mode" in text.lower():
            return True
        return False

    def _safe(self, fn, default, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            fn_name = getattr(fn, "__name__", "")
            if self._should_suppress_error_log(fn_name, exc):
                self.logger.info("okx soft-fallback on %s: %s", fn_name, exc)
            else:
                self.logger.exception("okx error: %s", exc)
            return default

    def get_balance(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v5/account/balance", private=True)

    def get_positions(self) -> Dict[str, Any]:
        return self._request(
            "GET",
            "/api/v5/account/positions",
            params={"instType": settings.instrument_type},
            private=True,
        )

    def get_account_config(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v5/account/config", private=True)

    def get_max_avail_size(self, inst_id: str, td_mode: str) -> Dict[str, Any]:
        return self._request(
            "GET",
            "/api/v5/account/max-avail-size",
            params={"instId": inst_id, "tdMode": td_mode},
            private=True,
        )

    def get_tickers(self) -> List[Dict[str, Any]]:
        return self._request(
            "GET",
            "/api/v5/market/tickers",
            params={"instType": settings.instrument_type},
            private=False,
        ).get("data", [])

    def get_instruments(self) -> List[Dict[str, Any]]:
        return self._request(
            "GET",
            "/api/v5/public/instruments",
            params={"instType": settings.instrument_type},
            private=False,
        ).get("data", [])

    def get_candles(self, inst_id: str, bar: str, limit: int) -> List[List[Any]]:
        return self._request(
            "GET",
            "/api/v5/market/candles",
            params={"instId": inst_id, "bar": bar, "limit": str(limit)},
            private=False,
        ).get("data", [])

    def set_leverage(
        self,
        inst_id: str,
        leverage: int,
        margin_mode: str = "cross",
        pos_side: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "instId": inst_id,
            "lever": str(leverage),
            "mgnMode": margin_mode,
        }
        if pos_side:
            payload["posSide"] = pos_side
        return self._request("POST", "/api/v5/account/set-leverage", params=payload, private=True)

    def place_order(
        self,
        inst_id: str,
        side: str,
        pos_side: Optional[str],
        size: float,
        order_type: str = "limit",
        price: Optional[float] = None,
        reduce_only: bool = False,
        margin_mode: str = "cross",
    ) -> Dict[str, Any]:
        payload = {
            "instId": inst_id,
            "tdMode": margin_mode,
            "side": side,
            "ordType": order_type,
            "sz": str(size),
            "reduceOnly": "true" if reduce_only else "false",
        }
        if pos_side:
            payload["posSide"] = pos_side
        if price is not None and order_type in {"limit", "post_only", "fok", "ioc"}:
            payload["px"] = str(price)
        return self._request("POST", "/api/v5/trade/order", params=payload, private=True)

    def place_algo_tp_sl(
        self,
        inst_id: str,
        side: str,
        pos_side: Optional[str],
        tp_trigger_px: Optional[float],
        sl_trigger_px: Optional[float],
        size: float,
        margin_mode: str = "cross",
    ) -> Dict[str, Any]:
        payload = {
            "instId": inst_id,
            "tdMode": margin_mode,
            "side": side,
            "ordType": "conditional",
            "sz": str(size),
        }
        if pos_side:
            payload["posSide"] = pos_side
        if tp_trigger_px is not None:
            payload["tpTriggerPx"] = str(tp_trigger_px)
            payload["tpOrdPx"] = "-1"
        if sl_trigger_px is not None:
            payload["slTriggerPx"] = str(sl_trigger_px)
            payload["slOrdPx"] = "-1"
        return self._request("POST", "/api/v5/trade/order-algo", params=payload, private=True)

    def safe_get_balance(self) -> Dict[str, Any]:
        return self._safe(self.get_balance, {"code": "-1", "data": []})

    def safe_get_positions(self) -> Dict[str, Any]:
        return self._safe(self.get_positions, {"code": "-1", "data": []})

    def safe_get_account_config(self) -> Dict[str, Any]:
        return self._safe(self.get_account_config, {"code": "-1", "data": []})

    def safe_get_max_avail_size(self, inst_id: str, td_mode: str) -> Dict[str, Any]:
        return self._safe(
            self.get_max_avail_size,
            {"code": "51010", "msg": "You can't complete this request under your current account mode.", "data": []},
            inst_id,
            td_mode,
        )

    def safe_get_tickers(self) -> List[Dict[str, Any]]:
        return self._safe(self.get_tickers, [])

    def safe_get_instruments(self) -> List[Dict[str, Any]]:
        return self._safe(self.get_instruments, [])

    def safe_get_candles(self, inst_id: str, bar: str, limit: int) -> List[List[Any]]:
        return self._safe(self.get_candles, [], inst_id, bar, limit)

    def safe_set_leverage(
        self,
        inst_id: str,
        leverage: int,
        margin_mode: str = "cross",
        pos_side: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._safe(
            self.set_leverage,
            {"code": "-1", "data": []},
            inst_id,
            leverage,
            margin_mode,
            pos_side,
        )

    def safe_place_order(self, **kwargs: Any) -> Dict[str, Any]:
        return self._safe(self.place_order, {"code": "-1", "data": []}, **kwargs)

    def safe_place_algo_tp_sl(self, **kwargs: Any) -> Dict[str, Any]:
        return self._safe(self.place_algo_tp_sl, {"code": "-1", "data": []}, **kwargs)
