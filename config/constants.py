"""
Constants: ABI fragments, DEX router addresses, program IDs, and other
chain-specific data used across the bot. All free / public resources.
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# FREE PUBLIC RPC ENDPOINTS (defaults, overridable via .env)
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_ETH_RPCS = [
    "https://eth.llamarpc.com",
    "https://rpc.ankr.com/eth",
]

DEFAULT_BSC_RPCS = [
    "https://bsc-dataseed.binance.org",
    "https://bsc-dataseed1.defibit.io",
    "https://rpc.ankr.com/bsc",
]

DEFAULT_SOL_RPCS = [
    "https://api.mainnet-beta.solana.com",
    "https://rpc.ankr.com/solana",
]

# ─────────────────────────────────────────────────────────────────────────────
# EVM DEX ROUTER ADDRESSES
# ─────────────────────────────────────────────────────────────────────────────

UNISWAP_V2_ROUTER = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
UNISWAP_V3_ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
PANCAKESWAP_V2_ROUTER = "0x10ED43C718714eb63d5aA57B78B54704E256024E"

# All known DEX routers (ETH)
ETH_DEX_ROUTERS = {
    UNISWAP_V2_ROUTER.lower(): "Uniswap V2",
    UNISWAP_V3_ROUTER.lower(): "Uniswap V3",
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": "Uniswap V3 Universal",
}

# All known DEX routers (BSC)
BSC_DEX_ROUTERS = {
    PANCAKESWAP_V2_ROUTER.lower(): "PancakeSwap V2",
    "0x13f4ea83d0bd40e75c8222255bc855a974568dd4": "PancakeSwap V3",
}

# ─────────────────────────────────────────────────────────────────────────────
# UNISWAP V2 / PANCAKESWAP V2 ROUTER ABI (minimal — swap methods only)
# ─────────────────────────────────────────────────────────────────────────────

UNISWAP_V2_ROUTER_ABI = [
    {
        "name": "swapExactETHForTokens",
        "type": "function",
        "inputs": [
            {"name": "amountOutMin", "type": "uint256"},
            {"name": "path", "type": "address[]"},
            {"name": "to", "type": "address"},
            {"name": "deadline", "type": "uint256"},
        ],
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "stateMutability": "payable",
    },
    {
        "name": "swapExactTokensForETH",
        "type": "function",
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "amountOutMin", "type": "uint256"},
            {"name": "path", "type": "address[]"},
            {"name": "to", "type": "address"},
            {"name": "deadline", "type": "uint256"},
        ],
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "stateMutability": "nonpayable",
    },
    {
        "name": "swapExactTokensForTokens",
        "type": "function",
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "amountOutMin", "type": "uint256"},
            {"name": "path", "type": "address[]"},
            {"name": "to", "type": "address"},
            {"name": "deadline", "type": "uint256"},
        ],
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "stateMutability": "nonpayable",
    },
    {
        "name": "getAmountsOut",
        "type": "function",
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "path", "type": "address[]"},
        ],
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "stateMutability": "view",
    },
    {
        "name": "WETH",
        "type": "function",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "pure",
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# ERC-20 ABI (minimal — balanceOf, approve, allowance, transfer, decimals)
# ─────────────────────────────────────────────────────────────────────────────

ERC20_ABI = [
    {
        "name": "balanceOf",
        "type": "function",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
    {
        "name": "approve",
        "type": "function",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
    },
    {
        "name": "allowance",
        "type": "function",
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
    {
        "name": "decimals",
        "type": "function",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
    },
    {
        "name": "symbol",
        "type": "function",
        "inputs": [],
        "outputs": [{"name": "", "type": "string"}],
        "stateMutability": "view",
    },
    {
        "name": "name",
        "type": "function",
        "inputs": [],
        "outputs": [{"name": "", "type": "string"}],
        "stateMutability": "view",
    },
    {
        "name": "totalSupply",
        "type": "function",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
    {
        "name": "Transfer",
        "type": "event",
        "inputs": [
            {"name": "from", "type": "address", "indexed": True},
            {"name": "to", "type": "address", "indexed": True},
            {"name": "value", "type": "uint256", "indexed": False},
        ],
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# KNOWN WETH / WBNB ADDRESSES
# ─────────────────────────────────────────────────────────────────────────────

WETH_ADDRESS = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
WBNB_ADDRESS = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"

# ─────────────────────────────────────────────────────────────────────────────
# UNISWAP V2 METHOD SIGNATURES (first 4 bytes of keccak256 of function sig)
# ─────────────────────────────────────────────────────────────────────────────

# These are the 4-byte selectors for common swap methods
SWAP_ETH_FOR_TOKENS_SIG = "0x7ff36ab5"   # swapExactETHForTokens
SWAP_TOKENS_FOR_ETH_SIG = "0x18cbafe5"   # swapExactTokensForETH
SWAP_TOKENS_SIG = "0x38ed1739"           # swapExactTokensForTokens
SWAP_ETH_FOR_EXACT_TOKENS_SIG = "0xfb3bdb41"  # swapETHForExactTokens
SWAP_EXACT_TOKENS_FOR_ETH_FOT_SIG = "0x791ac947"  # swapExactTokensForETHSupportingFeeOnTransferTokens
SWAP_EXACT_ETH_FOR_TOKENS_FOT_SIG = "0xb6f9de95"  # swapExactETHForTokensSupportingFeeOnTransferTokens

# Buy signatures (native coin in, token out)
BUY_SIGNATURES = {
    SWAP_ETH_FOR_TOKENS_SIG,
    SWAP_ETH_FOR_EXACT_TOKENS_SIG,
    SWAP_EXACT_ETH_FOR_TOKENS_FOT_SIG,
}

# Sell signatures (token in, native coin out)
SELL_SIGNATURES = {
    SWAP_TOKENS_FOR_ETH_SIG,
    SWAP_EXACT_TOKENS_FOR_ETH_FOT_SIG,
}

# ─────────────────────────────────────────────────────────────────────────────
# SOLANA PROGRAM IDs
# ─────────────────────────────────────────────────────────────────────────────

RAYDIUM_AMM_PROGRAM_ID = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
RAYDIUM_CLMM_PROGRAM_ID = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"
JUPITER_V6_PROGRAM_ID = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
ORCA_WHIRLPOOL_PROGRAM_ID = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"

SOLANA_DEX_PROGRAMS = {
    RAYDIUM_AMM_PROGRAM_ID: "Raydium AMM",
    RAYDIUM_CLMM_PROGRAM_ID: "Raydium CLMM",
    JUPITER_V6_PROGRAM_ID: "Jupiter V6",
    ORCA_WHIRLPOOL_PROGRAM_ID: "Orca Whirlpool",
}

# ─────────────────────────────────────────────────────────────────────────────
# FREE PRICE / DATA APIs
# ─────────────────────────────────────────────────────────────────────────────

DEXSCREENER_TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens/{address}"
DEXSCREENER_PAIRS_URL = "https://api.dexscreener.com/latest/dex/pairs/{chain}/{pair}"
COINGECKO_ETH_URL = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"
COINGECKO_BNB_URL = "https://api.coingecko.com/api/v3/simple/price?ids=binancecoin&vs_currencies=usd"
COINGECKO_SOL_URL = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
JUPITER_PRICE_URL = "https://api.dexscreener.com/latest/dex/tokens/{mint}"
JUPITER_QUOTE_URL = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_URL = "https://quote-api.jup.ag/v6/swap"

# ─────────────────────────────────────────────────────────────────────────────
# BOT UI CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

PROGRESS_BAR_LENGTH = 10
MAX_MESSAGE_LENGTH = 4096  # Telegram message limit
ITEMS_PER_PAGE = 5

# Chain display names and native tokens
CHAIN_INFO = {
    "ETH": {"name": "Ethereum", "native": "ETH", "emoji": "⟠", "explorer": "https://etherscan.io"},
    "BSC": {"name": "BNB Chain", "native": "BNB", "emoji": "🟡", "explorer": "https://bscscan.com"},
    "SOL": {"name": "Solana", "native": "SOL", "emoji": "◎", "explorer": "https://solscan.io"},
}

# Supported chains list
SUPPORTED_CHAINS = ["ETH", "BSC", "SOL"]

# Minimum viable trade amount in USD
MIN_TRADE_USD = 1.0

# Maximum dynamic slippage cap
MAX_SLIPPAGE_PCT = 25.0

# DEX Screener API
DEXSCREENER_TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens/{address}"

