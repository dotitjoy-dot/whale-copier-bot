# Whale Copy Trading Bot 🐋

A sleek, self-hosted, production-ready Telegram Bot for decentralized copy trading on Ethereum, Binance Smart Chain (BSC), and Solana.

## 🌟 Key Features

*   **Multi-Chain Support**: Effortlessly copy trades on **Ethereum (Uniswap V2/V3)**, **BSC (PancakeSwap V2/V3)**, and **Solana (Jupiter V6)**.
*   **Whale Tracking**: Monitor targeted wallet addresses (whales) in real-time. Automatically replicate their buy and sell behaviors.
*   **Military-Grade Security**: 
    *   100% self-hosted, keeping your private keys strictly on your servers.
    *   Keys are **AES-256-GCM encrypted** at rest in the database.
    *   In-memory passphrases auto-lock after inactivity.
*   **Rich Telegram GUI**: High-quality UI using Telegram inline keyboards, interactive menus, progress bars, and pagination.
*   **Advanced Risk & Money Management**:
    *   Trade sizing (Fixed USD, % of Balance, Mirror Multiplier).
    *   Pre-trade safety checks (Max Slippage, Duplicate trades, Daily Loss Limits).
    *   Live monitoring of Stop-Loss (SL), Take-Profit (TP), and Trailing Stops.
*   **Free & Open Stack**: Uses free public RPCs, CoinGecko, DexScreener, Python, and async SQLite. Absolutely no premium API dependencies required to start.

---

## 🛠️ Requirements

*   **Python 3.10+**
*   **Telegram Bot Token** (Get one from [@BotFather](https://t.me/botfather) on Telegram)
*   **Docker & Docker Compose** (Optional, but recommended for deployment)

---

## 🚀 Quickstart Installation (Local)

1. **Clone the Repository** and navigate to the directory:
   ```bash
   cd whale_copy_bot
   ```

2. **Create a Virtual Environment** and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Copy the example file and edit it:
   ```bash
   cp .env.example .env
   ```
   **Important changes in `.env`:**
   *   `TELEGRAM_BOT_TOKEN`: Your API token from BotFather.
   *   `ALLOWED_USER_IDS`: Your Telegram User ID (comma-separated). Find it via [@userinfobot](https://t.me/userinfobot).
   *   `ADMIN_TELEGRAM_ID`: Your Telegram User ID for admin privileges.
   *   `ENCRYPTION_SECRET`: Run `python -c "import secrets; print(secrets.token_hex(32))"` and paste the result here.

4. **Run the Bot**:
   ```bash
   python main.py
   ```

---

## 🐳 Deployment with Docker (Recommended)

To run the bot 24/7 on a VPS (like DigitalOcean, Hetzner, AWS) using Docker:

1. Follow step 3 above to set up your `.env` file first.
2. Build and run the container:
   ```bash
   docker-compose up -d --build
   ```
3. Check the logs to ensure successful startup:
   ```bash
   docker-compose logs -f
   ```

---

## 📖 How to Use the Bot

Once the bot is running, message it on Telegram with:
`/start`

The bot will guide you through the initial setup wizard:
1. **Passphrase Creation**: Provide a secret passphrase. This unlocks your bot session. If you lose this, you cannot access your wallets!
2. **Dashboard**: Navigate seamlessly across chains using the top dashboard selectors.
3. **Wallet Setup**: Go to `My Wallets` -> `Create Wallet` or `Import Wallet`.
4. **Add Whales**: Go to `Whale Wallets` -> `Add Whale` and paste the wallet address of a successful trader.
5. **Configure Settings**: Go to `Settings` to adjust Money Management (Trade Size) and Risk Management (Stop Loss, Take Profit, Slippage).
6. **Start Copying**: Go to `Copy Trading` and hit `▶️ START Copy Trading`.

---

## 📂 Project Structure

```bash
whale_copy_bot/
├── bot/                # Telegram UI, Handlers, Menus, & Keyboard Generation
├── chains/             # Blockchain Integration (ETH, BSC, SOL routing logic)
├── config/             # Configuration & Constants Loading (Pydantic settings)
├── core/               # Infrastructure, Encrypted DB, AES-256 Crypto, Logging
├── monitor/            # Background Tasks (Memory leak-free Whale Tracker polling)
├── trading/            # The Brain: Copy Engine, Risk Mgmt, Slippage, Size calc
├── wallets/            # Wallet Management & Private Key Management
├── main.py             # Application Entry Point
├── docker-compose.yml  # Docker environment setup
└── .env.example        # Environment variables template
```

---

## 🔒 Security Posture

*   No database row contains raw plain-text private keys.
*   Your `ENCRYPTION_SECRET` combined with a User's `Passphrase` securely limits surface attack areas.
*   Memory scrubbing clears passphrases after `AUTO_LOCK_MINUTES` or process shutdowns.
*   Unauthorized users attempting to send commands are instantly blocked.

## ⚖️ Disclaimer

*Copy trading involves significant financial risk. Meme token liquidity pools are highly volatile and subject to rugs, honeypots, and extreme slippage. This software is provided "as is" with no warranty. Use at your own risk.*
