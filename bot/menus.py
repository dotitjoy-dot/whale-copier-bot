"""
Menu state machine constants for ConversationHandler states.
Every multi-step flow uses these unique integer state identifiers.
"""

from __future__ import annotations

# ── Top-level menu states ────────────────────────────────────────────────────
MAIN_MENU = 0
DASHBOARD = 1

# ── Wallet states ────────────────────────────────────────────────────────────
WALLET_MENU = 10
WALLET_CREATE_CHAIN = 11
WALLET_CREATE_LABEL = 12
WALLET_CREATE_PASSPHRASE = 13
WALLET_IMPORT_CHAIN = 14
WALLET_IMPORT_KEY = 15
WALLET_IMPORT_LABEL = 16
WALLET_IMPORT_PASSPHRASE = 17
WALLET_EXPORT_SELECT = 18
WALLET_EXPORT_PASSPHRASE = 19
WALLET_BALANCE_SELECT = 20
WALLET_BALANCE_PASSPHRASE = 21
WALLET_REMOVE_SELECT = 22
WALLET_REMOVE_CONFIRM = 23

# ── Whale states ─────────────────────────────────────────────────────────────
WHALE_MENU = 30
WHALE_ADD_CHAIN = 31
WHALE_ADD_ADDRESS = 32
WHALE_ADD_LABEL = 33
WHALE_LIST = 34
WHALE_REMOVE_SELECT = 35
WHALE_REMOVE_CONFIRM = 36
WHALE_INSPECT_SELECT = 37

# ── Chain selection ──────────────────────────────────────────────────────────
CHAIN_SELECT = 40

# ── Copy trading ─────────────────────────────────────────────────────────────
COPY_MENU = 50
COPY_POSITIONS = 51
COPY_FORCE_CLOSE = 52

# ── Settings ─────────────────────────────────────────────────────────────────
SETTINGS_MENU = 60

# ── Money management ─────────────────────────────────────────────────────────
MONEY_MENU = 70
MONEY_MODE_SELECT = 71
MONEY_FIXED_AMOUNT = 72
MONEY_PERCENT = 73
MONEY_MULTIPLIER = 74
MONEY_MAX_POSITION = 75

# ── Risk management ──────────────────────────────────────────────────────────
RISK_MENU = 80
RISK_STOP_LOSS = 81
RISK_TAKE_PROFIT = 82
RISK_TRAILING_STOP = 83
RISK_DAILY_LIMIT = 84
RISK_MAX_SLIPPAGE = 85
RISK_CUSTOM_GAS = 86
RISK_PRIORITY_TIP = 87
RISK_AUTO_SELL = 88

# ── Trade filters ────────────────────────────────────────────────────────────
FILTERS_MENU = 89
FILTER_MIN_WHALE = 90
FILTER_MAX_AGE = 91

# ── Blacklist ────────────────────────────────────────────────────────────────
BLACKLIST_MENU = 100
BLACKLIST_ADD_ADDRESS = 101
BLACKLIST_REMOVE_SELECT = 102

# ── Alert settings ───────────────────────────────────────────────────────────
ALERTS_MENU = 110

# ── History ──────────────────────────────────────────────────────────────────
HISTORY_MENU = 120
PNL_MENU = 121
TRADE_JOURNEY = 122

# ── Admin ────────────────────────────────────────────────────────────────────
ADMIN_MENU = 130
ADMIN_BROADCAST = 131

# ── Sniper ───────────────────────────────────────────────────────────────────
SNIPER_MENU = 140
SNIPER_AMOUNT = 141
SNIPER_MIN_LIQ = 142
SNIPER_MAX_AGE = 143

# ── Partial Take Profits ────────────────────────────────────────────────────
PARTIAL_TP_MENU = 150
PARTIAL_TP_INPUT = 151

# ── Break-Even Stop Loss ────────────────────────────────────────────────────
BREAKEVEN_TRIGGER = 160

# ── Emergency Kill Switch ───────────────────────────────────────────────────
KILL_SWITCH_CONFIRM = 170

# ── DCA (Dollar Cost Averaging) ────────────────────────────────────────────
DCA_MENU = 180
DCA_TOKEN_ADDRESS = 181
DCA_AMOUNT = 182
DCA_SPLITS = 183
DCA_INTERVAL = 184

# ── Whale Leaderboard / Profitability Score ─────────────────────────────────
WHALE_LEADERBOARD = 190

# ── Price Alerts ────────────────────────────────────────────────────────────
PRICE_ALERT_MENU = 210
PRICE_ALERT_TOKEN = 211
PRICE_ALERT_PRICE = 212
PRICE_ALERT_DIRECTION = 213

# ── Anti-FOMO Cooldown ──────────────────────────────────────────────────────
COOLDOWN_SET = 220

# ── Token Audit Score ───────────────────────────────────────────────────────
TOKEN_AUDIT_INPUT = 230
TOKEN_AUDIT_RESULT = 231

# ── Trade Notes & Tags ──────────────────────────────────────────────────────
TRADE_NOTE_SELECT = 240
TRADE_NOTE_INPUT = 241
TRADE_TAG_SEARCH = 242

# ── Limit Order Simulation ──────────────────────────────────────────────────
LIMIT_ORDER_MENU = 250
LIMIT_ORDER_TOKEN = 251
LIMIT_ORDER_PRICE = 252
LIMIT_ORDER_AMOUNT = 253

# ── Portfolio Heatmap ───────────────────────────────────────────────────────
PORTFOLIO_MENU = 260

# ── Multi-Wallet Rotation ───────────────────────────────────────────────────
WALLET_ROTATION_MENU = 270

# ── Snooze Mode ─────────────────────────────────────────────────────────────
SNOOZE_SET = 280

# ── Auth / Passphrase ────────────────────────────────────────────────────────
AUTH_PASSPHRASE = 200
AUTH_CONFIRM = 201

# ── Account / License Key ────────────────────────────────────────────────────
ACCOUNT_MENU = 300
ACCOUNT_LICENSE_KEY = 301

