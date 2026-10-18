"""Conversational Shop CFO and Autonomous Intelligence Agent.
Answers natural language financial/operational questions using grounded shop data.
"""
import json
from google import genai
from google.genai import types
import store
from intl import money_label

CFO_SYSTEM_PROMPT = """You are SaySale AI CFO, an expert retail finance and inventory co-pilot for shop owners.
You provide clear, accurate, and actionable advice based ONLY on the shop's actual data provided below.
Rules:
1. Always state figures in the shop's currency.
2. Never invent numbers, imaginary products, or fictional transactions.
3. Be concise and direct: owners are busy shopkeepers.
4. When asked about inventory, highlight stockout risks and daily sales velocity.
5. Provide actionable recommendations (e.g. reordering before a specific day, margins, expenses).
6. Support multilingual conversation in English, French, or Spanish according to the user's prompt.
"""


def format_analytics_for_prompt(analytics: dict, language: str = 'en') -> str:
    shop = analytics['shop']
    curr = analytics['currency']
    fmt = lambda v: money_label(v, curr, language)
    
    top_p = ", ".join(f"{p['name']} ({p['units_sold']} units, {fmt(p['revenue_minor'])})" for p in analytics['top_products']) or "None yet"
    low_p = ", ".join(f"{p['name']} (Stock: {p['quantity']}, Threshold: {p['threshold']})" for p in analytics['low_stock']) or "All products healthy"
    
    runway_items = []
    for r in analytics['inventory_runway']:
        days_str = f"{r['days_left']} days left" if r['days_left'] is not None else "No recent sales"
        runway_items.append(f"{r['name']}: stock={r['current_stock']}, velocity={r['daily_velocity']} units/day, runway={days_str}")
    runway_text = "\n  - " + "\n  - ".join(runway_items) if runway_items else "No inventory tracked"

    reorder_items = []
    for item in analytics.get('restock_recommendations', []):
        if item['suggested_quantity'] is None:
            reorder_items.append(f"{item['name']}: below its stock threshold, but recent sales are insufficient to suggest an order quantity")
        else:
            reorder_items.append(
                f"{item['name']}: consider ordering {item['suggested_quantity']} units "
                f"(current stock {item['current_stock']}; target {item['target_stock']} units "
                f"for {item['target_coverage_days']} days of coverage)"
            )
    reorder_text = "\n  - " + "\n  - ".join(reorder_items) if reorder_items else "No reorder indicated by the current rule"
    
    recent_txs = []
    for tx in analytics['recent_transactions'][:8]:
        amt_str = fmt(tx['amount_minor']) if tx['amount_minor'] is not None else "N/A"
        tx_type_str = str(tx.get('type') or 'TRANSACTION').upper()
        recent_txs.append(f"{tx['created_at'][:10]} | {tx_type_str} | {tx['item_name'] or 'Expense'} | {amt_str}")
    recent_text = "\n  - " + "\n  - ".join(recent_txs) if recent_txs else "No transactions recorded yet"

    return f"""SHOP CONTEXT:
Shop Name: {shop['name']}
Currency: {curr}
Country: {shop['country']}
Timezone: {shop['timezone']}

FINANCIAL SNAPSHOT (All-time / Recent):
- Total Sales Recorded: {fmt(analytics['sales_total_minor'])} ({analytics['sales_count']} sales)
- Total Expenses: {fmt(analytics['expense_total_minor'])}
- Net Cash Inflow (Sales minus Expenses): {fmt(analytics['net_cash_minor'])}

INVENTORY & RUNWAY:
- Low / Depleted Stock Items: {low_p}
- Top Selling Items: {top_p}
- SKU Runway Velocity:
  {runway_text}
- Rule-based Restock Guidance (14-day target; heuristic, not a demand forecast):
  {reorder_text}

RECENT ACTIVITY:
  {recent_text}
"""


def ask_cfo(token: str, shop_id: str, question: str, api_key: str, model: str, language: str = 'en') -> str:
    """Answer an owner or manager's natural language question using grounded shop data."""
    if not question.strip():
        return "Please ask a question regarding your sales, expenses, or inventory."
    if not api_key or not model:
        raise ValueError("Configure GEMINI_API_KEY and GEMINI_MODEL to chat with your AI CFO.")
    
    store.authorize_ai(token, shop_id)
    analytics = store.get_shop_analytics(token, shop_id)
    data_context = format_analytics_for_prompt(analytics, language)
    
    prompt = f"{data_context}\n\nUSER QUESTION: {question}\n\nANSWER:"
    
    with genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=30000)) as client:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=CFO_SYSTEM_PROMPT,
                temperature=0.2,
            )
        )
    return (response.text or "").strip()


def generate_executive_briefing(token: str, shop_id: str, api_key: str, model: str, language: str = 'en') -> str:
    """Generate a daily WhatsApp/bulletin-ready executive briefing with proactive recommendations."""
    if not api_key or not model:
        raise ValueError("Configure GEMINI_API_KEY and GEMINI_MODEL to generate executive briefings.")
    
    store.authorize_ai(token, shop_id)
    analytics = store.get_shop_analytics(token, shop_id)
    data_context = format_analytics_for_prompt(analytics, language)
    
    instruction = (
        "Generate a concise, high-impact Daily Executive Briefing for the shop owner, "
        "formatted in clean Markdown with emojis for WhatsApp or email. "
        "Include: 1) Executive Summary (Sales, Expenses, Net), 2) Inventory Alert & Runways, "
        "3) 2 Proactive Tactical Recommendations (e.g. restock order or margin adjustment)."
    )
    
    prompt = f"{data_context}\n\nTASK: {instruction}"
    
    with genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=30000)) as client:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=CFO_SYSTEM_PROMPT,
                temperature=0.2,
            )
        )
    return (response.text or "").strip()
