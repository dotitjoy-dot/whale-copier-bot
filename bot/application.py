"""
Bot application construction and handler routing.
"""

from __future__ import annotations

import asyncio
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.menus import *
from core.database import Database
from core.logger import get_logger
from core.scheduler import Scheduler
from core.auth_manager import AuthManager
from monitor.whale_tracker import WhaleTracker
from trading.copy_engine import CopyEngine
from trading.auto_sniper import AutoSniper
from trading.dca_executor import DCAExecutor
from trading.price_alert_monitor import PriceAlertMonitor
from trading.limit_order_monitor import LimitOrderMonitor

# Import handlers
from bot.handlers.start import (
    start_command, handle_passphrase, show_dashboard,
    handle_license_key_input, prompt_license_key,
    AUTH_LICENSE_KEY,
)
from bot.handlers.chains import chain_select_callback, chain_switch_callback
from bot.handlers.wallet import (
    wallet_menu, wallet_balance, wallet_create_chain, wallet_create_chain_selected,
    wallet_create_label, wallet_create_passphrase, wallet_import_start,
    wallet_import_chain_selected, wallet_import_key, wallet_import_label,
    wallet_import_passphrase, wallet_remove, wallet_remove_confirm,
    wallet_export_select, wallet_export_execute, wallet_export_passphrase,
)
from bot.handlers.whales import (
    whale_menu, whale_page, whale_add_start, whale_add_chain_selected,
    whale_add_address, whale_add_label, whale_inspect,
    whale_remove, whale_remove_confirm
)
from bot.handlers.copy import (
    copy_menu, copy_start, copy_stop, copy_positions, copy_force_close, force_close_execute
)
from bot.handlers.settings import (
    settings_menu, filters_menu, filter_toggle_buys, filter_toggle_sells,
    filter_min_whale_prompt, filter_min_whale_set, filter_toggle_anti_rug,
    filter_toggle_smart_money
)
from bot.handlers.money_mgmt import (
    money_menu, money_mode_select, money_mode_set, money_fixed_prompt, money_fixed_set,
    money_percent_prompt, money_percent_set, money_multiplier_prompt, money_multiplier_set,
    money_max_pos_prompt, money_max_pos_set, money_toggle_paper
)
from bot.handlers.risk_mgmt import (
    risk_menu, risk_sl_prompt, risk_sl_set, risk_tp_prompt, risk_tp_set,
    risk_ts_prompt, risk_ts_set, risk_daily_prompt, risk_daily_set,
    risk_slippage_prompt, risk_slippage_set, risk_toggle_mev,
    risk_toggle_smart_slippage, risk_toggle_breakeven,
    risk_breakeven_trigger_prompt, risk_breakeven_trigger_set,
    risk_custom_gas_prompt, risk_custom_gas_set,
    risk_priority_tip_prompt, risk_priority_tip_set,
    risk_auto_sell_prompt, risk_auto_sell_set,
    partial_tp_menu, partial_tp_toggle, partial_tp_default,
    partial_tp_custom_prompt, partial_tp_custom_set,
)
from bot.handlers.blacklist import (
    blacklist_menu, blacklist_add_prompt, blacklist_add, blacklist_remove
)
from bot.handlers.alerts import alerts_menu, alert_toggle_callback
from bot.handlers.history import (
    history_menu, history_page, history_period, history_csv_export, pnl_report,
    share_pnl_card, trade_journey_prompt, trade_journey_view, trade_journey_image,
)
from bot.handlers.sniper import (
    sniper_menu, sniper_toggle,
    sniper_amount_prompt, sniper_amount_set,
    sniper_min_liq_prompt, sniper_min_liq_set,
    sniper_max_age_prompt, sniper_max_age_set,
)
from bot.handlers.admin import (
    admin_menu, admin_broadcast_prompt, admin_broadcast_send, admin_list_users,
    admin_stop_all, admin_status,
    admin_keygen_menu, admin_keygen_execute, admin_key_list, admin_revoke_key,
    admin_user_list, admin_users_page, admin_inspect_user,
    admin_grant_tier, admin_grant_execute, admin_revoke_sub,
    admin_ban_user, admin_unban_user,
    ADMIN_KEY_GEN, ADMIN_KEY_LIST, ADMIN_USER_LIST,
    ADMIN_USER_INSPECT, ADMIN_GRANT_TIER,
)
# New feature handlers
from bot.handlers.kill_switch import kill_switch_prompt, kill_switch_execute
from bot.handlers.dca import (
    dca_menu, dca_new_prompt, dca_token_set, dca_amount_set,
    dca_splits_set, dca_interval_set, dca_cancel,
)
from bot.handlers.leaderboard import whale_leaderboard
from bot.handlers.price_alerts import (
    price_alert_menu, alert_new_token_prompt, alert_token_set,
    alert_price_set, alert_direction_set, alert_remove,
)
from bot.handlers.trade_notes import (
    trade_note_select, trade_note_prompt, trade_note_save,
    trade_tag_search_prompt, trade_tag_search_results,
)
from bot.handlers.limit_orders import (
    limit_order_menu, limit_new_token_prompt, limit_token_set,
    limit_price_set, limit_amount_set, limit_cancel,
)
from bot.handlers.portfolio import portfolio_menu
from bot.handlers.token_audit import token_audit_prompt, token_audit_result
from bot.handlers.extras import (
    snooze_menu, snooze_set_preset, snooze_custom_set,
    cooldown_prompt, cooldown_set,
    wallet_rotation_menu, wallet_rotation_toggle,
)

logger = get_logger(__name__)


async def post_init(app: Application) -> None:
    """Post-initialization callback — sets up DB, auth middleware, tracker, engine."""
    settings = app.bot_data["settings"]
    db = Database(settings.db_path)
    await db.initialize()
    app.bot_data["db"] = db
    logger.info("Database initialized at %s", settings.db_path)

    # Auth manager (public bot — license key / subscription based)
    auth = AuthManager(
        admin_id=settings.admin_telegram_id,
        db=db,
    )
    auth.set_auto_lock(getattr(settings, 'auto_lock_minutes', 10))
    app.bot_data["auth"] = auth

    # Restore subscriptions and license keys from DB into memory
    db_subs = await db.load_all_subscriptions()
    from bot.handlers.start import _restore_sub
    for row in db_subs:
        _restore_sub(auth, row)
    logger.info("Restored %d subscriptions from DB", len(db_subs))

    db_keys = await db.load_all_license_keys()
    from core.auth_manager import LicenseKey
    from datetime import datetime
    for row in db_keys:
        lk = LicenseKey(
            key=row["key_str"],
            tier=row["tier"],
            duration_days=row["duration_days"],
            created_by=row["created_by"],
        )
        if row.get("created_at"):
            try: lk.created_at = datetime.fromisoformat(row["created_at"])
            except: pass
        if row.get("redeemed_by"):
            lk.redeemed_by = row["redeemed_by"]
            if row.get("redeemed_at"):
                try: lk.redeemed_at = datetime.fromisoformat(row["redeemed_at"])
                except: pass
        auth._license_keys[lk.key] = lk
    logger.info("Restored %d license keys from DB", len(db_keys))

    # Event queue for whale events → copy engine
    event_queue = asyncio.Queue()
    app.bot_data["event_queue"] = event_queue

    # Whale tracker
    tracker = WhaleTracker(db, event_queue)
    await tracker.start()
    app.bot_data["whale_tracker"] = tracker

    # Notification callback
    async def notify_user(telegram_id: int, message: str) -> None:
        try:
            await app.bot.send_message(telegram_id, message, parse_mode="HTML")
        except Exception as exc:
            logger.warning("Failed to notify user %d: %s", telegram_id, exc)

    # Copy engine
    engine = CopyEngine(db, event_queue, notify_callback=notify_user)
    await engine.start()
    app.bot_data["copy_engine"] = engine

    # Auto-Sniper — polls DEX Screener for trending tokens
    sniper = AutoSniper(db, event_queue)
    await sniper.start()
    app.bot_data["auto_sniper"] = sniper
    
    # Nansen Smart Money API polling (Background task directly interacting with DB)
    from monitor.nansen import NansenSmartMoneyUpdater
    import os
    nansen_api_key = os.getenv("NANSEN_API_KEY", "")
    nansen_updater = NansenSmartMoneyUpdater(db, nansen_api_key)
    await nansen_updater.start()
    app.bot_data["nansen_updater"] = nansen_updater

    # Scheduler — whale polling every 15 seconds
    scheduler = Scheduler()
    scheduler.add_interval_job(
        func=tracker.poll,
        job_id="whale_poll",
        seconds=15,
    )
    scheduler.start()
    app.bot_data["scheduler"] = scheduler

    # DCA Executor — executes pending DCA order splits
    dca_executor = DCAExecutor(db, notify_callback=notify_user, poll_interval=30)
    await dca_executor.start()
    app.bot_data["dca_executor"] = dca_executor

    # Price Alert Monitor — checks token prices vs user alert targets
    price_monitor = PriceAlertMonitor(db, notify_callback=notify_user, poll_interval=30)
    await price_monitor.start()
    app.bot_data["price_alert_monitor"] = price_monitor

    # Limit Order Monitor — fills simulated limit orders when price hits target
    limit_monitor = LimitOrderMonitor(db, notify_callback=notify_user, poll_interval=30)
    await limit_monitor.start()
    app.bot_data["limit_order_monitor"] = limit_monitor

    logger.info("All subsystems initialized (incl. DCA, Price Alerts, Limit Orders)")


async def post_shutdown(app: Application) -> None:
    """Graceful shutdown — stop all background tasks and close DB."""
    scheduler: Scheduler = app.bot_data.get("scheduler")
    if scheduler:
        scheduler.shutdown()

    tracker: WhaleTracker = app.bot_data.get("whale_tracker")
    if tracker:
        await tracker.stop()

    engine: CopyEngine = app.bot_data.get("copy_engine")
    if engine:
        await engine.stop()

    sniper: AutoSniper = app.bot_data.get("auto_sniper")
    if sniper:
        await sniper.stop()

    dca: DCAExecutor = app.bot_data.get("dca_executor")
    if dca:
        await dca.stop()

    price_mon: PriceAlertMonitor = app.bot_data.get("price_alert_monitor")
    if price_mon:
        await price_mon.stop()

    limit_mon: LimitOrderMonitor = app.bot_data.get("limit_order_monitor")
    if limit_mon:
        await limit_mon.stop()

    db: Database = app.bot_data.get("db")
    if db:
        await db.close()

    logger.info("Shutdown complete")


def build_conversation_handler() -> ConversationHandler:
    """Build the main ConversationHandler that drives all menu navigation."""
    return ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            # Authentication
            AUTH_PASSPHRASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_passphrase)],
            AUTH_LICENSE_KEY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_license_key_input),
                CallbackQueryHandler(prompt_license_key, pattern="^redeem_key$"),
            ],

            # Main Dashboard
            DASHBOARD: [
                CallbackQueryHandler(wallet_menu, pattern="^menu_wallets$"),
                CallbackQueryHandler(whale_menu, pattern="^menu_whales$"),
                CallbackQueryHandler(copy_menu, pattern="^menu_copy$"),
                CallbackQueryHandler(settings_menu, pattern="^menu_settings$"),
                CallbackQueryHandler(history_menu, pattern="^menu_history$"),
                CallbackQueryHandler(pnl_report, pattern="^menu_pnl$"),
                CallbackQueryHandler(chain_select_callback, pattern="^menu_chain$"),
                CallbackQueryHandler(admin_menu, pattern="^admin$"),
                # New features accessible from dashboard
                CallbackQueryHandler(kill_switch_prompt, pattern="^menu_kill_switch$"),
                CallbackQueryHandler(dca_menu, pattern="^menu_dca$"),
                CallbackQueryHandler(limit_order_menu, pattern="^menu_limit_orders$"),
                CallbackQueryHandler(price_alert_menu, pattern="^menu_alerts_price$"),
                CallbackQueryHandler(token_audit_prompt, pattern="^menu_audit$"),
                CallbackQueryHandler(portfolio_menu, pattern="^menu_portfolio$"),
            ],

            # Chain Switcher
            CHAIN_SELECT: [
                CallbackQueryHandler(chain_switch_callback, pattern=r"^chain_select_"),
                CallbackQueryHandler(show_dashboard, pattern="^menu_dashboard$"),
            ],

            # Wallet Management
            WALLET_MENU: [
                CallbackQueryHandler(wallet_create_chain, pattern="^wallet_create$"),
                CallbackQueryHandler(wallet_import_start, pattern="^wallet_import$"),
                CallbackQueryHandler(wallet_balance, pattern="^wallet_balance$"),
                CallbackQueryHandler(wallet_remove, pattern="^wallet_remove$"),
                CallbackQueryHandler(wallet_export_select, pattern="^wallet_export$"),
                CallbackQueryHandler(show_dashboard, pattern="^menu_dashboard$"),
            ],
            WALLET_CREATE_CHAIN: [
                CallbackQueryHandler(wallet_create_chain_selected, pattern=r"^chain_select_"),
                CallbackQueryHandler(wallet_menu, pattern="^menu_wallets$"),
            ],
            WALLET_CREATE_LABEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, wallet_create_label)],
            WALLET_CREATE_PASSPHRASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, wallet_create_passphrase)],
            WALLET_IMPORT_CHAIN: [
                CallbackQueryHandler(wallet_import_chain_selected, pattern=r"^chain_select_"),
                CallbackQueryHandler(wallet_menu, pattern="^menu_wallets$"),
            ],
            WALLET_IMPORT_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, wallet_import_key)],
            WALLET_IMPORT_LABEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, wallet_import_label)],
            WALLET_IMPORT_PASSPHRASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, wallet_import_passphrase)],
            # Wallet Remove
            WALLET_REMOVE_SELECT: [
                CallbackQueryHandler(wallet_remove_confirm, pattern=r"^wallet_rm_\d+$"),
                CallbackQueryHandler(wallet_menu, pattern="^menu_wallets$"),
            ],
            WALLET_REMOVE_CONFIRM: [
                CallbackQueryHandler(wallet_menu, pattern="^menu_wallets$"),
            ],
            # Wallet Export
            WALLET_EXPORT_SELECT: [
                CallbackQueryHandler(wallet_export_execute, pattern=r"^wallet_exp_\d+$"),
                CallbackQueryHandler(wallet_menu, pattern="^menu_wallets$"),
            ],
            WALLET_EXPORT_PASSPHRASE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wallet_export_passphrase),
            ],

            # Whale Management
            WHALE_MENU: [
                CallbackQueryHandler(whale_add_start, pattern="^whale_add$"),
                CallbackQueryHandler(whale_remove, pattern="^whale_remove$"),
                CallbackQueryHandler(whale_inspect, pattern=r"^whale_inspect_\d+$"),
                CallbackQueryHandler(whale_remove_confirm, pattern=r"^whale_rm_\d+$"),
                CallbackQueryHandler(whale_page, pattern=r"^whale_page_\d+$"),
                CallbackQueryHandler(whale_leaderboard, pattern="^menu_leaderboard$"),
                CallbackQueryHandler(show_dashboard, pattern="^menu_dashboard$"),
            ],
            WHALE_ADD_CHAIN: [CallbackQueryHandler(whale_add_chain_selected, pattern=r"^chain_select_")],
            WHALE_ADD_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, whale_add_address)],
            WHALE_ADD_LABEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, whale_add_label)],

            # Copy Trading
            COPY_MENU: [
                CallbackQueryHandler(copy_start, pattern="^copy_start$"),
                CallbackQueryHandler(copy_stop, pattern="^copy_stop$"),
                CallbackQueryHandler(copy_positions, pattern="^copy_positions$"),
                CallbackQueryHandler(copy_force_close, pattern="^copy_force_close$"),
                CallbackQueryHandler(show_dashboard, pattern="^menu_dashboard$"),
            ],
            COPY_POSITIONS: [
                CallbackQueryHandler(copy_menu, pattern="^menu_copy$"),
                CallbackQueryHandler(show_dashboard, pattern="^menu_dashboard$"),
            ],
            COPY_FORCE_CLOSE: [
                CallbackQueryHandler(force_close_execute, pattern=r"^force_close_\d+$"),
                CallbackQueryHandler(copy_menu, pattern="^menu_copy$"),
            ],

            # Settings
            SETTINGS_MENU: [
                CallbackQueryHandler(money_menu, pattern="^settings_money$"),
                CallbackQueryHandler(risk_menu, pattern="^settings_risk$"),
                CallbackQueryHandler(filters_menu, pattern="^settings_filters$"),
                CallbackQueryHandler(blacklist_menu, pattern="^settings_blacklist$"),
                CallbackQueryHandler(alerts_menu, pattern="^settings_alerts$"),
                CallbackQueryHandler(sniper_menu, pattern="^settings_sniper$"),
                CallbackQueryHandler(snooze_menu, pattern="^settings_snooze$"),
                CallbackQueryHandler(wallet_rotation_menu, pattern="^settings_rotation$"),
                CallbackQueryHandler(show_dashboard, pattern="^menu_dashboard$"),
            ],
            FILTERS_MENU: [
                CallbackQueryHandler(filter_toggle_anti_rug, pattern="^filter_toggle_anti_rug$"),
                CallbackQueryHandler(filter_toggle_smart_money, pattern="^filter_toggle_smart_money$"),
                CallbackQueryHandler(filter_toggle_buys, pattern="^filter_toggle_buys$"),
                CallbackQueryHandler(filter_toggle_sells, pattern="^filter_toggle_sells$"),
                CallbackQueryHandler(filter_min_whale_prompt, pattern="^filter_min_whale$"),
                CallbackQueryHandler(settings_menu, pattern="^menu_settings$"),
            ],
            FILTER_MIN_WHALE: [MessageHandler(filters.TEXT & ~filters.COMMAND, filter_min_whale_set)],

            # Money Management
            MONEY_MENU: [
                CallbackQueryHandler(money_toggle_paper, pattern="^money_toggle_paper$"),
                CallbackQueryHandler(money_mode_select, pattern="^money_mode$"),
                CallbackQueryHandler(money_fixed_prompt, pattern="^money_fixed_prompt$"),
                CallbackQueryHandler(money_percent_prompt, pattern="^money_percent_prompt$"),
                CallbackQueryHandler(money_multiplier_prompt, pattern="^money_multiplier_prompt$"),
                CallbackQueryHandler(money_max_pos_prompt, pattern="^money_max_pos_prompt$"),
                CallbackQueryHandler(settings_menu, pattern="^menu_settings$"),
            ],
            MONEY_MODE_SELECT: [
                CallbackQueryHandler(money_mode_set, pattern=r"^money_set_mode_"),
                CallbackQueryHandler(money_menu, pattern="^settings_money$"),
            ],
            MONEY_FIXED_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, money_fixed_set)],
            MONEY_PERCENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, money_percent_set)],
            MONEY_MULTIPLIER: [MessageHandler(filters.TEXT & ~filters.COMMAND, money_multiplier_set)],
            MONEY_MAX_POSITION: [MessageHandler(filters.TEXT & ~filters.COMMAND, money_max_pos_set)],

            # Risk Management (expanded with all new features)
            RISK_MENU: [
                CallbackQueryHandler(risk_toggle_mev, pattern="^risk_toggle_mev$"),
                CallbackQueryHandler(risk_toggle_smart_slippage, pattern="^risk_toggle_smart_slip$"),
                CallbackQueryHandler(risk_toggle_breakeven, pattern="^risk_breakeven$"),
                CallbackQueryHandler(risk_sl_prompt, pattern="^risk_sl$"),
                CallbackQueryHandler(risk_tp_prompt, pattern="^risk_tp$"),
                CallbackQueryHandler(risk_ts_prompt, pattern="^risk_ts$"),
                CallbackQueryHandler(risk_daily_prompt, pattern="^risk_daily$"),
                CallbackQueryHandler(risk_slippage_prompt, pattern="^risk_slippage$"),
                CallbackQueryHandler(risk_custom_gas_prompt, pattern="^risk_custom_gas$"),
                CallbackQueryHandler(risk_priority_tip_prompt, pattern="^risk_priority_tip$"),
                CallbackQueryHandler(risk_auto_sell_prompt, pattern="^risk_auto_sell$"),
                CallbackQueryHandler(partial_tp_menu, pattern="^risk_partial_tp$"),
                CallbackQueryHandler(cooldown_prompt, pattern="^risk_cooldown$"),
                CallbackQueryHandler(settings_menu, pattern="^menu_settings$"),
                CallbackQueryHandler(show_dashboard, pattern="^menu_dashboard$"),
            ],
            RISK_STOP_LOSS: [MessageHandler(filters.TEXT & ~filters.COMMAND, risk_sl_set)],
            RISK_TAKE_PROFIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, risk_tp_set)],
            RISK_TRAILING_STOP: [MessageHandler(filters.TEXT & ~filters.COMMAND, risk_ts_set)],
            RISK_DAILY_LIMIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, risk_daily_set)],
            RISK_MAX_SLIPPAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, risk_slippage_set)],
            RISK_CUSTOM_GAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, risk_custom_gas_set)],
            RISK_PRIORITY_TIP: [MessageHandler(filters.TEXT & ~filters.COMMAND, risk_priority_tip_set)],
            RISK_AUTO_SELL: [MessageHandler(filters.TEXT & ~filters.COMMAND, risk_auto_sell_set)],
            BREAKEVEN_TRIGGER: [MessageHandler(filters.TEXT & ~filters.COMMAND, risk_breakeven_trigger_set)],

            # Partial Take Profits
            PARTIAL_TP_MENU: [
                CallbackQueryHandler(partial_tp_toggle, pattern="^partial_tp_toggle$"),
                CallbackQueryHandler(partial_tp_default, pattern="^partial_tp_default$"),
                CallbackQueryHandler(partial_tp_custom_prompt, pattern="^partial_tp_custom$"),
                CallbackQueryHandler(risk_menu, pattern="^settings_risk$"),
                CallbackQueryHandler(show_dashboard, pattern="^menu_dashboard$"),
            ],
            PARTIAL_TP_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, partial_tp_custom_set)],

            # Sniper Settings
            SNIPER_MENU: [
                CallbackQueryHandler(sniper_toggle, pattern="^sniper_toggle$"),
                CallbackQueryHandler(sniper_amount_prompt, pattern="^sniper_amount$"),
                CallbackQueryHandler(sniper_min_liq_prompt, pattern="^sniper_min_liq$"),
                CallbackQueryHandler(sniper_max_age_prompt, pattern="^sniper_max_age$"),
                CallbackQueryHandler(settings_menu, pattern="^menu_settings$"),
                CallbackQueryHandler(show_dashboard, pattern="^menu_dashboard$"),
            ],
            SNIPER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, sniper_amount_set)],
            SNIPER_MIN_LIQ: [MessageHandler(filters.TEXT & ~filters.COMMAND, sniper_min_liq_set)],
            SNIPER_MAX_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, sniper_max_age_set)],

            # Blacklist
            BLACKLIST_MENU: [
                CallbackQueryHandler(blacklist_add_prompt, pattern="^blacklist_add$"),
                CallbackQueryHandler(blacklist_remove, pattern=r"^blacklist_rm_\d+$"),
                CallbackQueryHandler(settings_menu, pattern="^menu_settings$"),
            ],
            BLACKLIST_ADD_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, blacklist_add)],

            # Alerts
            ALERTS_MENU: [
                CallbackQueryHandler(alert_toggle_callback, pattern=r"^alert_toggle_"),
                CallbackQueryHandler(settings_menu, pattern="^menu_settings$"),
            ],

            # History (expanded with PnL card & trade journey)
            HISTORY_MENU: [
                CallbackQueryHandler(history_period, pattern=r"^history_(today|7d|all)$"),
                CallbackQueryHandler(history_page, pattern=r"^history_page_\d+$"),
                CallbackQueryHandler(history_csv_export, pattern="^history_csv$"),
                CallbackQueryHandler(share_pnl_card, pattern="^history_pnl_card$"),
                CallbackQueryHandler(trade_journey_prompt, pattern="^history_journey$"),
                CallbackQueryHandler(trade_note_select, pattern="^menu_notes$"),
                CallbackQueryHandler(show_dashboard, pattern="^menu_dashboard$"),
            ],
            PNL_MENU: [
                CallbackQueryHandler(share_pnl_card, pattern="^history_pnl_card$"),
                CallbackQueryHandler(show_dashboard, pattern="^menu_dashboard$"),
            ],
            TRADE_JOURNEY: [
                CallbackQueryHandler(trade_journey_view, pattern=r"^journey_\d+$"),
                CallbackQueryHandler(trade_journey_image, pattern=r"^journey_img_\d+$"),
                CallbackQueryHandler(trade_journey_prompt, pattern="^history_journey$"),
                CallbackQueryHandler(history_menu, pattern="^menu_history$"),
                CallbackQueryHandler(show_dashboard, pattern="^menu_dashboard$"),
            ],

            # Admin
            ADMIN_MENU: [
                CallbackQueryHandler(admin_keygen_menu, pattern="^admin_keygen$"),
                CallbackQueryHandler(admin_key_list, pattern="^admin_keylist$"),
                CallbackQueryHandler(admin_user_list, pattern="^admin_users$"),
                CallbackQueryHandler(admin_broadcast_prompt, pattern="^admin_broadcast$"),
                CallbackQueryHandler(admin_stop_all, pattern="^admin_stop_all$"),
                CallbackQueryHandler(admin_status, pattern="^admin_status$"),
                CallbackQueryHandler(show_dashboard, pattern="^menu_dashboard$"),
            ],
            ADMIN_BROADCAST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_send),
                CallbackQueryHandler(admin_menu, pattern="^admin$"),
            ],
            ADMIN_KEY_GEN: [
                CallbackQueryHandler(admin_keygen_execute, pattern=r"^admin_key_|^admin_bulk_"),
                CallbackQueryHandler(admin_keygen_menu, pattern="^admin_keygen$"),
                CallbackQueryHandler(admin_menu, pattern="^admin$"),
            ],
            ADMIN_KEY_LIST: [
                CallbackQueryHandler(admin_revoke_key, pattern=r"^admin_revoke_key_"),
                CallbackQueryHandler(admin_menu, pattern="^admin$"),
            ],
            ADMIN_USER_LIST: [
                CallbackQueryHandler(admin_inspect_user, pattern=r"^admin_inspect_"),
                CallbackQueryHandler(admin_users_page, pattern=r"^admin_users_(prev|next)"),
                CallbackQueryHandler(admin_menu, pattern="^admin$"),
            ],
            ADMIN_USER_INSPECT: [
                CallbackQueryHandler(admin_grant_tier, pattern=r"^admin_grant_"),
                CallbackQueryHandler(admin_revoke_sub, pattern=r"^admin_revoke_sub_"),
                CallbackQueryHandler(admin_ban_user, pattern=r"^admin_ban_"),
                CallbackQueryHandler(admin_unban_user, pattern=r"^admin_unban_"),
                CallbackQueryHandler(admin_user_list, pattern="^admin_users$"),
            ],
            ADMIN_GRANT_TIER: [
                CallbackQueryHandler(admin_grant_execute, pattern=r"^admin_grantdo_"),
                CallbackQueryHandler(admin_inspect_user, pattern=r"^admin_inspect_"),
                CallbackQueryHandler(admin_user_list, pattern="^admin_users$"),
            ],

            # ── NEW FEATURE STATES ──────────────────────────────────

            # Kill Switch
            KILL_SWITCH_CONFIRM: [
                CallbackQueryHandler(kill_switch_execute, pattern="^kill_confirm$"),
                CallbackQueryHandler(show_dashboard, pattern="^menu_dashboard$"),
            ],

            # DCA
            DCA_MENU: [
                CallbackQueryHandler(dca_new_prompt, pattern="^dca_new$"),
                CallbackQueryHandler(dca_cancel, pattern=r"^dca_cancel_\d+$"),
                CallbackQueryHandler(show_dashboard, pattern="^menu_dashboard$"),
            ],
            DCA_TOKEN_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, dca_token_set)],
            DCA_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, dca_amount_set)],
            DCA_SPLITS: [MessageHandler(filters.TEXT & ~filters.COMMAND, dca_splits_set)],
            DCA_INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, dca_interval_set)],

            # Whale Leaderboard
            WHALE_LEADERBOARD: [
                CallbackQueryHandler(whale_leaderboard, pattern="^menu_leaderboard$"),
                CallbackQueryHandler(whale_menu, pattern="^menu_whales$"),
                CallbackQueryHandler(show_dashboard, pattern="^menu_dashboard$"),
            ],

            # Price Alerts
            PRICE_ALERT_MENU: [
                CallbackQueryHandler(alert_new_token_prompt, pattern="^alert_new$"),
                CallbackQueryHandler(alert_remove, pattern=r"^alert_rm_\d+$"),
                CallbackQueryHandler(show_dashboard, pattern="^menu_dashboard$"),
            ],
            PRICE_ALERT_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, alert_token_set)],
            PRICE_ALERT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, alert_price_set)],
            PRICE_ALERT_DIRECTION: [
                CallbackQueryHandler(alert_direction_set, pattern=r"^alert_dir_"),
            ],

            # Anti-FOMO Cooldown
            COOLDOWN_SET: [MessageHandler(filters.TEXT & ~filters.COMMAND, cooldown_set)],

            # Token Audit
            TOKEN_AUDIT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, token_audit_result)],
            TOKEN_AUDIT_RESULT: [
                CallbackQueryHandler(token_audit_prompt, pattern="^menu_audit$"),
                CallbackQueryHandler(show_dashboard, pattern="^menu_dashboard$"),
            ],

            # Trade Notes & Tags
            TRADE_NOTE_SELECT: [
                CallbackQueryHandler(trade_note_prompt, pattern=r"^note_trade_\d+$"),
                CallbackQueryHandler(trade_tag_search_prompt, pattern="^note_search$"),
                CallbackQueryHandler(history_menu, pattern="^menu_history$"),
                CallbackQueryHandler(show_dashboard, pattern="^menu_dashboard$"),
            ],
            TRADE_NOTE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, trade_note_save)],
            TRADE_TAG_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, trade_tag_search_results)],

            # Limit Orders
            LIMIT_ORDER_MENU: [
                CallbackQueryHandler(limit_new_token_prompt, pattern="^limit_new$"),
                CallbackQueryHandler(limit_cancel, pattern=r"^limit_cancel_\d+$"),
                CallbackQueryHandler(show_dashboard, pattern="^menu_dashboard$"),
            ],
            LIMIT_ORDER_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, limit_token_set)],
            LIMIT_ORDER_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, limit_price_set)],
            LIMIT_ORDER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, limit_amount_set)],

            # Portfolio Heatmap
            PORTFOLIO_MENU: [
                CallbackQueryHandler(portfolio_menu, pattern="^menu_portfolio$"),
                CallbackQueryHandler(show_dashboard, pattern="^menu_dashboard$"),
            ],

            # Wallet Rotation
            WALLET_ROTATION_MENU: [
                CallbackQueryHandler(wallet_rotation_toggle, pattern="^rotation_toggle$"),
                CallbackQueryHandler(settings_menu, pattern="^menu_settings$"),
            ],

            # Snooze Mode
            SNOOZE_SET: [
                CallbackQueryHandler(snooze_set_preset, pattern=r"^snooze_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, snooze_custom_set),
            ],
        },
        fallbacks=[
            CommandHandler("start", start_command),
            CallbackQueryHandler(show_dashboard, pattern="^menu_dashboard$"),
            CallbackQueryHandler(wallet_menu, pattern="^menu_wallets$"),
            CallbackQueryHandler(whale_menu, pattern="^menu_whales$"),
            CallbackQueryHandler(copy_menu, pattern="^menu_copy$"),
            CallbackQueryHandler(settings_menu, pattern="^menu_settings$"),
            CallbackQueryHandler(money_menu, pattern="^settings_money$"),
            CallbackQueryHandler(risk_menu, pattern="^settings_risk$"),
            CallbackQueryHandler(filters_menu, pattern="^settings_filters$"),
            CallbackQueryHandler(blacklist_menu, pattern="^settings_blacklist$"),
            CallbackQueryHandler(alerts_menu, pattern="^settings_alerts$"),
            CallbackQueryHandler(sniper_menu, pattern="^settings_sniper$"),
            CallbackQueryHandler(history_menu, pattern="^menu_history$"),
            CallbackQueryHandler(admin_menu, pattern="^admin$"),
            # New feature fallbacks
            CallbackQueryHandler(dca_menu, pattern="^menu_dca$"),
            CallbackQueryHandler(limit_order_menu, pattern="^menu_limit_orders$"),
            CallbackQueryHandler(price_alert_menu, pattern="^menu_alerts_price$"),
            CallbackQueryHandler(token_audit_prompt, pattern="^menu_audit$"),
            CallbackQueryHandler(portfolio_menu, pattern="^menu_portfolio$"),
            CallbackQueryHandler(trade_note_select, pattern="^menu_notes$"),
            CallbackQueryHandler(whale_leaderboard, pattern="^menu_leaderboard$"),
            CallbackQueryHandler(kill_switch_prompt, pattern="^menu_kill_switch$"),
            CallbackQueryHandler(snooze_menu, pattern="^settings_snooze$"),
            CallbackQueryHandler(wallet_rotation_menu, pattern="^settings_rotation$"),
        ],
        name="main_conversation",
        persistent=False,
    )
