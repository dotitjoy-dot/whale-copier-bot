"""
PnL Card Generator — creates visually appealing shareable PnL card images.
Uses Pillow to draw styled cards with gradients, stats, and branding.
"""

from __future__ import annotations

import io
import os
from datetime import datetime
from typing import Dict, Optional

from core.logger import get_logger

logger = get_logger(__name__)

# Card dimensions and styling constants
CARD_WIDTH = 800
CARD_HEIGHT = 480
PADDING = 40

# Color palette — dark premium theme
BG_DARK = (15, 15, 25)
BG_CARD = (25, 28, 45)
ACCENT_GREEN = (0, 220, 130)
ACCENT_RED = (255, 75, 85)
ACCENT_GOLD = (255, 200, 50)
TEXT_WHITE = (255, 255, 255)
TEXT_MUTED = (140, 145, 165)
TEXT_LIGHT = (200, 205, 220)
BORDER_GLOW = (80, 90, 200)


def _try_load_font(size: int):
    """Try to load a clean TrueType font, falling back to default."""
    try:
        from PIL import ImageFont
        # Try common system fonts
        for font_name in [
            "arial.ttf", "Arial.ttf", "DejaVuSans.ttf",
            "Roboto-Regular.ttf", "segoeui.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]:
            try:
                return ImageFont.truetype(font_name, size)
            except (IOError, OSError):
                continue
        return ImageFont.load_default()
    except Exception:
        from PIL import ImageFont
        return ImageFont.load_default()


def _try_load_bold_font(size: int):
    """Try to load a bold TrueType font."""
    try:
        from PIL import ImageFont
        for font_name in [
            "arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf",
            "Roboto-Bold.ttf", "segoeuib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ]:
            try:
                return ImageFont.truetype(font_name, size)
            except (IOError, OSError):
                continue
        return _try_load_font(size)
    except Exception:
        return _try_load_font(size)


def _draw_rounded_rect(draw, bbox, radius, fill, outline=None, width=1):
    """Draw a rounded rectangle."""
    x1, y1, x2, y2 = bbox
    draw.rounded_rectangle(bbox, radius=radius, fill=fill, outline=outline, width=width)


def generate_pnl_card(
    username: str,
    period: str,
    total_trades: int,
    wins: int,
    losses: int,
    total_pnl: float,
    best_trade: float,
    worst_trade: float,
    win_rate: float,
    total_gas: float = 0.0,
    chain: str = "ALL",
) -> io.BytesIO:
    """
    Generate a visually appealing PnL card image.

    Args:
        username: Telegram username or display name.
        period: Time period string (e.g., "Today", "7 Days", "All Time").
        total_trades: Total number of trades.
        wins: Number of winning trades.
        losses: Number of losing trades.
        total_pnl: Total profit/loss in USD.
        best_trade: Best single trade PnL in USD.
        worst_trade: Worst single trade PnL in USD.
        win_rate: Win rate as percentage (0-100).
        total_gas: Total gas spent in USD.
        chain: Chain name or "ALL".

    Returns:
        BytesIO object containing the PNG image.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.error("Pillow not installed. Install with: pip install Pillow")
        raise

    # Create image with dark background
    img = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), BG_DARK)
    draw = ImageDraw.Draw(img)

    # Load fonts
    font_title = _try_load_bold_font(28)
    font_large = _try_load_bold_font(42)
    font_medium = _try_load_font(20)
    font_small = _try_load_font(16)
    font_label = _try_load_font(14)

    # ── Background card with subtle border ──
    _draw_rounded_rect(
        draw,
        (20, 20, CARD_WIDTH - 20, CARD_HEIGHT - 20),
        radius=20,
        fill=BG_CARD,
        outline=BORDER_GLOW,
        width=2,
    )

    # ── Header: Logo area + Title ──
    y = 45
    draw.text((PADDING + 10, y), "🐋", font=font_large, fill=TEXT_WHITE)
    draw.text((PADDING + 60, y + 2), "WHALE COPY BOT", font=font_title, fill=TEXT_WHITE)
    draw.text((PADDING + 60, y + 34), f"@{username} • {period} • {chain}", font=font_small, fill=TEXT_MUTED)

    # ── Divider line ──
    y = 115
    draw.line([(PADDING, y), (CARD_WIDTH - PADDING, y)], fill=BORDER_GLOW, width=1)

    # ── Main PnL display ──
    y = 130
    pnl_color = ACCENT_GREEN if total_pnl >= 0 else ACCENT_RED
    pnl_sign = "+" if total_pnl >= 0 else ""
    pnl_text = f"{pnl_sign}${total_pnl:,.2f}"

    draw.text((PADDING + 10, y), "TOTAL P&L", font=font_label, fill=TEXT_MUTED)
    draw.text((PADDING + 10, y + 20), pnl_text, font=_try_load_bold_font(48), fill=pnl_color)

    # Status emoji
    if total_pnl > 0:
        status = "🚀 PROFIT"
    elif total_pnl < 0:
        status = "📉 LOSS"
    else:
        status = "⚖️ BREAK EVEN"
    draw.text((CARD_WIDTH - PADDING - 180, y + 30), status, font=font_medium, fill=pnl_color)

    # ── Stats Grid (2x3) ──
    y = 220
    grid_items = [
        ("📊 Trades", str(total_trades)),
        ("🎯 Win Rate", f"{win_rate:.1f}%"),
        ("✅ Wins", str(wins)),
        ("❌ Losses", str(losses)),
        ("🏆 Best Trade", f"${best_trade:+,.2f}" if best_trade else "$0.00"),
        ("💀 Worst Trade", f"${worst_trade:+,.2f}" if worst_trade else "$0.00"),
    ]

    col_width = (CARD_WIDTH - PADDING * 2 - 40) // 3
    for i, (label, value) in enumerate(grid_items):
        col = i % 3
        row = i // 3
        x = PADDING + 10 + col * (col_width + 15)
        item_y = y + row * 75

        # Background pill for each stat
        _draw_rounded_rect(
            draw,
            (x, item_y, x + col_width, item_y + 60),
            radius=10,
            fill=(35, 38, 58),
        )

        draw.text((x + 12, item_y + 8), label, font=font_label, fill=TEXT_MUTED)

        # Color the value based on content
        val_color = TEXT_WHITE
        if "Best" in label and best_trade and best_trade > 0:
            val_color = ACCENT_GREEN
        elif "Worst" in label and worst_trade and worst_trade < 0:
            val_color = ACCENT_RED
        elif "Win Rate" in label:
            val_color = ACCENT_GREEN if win_rate >= 50 else ACCENT_RED

        draw.text((x + 12, item_y + 28), value, font=font_medium, fill=val_color)

    # ── Gas cost if available ──
    if total_gas > 0:
        y_gas = CARD_HEIGHT - 80
        draw.text(
            (PADDING + 10, y_gas),
            f"⛽ Gas Spent: ${total_gas:.2f}",
            font=font_small,
            fill=TEXT_MUTED,
        )

    # ── Footer ──
    y_footer = CARD_HEIGHT - 55
    draw.line([(PADDING, y_footer - 5), (CARD_WIDTH - PADDING, y_footer - 5)], fill=BORDER_GLOW, width=1)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    draw.text(
        (PADDING + 10, y_footer + 2),
        f"Generated: {timestamp} • Whale Copy Bot v2.0",
        font=font_label,
        fill=TEXT_MUTED,
    )

    # ── Win/Loss indicator bar ──
    bar_y = y_footer - 30
    bar_width = CARD_WIDTH - PADDING * 2 - 20
    if total_trades > 0:
        win_width = int(bar_width * (wins / total_trades))
        loss_width = bar_width - win_width
        _draw_rounded_rect(draw, (PADDING + 10, bar_y, PADDING + 10 + win_width, bar_y + 8), radius=4, fill=ACCENT_GREEN)
        if loss_width > 0:
            _draw_rounded_rect(draw, (PADDING + 10 + win_width, bar_y, PADDING + 10 + bar_width, bar_y + 8), radius=4, fill=ACCENT_RED)

    # Save to BytesIO
    buffer = io.BytesIO()
    img.save(buffer, format="PNG", quality=95)
    buffer.seek(0)
    buffer.name = f"pnl_card_{username}_{period.replace(' ', '_').lower()}.png"

    return buffer


def generate_trade_pnl_card(
    username: str,
    token_symbol: str,
    chain: str,
    action: str,
    entry_price: float,
    exit_price: float,
    pnl_usd: float,
    pnl_pct: float,
    amount_usd: float,
    hold_time: str = "",
) -> io.BytesIO:
    """
    Generate a PnL card for a single trade (share a specific win).

    Args:
        username: Telegram username.
        token_symbol: Token ticker.
        chain: Chain name.
        action: 'BUY' or 'SELL'.
        entry_price: Entry price USD.
        exit_price: Exit price USD.
        pnl_usd: PnL in USD.
        pnl_pct: PnL as percentage.
        amount_usd: Trade size in USD.
        hold_time: How long the position was held.

    Returns:
        BytesIO object containing the PNG image.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        raise

    width, height = 600, 360
    img = Image.new("RGB", (width, height), BG_DARK)
    draw = ImageDraw.Draw(img)

    font_title = _try_load_bold_font(24)
    font_large = _try_load_bold_font(36)
    font_medium = _try_load_font(18)
    font_small = _try_load_font(14)
    font_label = _try_load_font(12)

    # Card background
    _draw_rounded_rect(draw, (15, 15, width - 15, height - 15), radius=16, fill=BG_CARD, outline=BORDER_GLOW, width=2)

    # Header
    pnl_color = ACCENT_GREEN if pnl_usd >= 0 else ACCENT_RED
    emoji = "🚀" if pnl_usd >= 0 else "📉"

    y = 30
    draw.text((35, y), f"{emoji} ${token_symbol} TRADE", font=font_title, fill=TEXT_WHITE)
    draw.text((35, y + 30), f"@{username} • {chain}", font=font_small, fill=TEXT_MUTED)

    # PnL
    y = 90
    draw.line([(30, y), (width - 30, y)], fill=BORDER_GLOW, width=1)
    y = 100
    pnl_sign = "+" if pnl_usd >= 0 else ""
    draw.text((35, y), f"{pnl_sign}${pnl_usd:,.2f}", font=font_large, fill=pnl_color)
    draw.text((35, y + 42), f"{pnl_sign}{pnl_pct:.1f}%", font=font_medium, fill=pnl_color)

    # Trade details
    y = 180
    details = [
        ("💰 Size", f"${amount_usd:,.2f}"),
        ("📈 Entry", f"${entry_price:.10f}"),
        ("📉 Exit", f"${exit_price:.10f}"),
    ]
    if hold_time:
        details.append(("⏱️ Held", hold_time))

    for i, (label, value) in enumerate(details):
        dy = y + i * 28
        draw.text((35, dy), label, font=font_small, fill=TEXT_MUTED)
        draw.text((180, dy), value, font=font_small, fill=TEXT_LIGHT)

    # Footer
    y_footer = height - 45
    draw.line([(30, y_footer - 5), (width - 30, y_footer - 5)], fill=BORDER_GLOW, width=1)
    draw.text((35, y_footer + 2), "🐋 Whale Copy Bot", font=font_label, fill=TEXT_MUTED)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG", quality=95)
    buffer.seek(0)
    buffer.name = f"trade_pnl_{token_symbol}.png"
    return buffer
