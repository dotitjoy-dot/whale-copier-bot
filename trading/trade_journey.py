"""
Trade Journey — generates visual timeline of a trade's lifecycle.
Shows Entry → Trailing Stop Triggered → Partial Sold → Break-Even SL Set → Exit.
Produces both text-based and image-based timelines.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Dict, List

from core.logger import get_logger

logger = get_logger(__name__)

# Event type icons
EVENT_ICONS = {
    "ENTRY": "🟢",
    "BUY_EXECUTED": "🟢",
    "PRICE_UPDATE": "📊",
    "PARTIAL_SELL": "🟡",
    "BREAKEVEN_SL": "🛡️",
    "SL_MOVED": "🔻",
    "TRAILING_STOP_ACTIVE": "📉",
    "TRAILING_STOP_HIT": "📉",
    "TAKE_PROFIT_HIT": "🎯",
    "STOP_LOSS_HIT": "🔻",
    "AUTO_SELL_TIMEOUT": "⏰",
    "MANUAL_CLOSE": "🔧",
    "EXIT": "🔴",
    "SNIPER_ENTRY": "🎯",
}


def format_trade_journey_text(
    trade: Dict,
    events: List[Dict],
    token_symbol: str = "???",
) -> str:
    """
    Format a trade journey as a rich text timeline for Telegram (HTML).

    Args:
        trade: Trade dict from the database.
        events: List of trade_events dicts, chronologically ordered.
        token_symbol: Token symbol for display.

    Returns:
        HTML-formatted timeline string.
    """
    entry_price = float(trade.get("entry_price_usd", 0))
    exit_price = float(trade.get("exit_price_usd", 0))
    pnl = float(trade.get("pnl_usd", 0))
    amount = float(trade.get("amount_in_usd", 0))
    chain = trade.get("chain", "?")
    status = trade.get("status", "UNKNOWN")

    # Header
    pnl_emoji = "🟢" if pnl >= 0 else "🔴"
    lines = [
        "📋 <b>TRADE JOURNEY</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━",
        f"🪙 Token: <b>${token_symbol}</b> ({chain})",
        f"💰 Size: ${amount:,.2f}",
        f"📈 Entry: ${entry_price:.10f}",
    ]

    if exit_price > 0:
        lines.append(f"📉 Exit: ${exit_price:.10f}")
        pnl_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
        lines.append(f"{pnl_emoji} PnL: ${pnl:+,.2f} ({pnl_pct:+.1f}%)")

    lines.append("")
    lines.append("📜 <b>TIMELINE</b>")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━")

    # Timeline events
    if not events:
        # Generate basic timeline from trade data
        lines.append(f"  ┃")
        lines.append(f"  ┣━ 🟢 Entry at ${entry_price:.10f}")
        if exit_price > 0:
            lines.append(f"  ┃")
            lines.append(f"  ┗━ 🔴 Exit at ${exit_price:.10f}")
        else:
            lines.append(f"  ┃")
            lines.append(f"  ┗━ ⏳ Position still open")
    else:
        for i, event in enumerate(events):
            icon = EVENT_ICONS.get(event.get("event_type", ""), "•")
            desc = event.get("description", "")
            price = float(event.get("price_usd", 0))
            pnl_pct = float(event.get("pnl_pct", 0))
            timestamp = event.get("created_at", "")

            # Format timestamp
            try:
                dt = datetime.fromisoformat(timestamp)
                time_str = dt.strftime("%H:%M:%S")
            except (ValueError, TypeError):
                time_str = "??:??:??"

            is_last = i == len(events) - 1
            connector = "  ┗━" if is_last else "  ┣━"

            line = f"{connector} {icon} {desc}"
            if price > 0:
                line += f" (${price:.10f})"
            if pnl_pct != 0:
                line += f" [{pnl_pct:+.1f}%]"
            line += f"  <i>{time_str}</i>"

            if not is_last:
                lines.append(f"  ┃")
            lines.append(line)

    lines.append("")
    lines.append(f"📍 Status: <b>{status}</b>")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━")

    return "\n".join(lines)


def generate_trade_journey_image(
    trade: Dict,
    events: List[Dict],
    token_symbol: str = "???",
) -> io.BytesIO:
    """
    Generate a visual trade journey timeline image.

    Args:
        trade: Trade dict from the database.
        events: List of trade_events dicts.
        token_symbol: Token symbol for display.

    Returns:
        BytesIO containing the PNG image.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise

    # Dynamic height based on events
    num_events = max(len(events), 2)
    height = 200 + num_events * 65
    width = 700

    # Colors
    BG = (15, 15, 25)
    CARD_BG = (25, 28, 45)
    GREEN = (0, 220, 130)
    RED = (255, 75, 85)
    GOLD = (255, 200, 50)
    WHITE = (255, 255, 255)
    MUTED = (140, 145, 165)
    BORDER = (80, 90, 200)
    TIMELINE_LINE = (60, 65, 100)

    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    # Card background
    draw.rounded_rectangle((15, 15, width - 15, height - 15), radius=16, fill=CARD_BG, outline=BORDER, width=2)

    # Font loading
    def load_font(size, bold=False):
        fonts = [
            "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        ]
        for f in fonts:
            try:
                return ImageFont.truetype(f, size)
            except (IOError, OSError):
                continue
        return ImageFont.load_default()

    font_title = load_font(22, bold=True)
    font_medium = load_font(16)
    font_small = load_font(13)
    font_label = load_font(11)

    # Header
    y = 30
    entry_price = float(trade.get("entry_price_usd", 0))
    exit_price = float(trade.get("exit_price_usd", 0))
    pnl = float(trade.get("pnl_usd", 0))
    pnl_color = GREEN if pnl >= 0 else RED

    draw.text((35, y), f"📋 ${token_symbol} Trade Journey", font=font_title, fill=WHITE)
    draw.text((35, y + 28), f"{trade.get('chain', '?')} • Entry: ${entry_price:.10f}", font=font_small, fill=MUTED)

    if exit_price > 0:
        pnl_sign = "+" if pnl >= 0 else ""
        draw.text((width - 200, y + 5), f"{pnl_sign}${pnl:,.2f}", font=load_font(20, bold=True), fill=pnl_color)

    # Divider
    y = 85
    draw.line([(30, y), (width - 30, y)], fill=BORDER, width=1)

    # Timeline
    y_start = 105
    timeline_x = 55
    event_list = events if events else []

    # If no events, create basic ones
    if not event_list:
        event_list = [
            {"event_type": "ENTRY", "description": "Position opened", "price_usd": entry_price, "pnl_pct": 0, "created_at": trade.get("created_at", "")},
        ]
        if exit_price > 0:
            pnl_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
            event_list.append(
                {"event_type": "EXIT", "description": "Position closed", "price_usd": exit_price, "pnl_pct": pnl_pct, "created_at": trade.get("confirmed_at", "")}
            )

    for i, event in enumerate(event_list):
        y_pos = y_start + i * 60
        is_last = i == len(event_list) - 1

        # Timeline line
        if not is_last:
            draw.line([(timeline_x, y_pos + 18), (timeline_x, y_pos + 60)], fill=TIMELINE_LINE, width=2)

        # Event dot
        event_type = event.get("event_type", "")
        if event_type in ("ENTRY", "BUY_EXECUTED", "SNIPER_ENTRY"):
            dot_color = GREEN
        elif event_type in ("EXIT", "STOP_LOSS_HIT", "TRAILING_STOP_HIT"):
            dot_color = RED
        elif event_type in ("PARTIAL_SELL", "TAKE_PROFIT_HIT"):
            dot_color = GOLD
        elif event_type == "BREAKEVEN_SL":
            dot_color = (100, 180, 255)
        else:
            dot_color = MUTED

        draw.ellipse(
            (timeline_x - 8, y_pos + 4, timeline_x + 8, y_pos + 20),
            fill=dot_color,
            outline=WHITE,
            width=1,
        )

        # Event text
        icon = EVENT_ICONS.get(event_type, "•")
        desc = event.get("description", event_type)
        price = float(event.get("price_usd", 0))
        evt_pnl = float(event.get("pnl_pct", 0))

        text = f"{icon} {desc}"
        draw.text((timeline_x + 20, y_pos + 2), text, font=font_medium, fill=WHITE)

        detail = ""
        if price > 0:
            detail += f"${price:.10f}"
        if evt_pnl != 0:
            detail += f"  [{evt_pnl:+.1f}%]"

        try:
            ts = event.get("created_at", "")
            if ts:
                dt = datetime.fromisoformat(ts)
                detail += f"  {dt.strftime('%H:%M:%S')}"
        except (ValueError, TypeError):
            pass

        if detail:
            draw.text((timeline_x + 20, y_pos + 22), detail, font=font_small, fill=MUTED)

    # Footer
    y_footer = height - 45
    draw.line([(30, y_footer - 5), (width - 30, y_footer - 5)], fill=BORDER, width=1)
    draw.text((35, y_footer + 2), "🐋 Whale Copy Bot • Trade Journey", font=font_label, fill=MUTED)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG", quality=95)
    buffer.seek(0)
    buffer.name = f"journey_{token_symbol}.png"
    return buffer
