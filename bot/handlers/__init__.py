"""
Bot handlers package — exports all handler functions.

NOTE: application.py performs its own direct imports from each handler
module. This __init__.py re-exports the most commonly used symbols for
convenience when importing from `bot.handlers` elsewhere.
"""

# Start / onboarding
from bot.handlers.start import start_command, handle_passphrase, show_dashboard

# Wallet
from bot.handlers.wallet import (
    wallet_menu, wallet_create_chain, wallet_create_chain_selected,
    wallet_create_label, wallet_create_passphrase,
    wallet_import_start, wallet_import_chain_selected,
    wallet_import_key, wallet_import_label,
    wallet_import_passphrase, wallet_balance,
    wallet_remove, wallet_remove_confirm,
    wallet_export_select, wallet_export_execute, wallet_export_passphrase,
)

# Whales
from bot.handlers.whales import (
    whale_menu, whale_add_start, whale_add_chain_selected,
    whale_add_address, whale_add_label,
    whale_remove, whale_remove_confirm, whale_inspect, whale_page,
)

# Copy trading
from bot.handlers.copy import (
    copy_menu, copy_start, copy_stop,
    copy_positions, copy_force_close, force_close_execute,
)

# Chain
from bot.handlers.chains import chain_select_callback, chain_switch_callback

# Settings hub
from bot.handlers.settings import settings_menu, filters_menu

# Money management
from bot.handlers.money_mgmt import (
    money_menu, money_toggle_paper,
    money_mode_select, money_mode_set,
    money_fixed_prompt, money_fixed_set,
    money_percent_prompt, money_percent_set,
    money_multiplier_prompt, money_multiplier_set,
    money_max_pos_prompt, money_max_pos_set,
)

# Risk management (expanded with new features)
from bot.handlers.risk_mgmt import (
    risk_menu,
    risk_toggle_mev, risk_toggle_smart_slippage, risk_toggle_breakeven,
    risk_sl_prompt, risk_sl_set,
    risk_tp_prompt, risk_tp_set,
    risk_ts_prompt, risk_ts_set,
    risk_daily_prompt, risk_daily_set,
    risk_slippage_prompt, risk_slippage_set,
    risk_custom_gas_prompt, risk_custom_gas_set,
    risk_priority_tip_prompt, risk_priority_tip_set,
    risk_auto_sell_prompt, risk_auto_sell_set,
    risk_breakeven_trigger_prompt, risk_breakeven_trigger_set,
    partial_tp_menu, partial_tp_toggle, partial_tp_default,
    partial_tp_custom_prompt, partial_tp_custom_set,
)

# Sniper
from bot.handlers.sniper import (
    sniper_menu, sniper_toggle,
    sniper_amount_prompt, sniper_amount_set,
    sniper_min_liq_prompt, sniper_min_liq_set,
    sniper_max_age_prompt, sniper_max_age_set,
)

# Blacklist
from bot.handlers.blacklist import (
    blacklist_menu, blacklist_add_prompt, blacklist_add, blacklist_remove,
)

# Alerts
from bot.handlers.alerts import alerts_menu, alert_toggle_callback

# History, PnL, Trade Journey
from bot.handlers.history import (
    history_menu, history_period, history_page, history_csv_export,
    pnl_report, share_pnl_card,
    trade_journey_prompt, trade_journey_view, trade_journey_image,
)

# Admin
from bot.handlers.admin import (
    admin_menu, admin_broadcast_prompt, admin_broadcast_send,
    admin_list_users, admin_stop_all, admin_status,
)

# ── NEW FEATURES ──────────────────────────────────────────────────────────

# Emergency Kill Switch
from bot.handlers.kill_switch import kill_switch_prompt, kill_switch_execute

# DCA (Dollar Cost Averaging)
from bot.handlers.dca import (
    dca_menu, dca_new_prompt, dca_token_set, dca_amount_set,
    dca_splits_set, dca_interval_set, dca_cancel,
)

# Whale Leaderboard
from bot.handlers.leaderboard import whale_leaderboard

# Price Alerts
from bot.handlers.price_alerts import (
    price_alert_menu, alert_new_token_prompt, alert_token_set,
    alert_price_set, alert_direction_set, alert_remove,
)

# Trade Notes & Tags
from bot.handlers.trade_notes import (
    trade_note_select, trade_note_prompt, trade_note_save,
    trade_tag_search_prompt, trade_tag_search_results,
)

# Limit Orders
from bot.handlers.limit_orders import (
    limit_order_menu, limit_new_token_prompt, limit_token_set,
    limit_price_set, limit_amount_set, limit_cancel,
)

# Portfolio Heatmap
from bot.handlers.portfolio import portfolio_menu

# Token Audit
from bot.handlers.token_audit import token_audit_prompt, token_audit_result

# Extras (Snooze, Cooldown, Wallet Rotation)
from bot.handlers.extras import (
    snooze_menu, snooze_set_preset, snooze_custom_set,
    cooldown_prompt, cooldown_set,
    wallet_rotation_menu, wallet_rotation_toggle,
)
