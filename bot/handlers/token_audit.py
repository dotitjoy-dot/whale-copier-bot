"""
Token audit handler — query GoPlus/TokenSniffer safety scores before buying.
"""

from __future__ import annotations

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.keyboards import back_button
from bot.menus import TOKEN_AUDIT_INPUT, TOKEN_AUDIT_RESULT, DASHBOARD
from core.logger import get_logger

logger = get_logger(__name__)

GOPLUS_API = "https://api.gopluslabs.io/api/v1/token_security"
CHAIN_IDS = {"ETH": "1", "BSC": "56"}

RUGCHECK_API = "https://api.rugcheck.xyz/v1/tokens"

async def _fetch_rugcheck_score(token_address: str) -> dict:
    """Query RugCheck API for Solana token safety data."""
    url = f"{RUGCHECK_API}/{token_address}/report"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        logger.warning("RugCheck API error: %s", e)
    return {}

def _format_rugcheck_score(data: dict) -> tuple:
    """Parse RugCheck response into readable safety metrics. Returns (text, score)."""
    if not data:
        return "⚠️ Unable to fetch security data.", 0

    risks = data.get("risks", [])
    raw_score = data.get("score", 0)  # RugCheck: higher score = higher risk
    
    # Scale score to a 0-100 range where 100 is best:
    # A score of < 500 is typically moderate/good, > 1000 is bad.
    safety_score = max(0, int(100 - (raw_score / 50)))
    
    risk_labels = []
    safe_labels = []
    
    for r in risks:
        level = r.get("level", "info")
        name = r.get("name", "Unknown")
        v = r.get("value", "")
        # Format "Name: Value" if value exists
        label_text = f"{name}: {v}" if v else name

        if level == "danger":
            risk_labels.append(f"🚨 {label_text}")
        elif level == "warning":
            risk_labels.append(f"⚠️ {label_text}")

    if not risks or len(risk_labels) == 0:
        safe_labels.append("✅ No major risks detected")
        
    # Score visual
    if safety_score >= 80:
        score_emoji = "🟢"
        score_label = "SAFE"
    elif safety_score >= 50:
        score_emoji = "🟡"
        score_label = "MODERATE"
    else:
        score_emoji = "🔴"
        score_label = "HIGH RISK"

    # Extract extra token info
    token_meta = data.get("tokenMeta") or {}
    name = token_meta.get("name", "Unknown Name")
    symbol = token_meta.get("symbol", "UNKNOWN")
    
    token_info = data.get("token") or {}
    decimals = int(token_info.get("decimals", 9))
    try:
        supply_raw = float(token_info.get("supply", 0))
        formatted_supply = supply_raw / (10 ** decimals)
    except (ValueError, TypeError):
        formatted_supply = 0.0
        
    total_lp = float(data.get("totalMarketLiquidity", 0.0) or 0.0)

    # Begin formatting
    text = f"🏷️ <b>Token:</b> {name} (${symbol})\n"
    if formatted_supply > 0:
        text += f"📦 <b>Supply:</b> {formatted_supply:,.0f}\n"
    if total_lp > 0:
        text += f"💧 <b>Liquidity:</b> ${total_lp:,.2f}\n"
    
    text += "\n"
    text += f"{score_emoji} <b>Safety Score: {safety_score}/100 ({score_label})</b>\n\n"

    if risk_labels:
        text += "<b>⚠️ Risks:</b>\n"
        for r in risk_labels:
            text += f"  {r}\n"
        text += "\n"

    if safe_labels:
        text += "<b>✅ Passed:</b>\n"
        for s in safe_labels:
            text += f"  {s}\n"
        text += "\n"
        
    return text, safety_score


async def _fetch_goplus_score(chain: str, token_address: str) -> dict:
    """Query GoPlus API for token safety data."""
    chain_id = CHAIN_IDS.get(chain, "1")
    url = f"{GOPLUS_API}/{chain_id}?contract_addresses={token_address}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                result = data.get("result") or {}
                # GoPlus returns results keyed by lowercase address
                token_data = result.get(token_address.lower(), {})
                return token_data
    except Exception as e:
        logger.warning("GoPlus API error: %s", e)
    return {}


def _format_safety_score(data: dict) -> tuple:
    """Parse GoPlus response into readable safety metrics. Returns (text, score)."""
    if not data:
        return "⚠️ Unable to fetch security data.", 0

    risks = []
    safe_checks = []
    score = 100

    # Check critical risks
    if data.get("is_honeypot") == "1":
        risks.append("🚨 HONEYPOT DETECTED")
        score -= 50

    if data.get("is_open_source") == "0":
        risks.append("⚠️ Contract NOT open source")
        score -= 15

    if data.get("is_proxy") == "1":
        risks.append("⚠️ Proxy contract (upgradeable)")
        score -= 10

    if data.get("is_mintable") == "1":
        risks.append("⚠️ Mintable (owner can create tokens)")
        score -= 15

    if data.get("can_take_back_ownership") == "1":
        risks.append("⚠️ Can reclaim ownership")
        score -= 10

    if data.get("owner_change_balance") == "1":
        risks.append("🚨 Owner can modify balances")
        score -= 20

    if data.get("hidden_owner") == "1":
        risks.append("⚠️ Hidden owner")
        score -= 10

    if data.get("selfdestruct") == "1":
        risks.append("🚨 Self-destruct function")
        score -= 20

    if data.get("external_call") == "1":
        risks.append("⚠️ External calls in contract")
        score -= 5

    # Safe checks
    if data.get("is_open_source") == "1":
        safe_checks.append("✅ Open source verified")

    if data.get("is_honeypot") == "0":
        safe_checks.append("✅ Not a honeypot")

    if data.get("is_mintable") == "0":
        safe_checks.append("✅ Not mintable")

    if data.get("can_take_back_ownership") == "0":
        safe_checks.append("✅ Ownership secure")

    # Holders info
    holder_count = data.get("holder_count", "?")
    lp_holders = data.get("lp_holder_count", "?")

    buy_tax = data.get("buy_tax", "0")
    sell_tax = data.get("sell_tax", "0")

    try:
        buy_tax_pct = float(buy_tax) * 100
        sell_tax_pct = float(sell_tax) * 100
    except (ValueError, TypeError):
        buy_tax_pct = 0
        sell_tax_pct = 0

    if buy_tax_pct > 10:
        risks.append(f"⚠️ High buy tax: {buy_tax_pct:.1f}%")
        score -= 10
    if sell_tax_pct > 10:
        risks.append(f"⚠️ High sell tax: {sell_tax_pct:.1f}%")
        score -= 10

    score = max(0, score)

    # Score visual
    if score >= 80:
        score_emoji = "🟢"
        score_label = "SAFE"
    elif score >= 50:
        score_emoji = "🟡"
        score_label = "MODERATE"
    else:
        score_emoji = "🔴"
        score_label = "HIGH RISK"

    text = f"{score_emoji} <b>Safety Score: {score}/100 ({score_label})</b>\n\n"

    if risks:
        text += "<b>⚠️ Risks:</b>\n"
        for r in risks:
            text += f"  {r}\n"
        text += "\n"

    if safe_checks:
        text += "<b>✅ Passed:</b>\n"
        for s in safe_checks:
            text += f"  {s}\n"
        text += "\n"

    text += (
        f"📊 <b>Metrics:</b>\n"
        f"  👥 Holders: {holder_count}\n"
        f"  💧 LP Holders: {lp_holders}\n"
        f"  💸 Buy Tax: {buy_tax_pct:.1f}%\n"
        f"  💸 Sell Tax: {sell_tax_pct:.1f}%\n"
    )

    return text, score


async def token_audit_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt for token address to audit."""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "🛡️ <b>TOKEN AUDIT</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Enter a token contract address to check\n"
            "its safety score via GoPlus Security:\n",
            parse_mode="HTML",
        )
    else:
        await update.effective_chat.send_message(
            "🛡️ Enter a token contract address to audit:",
        )
    return TOKEN_AUDIT_INPUT


async def token_audit_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Fetch and display token audit results."""
    address = update.message.text.strip()
    if len(address) < 20:
        await update.effective_chat.send_message("⚠️ Invalid address. Try again:")
        return TOKEN_AUDIT_INPUT

    chain = context.user_data.get("chain", "ETH")
    await update.effective_chat.send_message("🔍 Scanning token security...")

    if chain == "SOL":
        data = await _fetch_rugcheck_score(address)
        safety_text, score = _format_rugcheck_score(data)
        source = "RugCheck API"
    else:
        data = await _fetch_goplus_score(chain, address)
        safety_text, score = _format_safety_score(data)
        source = "GoPlus Security API"

    text = (
        "🛡️ <b>TOKEN AUDIT RESULT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 <code>{address[:8]}...{address[-6:]}</code>\n"
        f"⛓️ Chain: {chain}\n\n"
        f"{safety_text}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Data from {source}</i>"
    )

    buttons = [
        [InlineKeyboardButton("🔍 Audit Another", callback_data="menu_audit")],
        [InlineKeyboardButton("◀️ Back", callback_data="menu_dashboard")],
    ]

    await update.effective_chat.send_message(
        text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML",
    )
    return TOKEN_AUDIT_RESULT
