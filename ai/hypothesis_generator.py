# ai/hypothesis_generator.py — UPDATED: utilise AIRouter (Groq/Grok/Ollama)

import json
import re
import logging

logger = logging.getLogger("HypothesisGenerator")

SYSTEM_PROMPT = """You are a senior quantitative equity analyst specialising in European equities (EURO STOXX 50).
You think rigorously, cite specific metrics, and produce structured investment hypotheses.
Always structure your response as valid JSON with the keys defined in the user prompt.
Be concise, specific, and grounded in the data provided.
Return ONLY the JSON object — no preamble, no markdown fences, no explanation."""


def _parse_json(raw: str, ticker: str, ticker_name: str) -> dict:
    text = raw.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    cleaned = re.sub(r'```(?:json)?\s*', '', text).strip().rstrip('`').strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    logger.warning(f"JSON parse failed for {ticker}")
    return {"ticker": ticker, "name": ticker_name, "direction": "UNKNOWN",
            "thesis": raw, "catalysts": [], "risks": [], "key_metrics": {},
            "conviction": "LOW", "time_horizon": "6M", "price_target_rationale": ""}


class HypothesisGenerator:

    def __init__(self):
        from ai.ai_router import get_ai_router
        self._router = get_ai_router()

    def _chat(self, messages, temperature=0.5):
        return self._router.chat(messages=messages, system=SYSTEM_PROMPT,
                                  temperature=temperature, max_tokens=1500)

    def generate_hypothesis(self, ticker, ticker_name, fundamentals,
                             scores, user_context="") -> dict:
        fund_str  = json.dumps(
            {k: round(v, 4) if isinstance(v, float) else v
             for k, v in fundamentals.items() if v is not None}, indent=2)
        score_str = json.dumps(scores, indent=2)

        prompt = f"""Analyse {ticker} ({ticker_name}) and produce an investment hypothesis.

FUNDAMENTAL DATA:
{fund_str}

QUANTITATIVE SCORES:
{score_str}

ADDITIONAL CONTEXT:
{user_context or "None provided."}

Return ONLY a JSON object:
{{
  "ticker": "{ticker}",
  "name": "{ticker_name}",
  "direction": "LONG" or "SHORT",
  "thesis": "2-3 sentence investment thesis",
  "catalysts": ["catalyst 1", "catalyst 2", "catalyst 3"],
  "risks": ["risk 1", "risk 2"],
  "key_metrics": {{"pe": <value>, "roe": <value>, "momentum_12m": <value>}},
  "conviction": "HIGH" or "MEDIUM" or "LOW",
  "time_horizon": "3M" or "6M" or "12M",
  "price_target_rationale": "brief rationale"
}}"""

        raw = self._chat([{"role": "user", "content": prompt}], temperature=0.4)
        return _parse_json(raw, ticker, ticker_name)

    def compare_pair(self, ticker_a, ticker_b, data_a, data_b) -> str:
        prompt = f"""Evaluate a long/short pair trade:

LONG CANDIDATE: {ticker_a}
{json.dumps(data_a, indent=2)}

SHORT CANDIDATE: {ticker_b}
{json.dumps(data_b, indent=2)}

Produce a detailed pair trade thesis:
1. Relative value rationale
2. Convergence catalyst
3. Key risks to the pair
4. Suggested entry conditions
5. Expected time horizon"""
        return self._chat([{"role": "user", "content": prompt}], temperature=0.5)

    def analyse_portfolio(self, portfolio_summary, risk_metrics) -> str:
        prompt = f"""Review this EURO STOXX 50 long/short portfolio.

PORTFOLIO SUMMARY:
{json.dumps(portfolio_summary, indent=2)}

RISK METRICS:
{json.dumps(risk_metrics, indent=2)}

Provide: positioning concentration, risk/reward balance,
macro sensitivities, and 2-3 actionable recommendations."""
        return self._chat([{"role": "user", "content": prompt}], temperature=0.6)

    def free_analysis(self, user_message, context="") -> str:
        system = SYSTEM_PROMPT
        if context:
            system += f"\n\nCONTEXT:\n{context}"
        return self._router.chat(
            messages=[{"role": "user", "content": user_message}],
            system=system, temperature=0.7)