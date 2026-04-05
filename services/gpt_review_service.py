import json
import logging
from typing import Any, Dict, List

from config.settings import settings

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None


class GPTReviewService:
    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.client = OpenAI(api_key=settings.openai_api_key) if (OpenAI and settings.openai_api_key) else None

    def available(self) -> bool:
        return bool(self.client and settings.enable_daily_gpt_review)

    def _extract_json(self, text: str) -> Dict[str, Any]:
        text = (text or "").strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except Exception:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                return {}
        return {}

    def _fallback_suggestions(self, digest: Dict[str, Any]) -> List[Dict[str, Any]]:
        stats = digest.get("stats", {})
        suggestions: List[Dict[str, Any]] = []
        win_rate = float(stats.get("win_rate", 0.0) or 0.0)
        avg_pnl = float(stats.get("avg_pnl", 0.0) or 0.0)
        avg_dd = float(stats.get("avg_drawdown", 0.0) or 0.0)
        avg_hold = float(stats.get("avg_hold_minutes", 0.0) or 0.0)

        if win_rate < 0.45 or avg_pnl < 0:
            suggestions.append({
                "area": "entry_logic",
                "summary": "提高進場選擇性，避免低質量信號大量成交。",
                "param_patch": {"entry_confidence_shift": 0.018, "breakout_bias": -0.03},
            })
        else:
            suggestions.append({
                "area": "entry_logic",
                "summary": "略微放寬進場以擴大真實樣本。",
                "param_patch": {"entry_confidence_shift": -0.01, "size_multiplier_bias": 0.04},
            })

        if avg_dd < avg_pnl * -1.1:
            suggestions.append({
                "area": "protective_orders",
                "summary": "保護單偏鬆，收緊 break-even 與 trailing。",
                "param_patch": {"protective_tightness": 0.08, "trailing_aggression": 0.1, "break_even_bias": -0.08},
            })

        if avg_hold > 90 and avg_pnl <= 0:
            suggestions.append({
                "area": "exit_style",
                "summary": "持倉偏久但收益差，應提早退出弱單。",
                "param_patch": {"exit_aggression": 0.08, "exit_patience": -0.08, "hold_extension_bias": -0.03},
            })
        elif win_rate > 0.5 and avg_pnl > 0:
            suggestions.append({
                "area": "exit_style",
                "summary": "獲利單值得再抱一些。",
                "param_patch": {"exit_patience": 0.07, "take_profit_atr_bias": 0.08, "hold_extension_bias": 0.03},
            })

        return suggestions

    def _call_gpt(self, payload: Dict[str, Any], instructions: str) -> Dict[str, Any]:
        if not self.available():
            return {}
        try:
            response = self.client.responses.create(
                model=settings.gpt_model,
                reasoning={"effort": settings.gpt_reasoning_effort},
                instructions=instructions,
                input=json.dumps(payload, ensure_ascii=False),
                timeout=settings.gpt_timeout_sec,
            )
            return self._extract_json(getattr(response, "output_text", ""))
        except Exception as exc:  # pragma: no cover
            self.logger.exception("GPT review call failed: %s", exc)
            return {"error": str(exc)}

    def _judge_patch(self, digest: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
        stats = digest.get("stats", {})
        win_rate = float(stats.get("win_rate", 0.0) or 0.0)
        avg_pnl = float(stats.get("avg_pnl", 0.0) or 0.0)
        avg_dd = float(stats.get("avg_drawdown", 0.0) or 0.0)
        avg_hold = float(stats.get("avg_hold_minutes", 0.0) or 0.0)

        score = 0.5
        reasons: List[str] = []
        entry_shift = float(patch.get("entry_confidence_shift", 0.0) or 0.0)
        tp_bias = float(patch.get("take_profit_atr_bias", 0.0) or 0.0)
        sl_bias = float(patch.get("stop_loss_atr_bias", 0.0) or 0.0)
        break_even_bias = float(patch.get("break_even_bias", 0.0) or 0.0)
        trailing = float(patch.get("trailing_aggression", 0.0) or 0.0)
        exit_agg = float(patch.get("exit_aggression", 0.0) or 0.0)
        exit_patience = float(patch.get("exit_patience", 0.0) or 0.0)

        if entry_shift > 0 and (win_rate < 0.48 or avg_pnl < 0):
            score += 0.18
            reasons.append("低勝率時提高門檻合理")
        elif entry_shift < 0 and win_rate > 0.53 and avg_pnl >= 0:
            score += 0.14
            reasons.append("表現尚可時略放寬進場有助擴樣本")
        elif entry_shift != 0:
            score -= 0.08
            reasons.append("進場調整與當前統計不完全一致")

        if break_even_bias < 0 or trailing > 0 or sl_bias < 0:
            if avg_dd < avg_pnl * -1.05 or avg_pnl < 0:
                score += 0.16
                reasons.append("回撤偏大，收緊保護單合理")
            else:
                score -= 0.05

        if tp_bias > 0 or exit_patience > 0:
            if win_rate > 0.5 and avg_pnl > 0:
                score += 0.14
                reasons.append("正報酬日可延長持有優質單")
            else:
                score -= 0.07

        if exit_agg > 0 and (avg_hold > 80 and avg_pnl <= 0):
            score += 0.14
            reasons.append("持有過久但收益差，提早退出合理")
        elif exit_agg > 0:
            score -= 0.03

        verdict = "accept" if score >= 0.56 else "discuss_more"
        if score <= 0.42:
            verdict = "reject"
        return {"verdict": verdict, "score": round(score, 4), "reasons": reasons}

    def _merge_accepted(self, accepted: List[Dict[str, Any]]) -> Dict[str, Any]:
        merged: Dict[str, float] = {}
        for item in accepted:
            patch = item.get("param_patch", {})
            for key, value in patch.items():
                try:
                    merged[key] = merged.get(key, 0.0) + float(value)
                except Exception:
                    continue
        for key in list(merged.keys()):
            merged[key] = round(merged[key], 6)
        return merged

    def deliberate(self, digest: Dict[str, Any], current_policy: Dict[str, Any]) -> Dict[str, Any]:
        fallback = self._fallback_suggestions(digest)
        discussion_log: List[Dict[str, Any]] = []

        prompt = {
            "goal": "Analyze one day of live crypto trades. Provide suggestions, not direct hard locks. The bot is the final judge.",
            "rules": [
                "Focus on entry logic, position management, protective orders, and exit style.",
                "Templates are assistive only.",
                "No same-direction cap recommendation.",
                "Do not recommend disabling weak symbols as a hard rule.",
                "Return strict JSON only.",
            ],
            "digest": digest,
            "current_policy": current_policy,
            "required_json_schema": {
                "summary": "plain text",
                "suggestions": [
                    {
                        "area": "entry_logic|position_management|protective_orders|exit_style|sizing",
                        "summary": "plain text",
                        "param_patch": {
                            "entry_confidence_shift": "float delta",
                            "size_multiplier_bias": "float delta",
                            "leverage_bias": "float delta",
                            "breakout_bias": "float delta",
                            "trend_follow_bias": "float delta",
                            "stop_loss_atr_bias": "float delta",
                            "take_profit_atr_bias": "float delta",
                            "break_even_bias": "float delta",
                            "trailing_aggression": "float delta",
                            "protective_tightness": "float delta",
                            "exit_aggression": "float delta",
                            "exit_patience": "float delta",
                            "hold_extension_bias": "float delta",
                        },
                    }
                ],
            },
        }
        response = self._call_gpt(prompt, "You are the external trading reviewer. Output JSON only.")
        suggestions = response.get("suggestions") if isinstance(response.get("suggestions"), list) else fallback
        summary = str(response.get("summary", "GPT 未提供可解析回覆，改用本地審議。"))

        current_suggestions = suggestions
        rounds_used = 0
        for round_idx in range(settings.gpt_review_max_rounds):
            rounds_used = round_idx + 1
            judged = []
            objections = []
            for item in current_suggestions:
                patch = item.get("param_patch", {}) if isinstance(item, dict) else {}
                verdict = self._judge_patch(digest, patch)
                row = dict(item)
                row.update(verdict)
                judged.append(row)
                if verdict["verdict"] == "discuss_more":
                    objections.append({"summary": item.get("summary"), "patch": patch, "reasons": verdict["reasons"]})
            discussion_log.append({"round": rounds_used, "judged": judged})
            if not objections or not self.available() or round_idx + 1 >= settings.gpt_review_max_rounds:
                current_suggestions = judged
                break

            revision_prompt = {
                "digest": digest,
                "current_policy": current_policy,
                "previous_summary": summary,
                "objections": objections,
                "instruction": "Revise the suggestions so the bot and GPT can converge. Return strict JSON only.",
            }
            revised = self._call_gpt(revision_prompt, "You are in a negotiation loop with the bot. Output JSON only.")
            current_suggestions = revised.get("suggestions") if isinstance(revised.get("suggestions"), list) else judged
            summary = str(revised.get("summary", summary))

        accepted = [x for x in current_suggestions if str(x.get("verdict", "accept")) == "accept"]
        rejected = [x for x in current_suggestions if str(x.get("verdict", "")) == "reject"]
        need_more = [x for x in current_suggestions if str(x.get("verdict", "")) == "discuss_more"]
        consensus_patch = self._merge_accepted(accepted)
        plain_text = f"每日 GPT 協商檢討：{digest.get('trade_date')}，建議 {len(current_suggestions)} 條，接受 {len(accepted)}、拒絕 {len(rejected)}、未完全收斂 {len(need_more)}。{summary}"
        return {
            "plain_text": plain_text,
            "summary": summary,
            "discussion_log": discussion_log,
            "accepted": accepted,
            "rejected": rejected,
            "need_more": need_more,
            "consensus_patch": consensus_patch,
            "rounds_used": rounds_used,
            "gpt_status": self.available(),
        }
