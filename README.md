# Whale Copy Trading Bot 🐋

A sleek, production-ready, multi-chain Telegram Bot for decentralized copy trading. Built to be deployed as a **Public SaaS** with a fully integrated advanced authentication, subscription, and licensing system.

## 🌟 Key Features

*   **Multi-Chain Support**: Effortlessly copy trades on **Ethereum (Uniswap V2/V3)**, **BSC (PancakeSwap V2/V3)**, and **Solana (Jupiter V6 & Raydium)**.
*   **Built-in Public SaaS Authentication**: Ready to generate revenue out-of-the-box.
    *   **7-Day Free Trials**: Automatically granted to new users.
    *   **Subscription Tiers**: `FREE`, `PRO`, and `ELITE` tiers with customizable usage limits (max whales, max trades, premium features).
    *   **License Key System**: Sell license keys offline or via an external storefront. Users redeem keys directly in the bot.
*   **👑 Advanced Admin Panel**: Accessible only to the bot owner.
    *   Real-time statistics (Active users, Active subscriptions, Unredeemed keys).
    *   Generate Single or Bulk License Keys.
    *   User Management: Inspect users, manually grant/revoke subscriptions, and **Ban/Unban** malicious users.
    *   Broadcast rich HTML messages to all registered users.
*   **🛡️ Token Auditing & RugCheck**: Integrated Token Audit feature utilizing `RugCheck API` for Solana tokens (and GoPlus for EVM), saving users from malicious honeypots before they buy.
*   **Whale Tracking**: Monitor targeted wallet addresses in real-time. Automatically replicate their buy and sell behaviors.
*   **Advanced Risk & Money Management**:
    *   Trade sizing (Fixed USD, % of Balance, Mirror Multiplier).
    *   Pre-trade safety checks (Max Slippage, Duplicate trades, Daily Loss Limits).
    *   Live monitoring of Stop-Loss (SL), Take-Profit (TP), and Trailing Stops.

---

## 🛠️ Tech Stack & Requirements

*   **Python 3.10+**
*   **Telegram Bot Token** (Get one from [@BotFather](https://t.me/botfather))
*   **Free Public APIs**: Uses free RPCs, CoinGecko, DexScreener, RugCheck (Solana), and GoPlus (EVM). No paid API keys required.
*   **Database**: Async SQLite (No complex database server setup needed).

---

## 🚀 Quickstart Installation (Local)

1. **Clone the Repository** and navigate to the directory:
   ```bash
   git clone <your_repo_url>
   cd "whale_copy_bot"
   ```

2. **Create a Virtual Environment** and install dependencies:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Mac/Linux:
   source .venv/bin/activate
   
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Copy the example file and edit it:
   ```bash
   cp .env.example .env
   ```
   **Crucial changes in `.env`:**
   *   `TELEGRAM_BOT_TOKEN`: Your API token from BotFather.
   *   `ADMIN_TELEGRAM_ID`: **Very Important**. Put YOUR Telegram User ID here. This grants you access to the Admin Panel and bypasses all subscription locks. Find it via an ID bot.
   *   `ENCRYPTION_SECRET`: Run `python -c "import secrets; print(secrets.token_hex(32))"` and paste the result here. Remember to ALWAYS back this up.

4. **Run the Bot**:
   ```bash
   python main.py
   ```

---

## ☁️ Deployment on Render (Free 24/7 Hosting)

Render provides a great platform for hosting Telegram bots with free CPU tiers. Since this bot uses a Webhook approach to keep the container alive, here is how to deploy it:

1. **Push to GitHub**: Make sure your entire project (except the `.venv` folder, `.env` file, and `data/` folder) is pushed to a private GitHub repository.
2. **Create a Web Service**: 
   * Go to [Render Dashboard](https://dashboard.render.com/).
   * Click **New +** and select **Web Service**.
   * Connect your GitHub repository.
3. **Configure the Service**:
   * **Language**: `Python 3`
   * **Build Command**: `pip install -r requirements.txt`
   * **Start Command**: `python main.py`
4. **Environment Variables**:
   * Scroll down to the Environment Variables section in Render.
   * Add all the keys from your local `.env` file (`TELEGRAM_BOT_TOKEN`, `ADMIN_TELEGRAM_ID`, `ENCRYPTION_SECRET`).
   * Add a new variable: `PORT` with the value `8080`.
   * Add a new variable: `RENDER_EXTERNAL_URL` with the value of your Render provided web address (e.g. `https://your-bot-name.onrender.com`).
5. **Disk (For Database Persistence)**:
   * To prevent losing your users and wallets when Render restarts the server, go to the **Disks** section.
   * Add a disk named `bot-data`, mount path: `/app/data/`, and size: `1 GB`. 
   * Update your `.env` to point `DB_PATH=/app/data/whale_copy.db`.
6. **Deploy**: Click "Create Web Service". The dashboard will show logs as it spins up and connects to Telegram!

---

## 📖 How to Use the Bot

Once the bot is running, message it on Telegram with `/start`:

1. **Free Trial**: New users immediately get a 7-day free trial limit.
2. **Passphrase Creation**: Users provide a secret passphrase. This unlocks their session and decrypts their private keys in memory.
3. **Dashboard**: Navigate seamlessly across ETH, BSC, and SOL using the top dashboard selectors.
4. **👑 Admin Panel**: If your ID matches `ADMIN_TELEGRAM_ID`, click the **Admin Panel** button unconditionally added to your dashboard to generate keys for users.
5. **Wallet Setup**: Go to `My Wallets` -> `Create Wallet` or `Import Wallet`.
6. **Start Copying**: Go to `Copy Trading` and hit `▶️ START Copy Trading`.

---

## � Security Architecture

*   **Zero-Knowledge Storage**: No database row contains raw plain-text private keys.
*   **Double Encryption**: The `ENCRYPTION_SECRET` (server-side) combined with a User's `Passphrase` (client-side memory) creates a secure encryption key for their wallet.
*   **Auto-Locking**: Memory scrubbing clears user passphrases after a configurable period of inactivity (`AUTO_LOCK_MINUTES`) or process shutdowns.
*   **Anti-Spam**: Unauthorized/banned users attempting to send commands are instantly blocked by middleware at the routing level.

---

## ⚖️ Disclaimer

*Copy trading involves significant financial risk. Meme token liquidity pools are highly volatile and subject to rugs, honeypots, and extreme slippage. This software is provided "as is" with no warranty. Use at your own risk.*
