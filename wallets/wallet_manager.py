"""
HD Wallet Manager — creates, imports, exports, and manages EVM + Solana wallets.
Private keys are ALWAYS stored AES-256-GCM encrypted. They are decrypted only
in memory for the duration of a single operation, then garbage collected.
Mnemonics are encrypted and stored alongside private keys for export/recovery.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

import httpx
from eth_account import Account
from mnemonic import Mnemonic

from core.database import Database
from core.encryption import encrypt_private_key, decrypt_private_key
from core.logger import get_logger
from config.constants import CHAIN_INFO, DEXSCREENER_TOKEN_URL

logger = get_logger(__name__)

# Enable eth-account HD derivation
Account.enable_unaudited_hdwallet_features()


def _truncate_address(address: str) -> str:
    """Return a masked address like 0x1234...5678."""
    if len(address) > 10:
        return f"{address[:6]}...{address[-4:]}"
    return address


# ─────────────────────────────────────────────────────────────────────────────
# EVM Wallets
# ─────────────────────────────────────────────────────────────────────────────


async def create_evm_wallet(
    db: Database,
    telegram_id: int,
    chain: str,
    label: str,
    passphrase: str,
) -> Dict:
    """
    Generate a BIP-39 mnemonic, derive an EVM wallet (m/44'/60'/0'/0/0),
    encrypt the private key, and store in the database.

    Args:
        db: Database instance.
        telegram_id: Owner's Telegram user ID.
        chain: 'ETH' or 'BSC'.
        label: Human-readable wallet label.
        passphrase: User passphrase for AES-256-GCM encryption.

    Returns:
        Dict with 'address', 'mnemonic' (shown once only), 'wallet_id'.
    """
    if not passphrase:
        raise ValueError("Passphrase cannot be empty")

    # Generate 12-word BIP-39 mnemonic (128 bits of entropy)
    mnemo = Mnemonic("english")
    mnemonic_str = mnemo.generate(strength=128)

    # Derive using eth-account's built-in HD support
    account = Account.from_mnemonic(mnemonic_str, account_path="m/44'/60'/0'/0/0")
    address = account.address
    private_key_hex = account.key.hex()

    # Encrypt private key and mnemonic — NEVER store plaintext
    encrypted_pk = encrypt_private_key(private_key_hex, passphrase)
    encrypted_mnemonic = encrypt_private_key(mnemonic_str, passphrase)

    # Store in database
    wallet_id = await db.add_wallet(telegram_id, chain, address, encrypted_pk, label, encrypted_mnemonic)

    logger.info("Created EVM wallet %s for user %d on %s", _truncate_address(address), telegram_id, chain)

    return {
        "wallet_id": wallet_id,
        "address": address,
        "chain": chain,
        "label": label,
        "mnemonic": mnemonic_str,  # Caller must show once and discard
    }


async def create_solana_wallet(
    db: Database,
    telegram_id: int,
    label: str,
    passphrase: str,
) -> Dict:
    """
    Generate a BIP-39 mnemonic, derive a Solana keypair (ed25519, m/44'/501'/0'/0'),
    encrypt the secret key, and store in the database.

    Args:
        db: Database instance.
        telegram_id: Owner's Telegram user ID.
        label: Human-readable wallet label.
        passphrase: User passphrase for encryption.

    Returns:
        Dict with 'address' (base58 pubkey), 'mnemonic', 'wallet_id'.
    """
    if not passphrase:
        raise ValueError("Passphrase cannot be empty")

    from solders.keypair import Keypair  # type: ignore
    import hashlib
    import hmac as py_hmac

    # Generate 12-word mnemonic (128 bits)
    mnemo = Mnemonic("english")
    mnemonic_str = mnemo.generate(strength=128)

    # Derive seed from mnemonic (BIP-39, no passphrase extension)
    seed = mnemo.to_seed(mnemonic_str, passphrase="")

    # Derive ed25519 keypair using SLIP-10 (m/44'/501'/0'/0')
    # Manual SLIP-10 derivation for ed25519
    def _derive_slip10(seed: bytes, path: str) -> bytes:
        """Derive an ed25519 private key from seed using SLIP-10."""
        CURVE = b"ed25519 seed"
        key = py_hmac.new(CURVE, seed, hashlib.sha512).digest()
        sk, chain = key[:32], key[32:]
        segments = [int(s.replace("'", "")) + (0x80000000 if "'" in s else 0)
                    for s in path.split("/")[1:]]
        for index in segments:
            data = b"\x00" + sk + index.to_bytes(4, "big")
            key = py_hmac.new(chain, data, hashlib.sha512).digest()
            sk, chain = key[:32], key[32:]
        return sk

    secret_key_bytes = _derive_slip10(seed[:64], "m/44'/501'/0'/0'")
    keypair = Keypair.from_seed(secret_key_bytes)
    address = str(keypair.pubkey())

    # Encrypt the 32-byte seed (hex-encoded) and mnemonic
    encrypted_pk = encrypt_private_key(secret_key_bytes.hex(), passphrase)
    encrypted_mnemonic = encrypt_private_key(mnemonic_str, passphrase)

    wallet_id = await db.add_wallet(telegram_id, "SOL", address, encrypted_pk, label, encrypted_mnemonic)

    logger.info("Created Solana wallet %s for user %d", _truncate_address(address), telegram_id)

    return {
        "wallet_id": wallet_id,
        "address": address,
        "chain": "SOL",
        "label": label,
        "mnemonic": mnemonic_str,
    }


async def import_evm_wallet(
    db: Database,
    telegram_id: int,
    chain: str,
    label: str,
    private_key_hex: str,
    passphrase: str,
) -> Dict:
    """
    Import an existing EVM wallet by its private key hex string.

    Args:
        db: Database instance.
        telegram_id: Owner's Telegram user ID.
        chain: 'ETH' or 'BSC'.
        label: Human-readable wallet label.
        private_key_hex: Raw or 0x-prefixed hex private key.
        passphrase: User passphrase for encryption.

    Returns:
        Dict with 'address', 'wallet_id'.

    Raises:
        ValueError: If the private key is invalid format.
    """
    if not passphrase:
        raise ValueError("Passphrase cannot be empty")

    # Normalize to 0x-prefixed
    pk = private_key_hex.strip()
    if not pk.startswith("0x"):
        pk = "0x" + pk

    try:
        account = Account.from_key(pk)
    except Exception as exc:
        raise ValueError(f"Invalid EVM private key: {exc}") from exc

    address = account.address
    encrypted_pk = encrypt_private_key(pk, passphrase)
    wallet_id = await db.add_wallet(telegram_id, chain, address, encrypted_pk, label)

    logger.info("Imported EVM wallet %s for user %d on %s", _truncate_address(address), telegram_id, chain)
    return {"wallet_id": wallet_id, "address": address, "chain": chain, "label": label}


async def import_solana_wallet(
    db: Database,
    telegram_id: int,
    label: str,
    private_key_base58: str,
    passphrase: str,
) -> Dict:
    """
    Import an existing Solana wallet by its base58 encoded private key.

    Args:
        db: Database instance.
        telegram_id: Owner's Telegram user ID.
        label: Human-readable wallet label.
        private_key_base58: Base58-encoded 64-byte keypair secret.
        passphrase: User passphrase for encryption.

    Returns:
        Dict with 'address', 'wallet_id'.
    """
    if not passphrase:
        raise ValueError("Passphrase cannot be empty")

    from solders.keypair import Keypair  # type: ignore
    import base58

    try:
        secret_bytes = base58.b58decode(private_key_base58.strip())
        if len(secret_bytes) == 64:
            keypair = Keypair.from_bytes(secret_bytes)
        elif len(secret_bytes) == 32:
            keypair = Keypair.from_seed(secret_bytes)
        else:
            raise ValueError(f"Expected 32 or 64 bytes, got {len(secret_bytes)}")
    except Exception as exc:
        raise ValueError(f"Invalid Solana private key: {exc}") from exc

    address = str(keypair.pubkey())
    encrypted_pk = encrypt_private_key(secret_bytes.hex(), passphrase)
    wallet_id = await db.add_wallet(telegram_id, "SOL", address, encrypted_pk, label)

    logger.info("Imported Solana wallet %s for user %d", _truncate_address(address), telegram_id)
    return {"wallet_id": wallet_id, "address": address, "chain": "SOL", "label": label}


async def get_decrypted_private_key(
    db: Database, wallet_id: int, passphrase: str
) -> str:
    """
    Decrypt and return the private key for a wallet.
    NEVER logs the private key.

    Args:
        db: Database instance.
        wallet_id: Wallet database row ID.
        passphrase: User passphrase for decryption.

    Returns:
        Decrypted private key string.

    Raises:
        ValueError: If wallet not found or wrong passphrase.
    """
    wallet = await db.get_wallet(wallet_id)
    if not wallet:
        raise ValueError(f"Wallet {wallet_id} not found")
    # This will raise ValueError on wrong passphrase
    return decrypt_private_key(wallet["encrypted_pk"], passphrase)


async def get_wallet_balance(
    db: Database, wallet_id: int, passphrase: str
) -> Dict:
    """
    Fetch native balance + top ERC-20/SPL token balances for a wallet.

    Args:
        db: Database instance.
        wallet_id: Wallet database row ID.
        passphrase: Passphrase (needed to decrypt address — actually address is stored plaintext).

    Returns:
        Dict with native_balance, native_symbol, usd_value, tokens list.
    """
    wallet = await db.get_wallet(wallet_id)
    if not wallet:
        raise ValueError(f"Wallet {wallet_id} not found")

    chain = wallet["chain"]
    address = wallet["address"]

    if chain in ("ETH", "BSC"):
        from wallets.evm_wallet import EVMWallet
        evm = EVMWallet(chain, address)
        return await evm.get_balance()
    elif chain == "SOL":
        from wallets.solana_wallet import SolanaWallet
        sol = SolanaWallet(address)
        return await sol.get_balance()
    else:
        raise ValueError(f"Unsupported chain: {chain}")


async def export_wallet_full(
    db: Database, wallet_id: int, passphrase: str
) -> Dict:
    """
    Export wallet with decrypted recovery phrase and private key in
    formats compatible with all hot/cold wallets (MetaMask, Phantom,
    Trust Wallet, Ledger, etc.).

    Args:
        db: Database instance.
        wallet_id: Wallet to export.
        passphrase: Passphrase to decrypt secrets.

    Returns:
        Dict with chain, address, label, private_key, mnemonic,
        and wallet-compatible format hints.
    """
    wallet = await db.get_wallet(wallet_id)
    if not wallet:
        raise ValueError(f"Wallet {wallet_id} not found")

    chain = wallet["chain"]
    address = wallet["address"]
    label = wallet["label"]

    # Decrypt private key
    raw_pk = decrypt_private_key(wallet["encrypted_pk"], passphrase)

    # Decrypt mnemonic (may be empty for imported wallets)
    mnemonic = ""
    enc_mnemonic = wallet.get("encrypted_mnemonic") or ""
    if enc_mnemonic:
        try:
            mnemonic = decrypt_private_key(enc_mnemonic, passphrase)
        except Exception:
            mnemonic = ""  # Imported wallet — no mnemonic stored

    # Format private key for wallet compatibility
    if chain in ("ETH", "BSC"):
        # EVM wallets expect 0x-prefixed hex
        pk_display = raw_pk if raw_pk.startswith("0x") else f"0x{raw_pk}"
        derivation_path = "m/44'/60'/0'/0/0"
        compatible_wallets = "MetaMask, Trust Wallet, Rabby, Ledger, Trezor"
    else:
        # Solana wallets expect base58-encoded key
        import base58
        pk_bytes = bytes.fromhex(raw_pk)
        if len(pk_bytes) == 32:
            # Need 64-byte format (secret + pubkey) for Phantom/Solflare
            from solders.keypair import Keypair  # type: ignore
            kp = Keypair.from_seed(pk_bytes)
            pk_display = base58.b58encode(bytes(kp)).decode()
        else:
            pk_display = base58.b58encode(pk_bytes).decode()
        derivation_path = "m/44'/501'/0'/0'"
        compatible_wallets = "Phantom, Solflare, Trust Wallet, Ledger"

    return {
        "chain": chain,
        "address": address,
        "label": label,
        "mnemonic": mnemonic,
        "private_key": pk_display,
        "derivation_path": derivation_path,
        "compatible_wallets": compatible_wallets,
    }


async def list_user_wallets(db: Database, telegram_id: int) -> List[Dict]:
    """
    Return all wallets for a user with masked (truncated) addresses.

    Args:
        db: Database instance.
        telegram_id: User's Telegram ID.

    Returns:
        List of wallet dicts with masked addresses.
    """
    wallets = await db.list_wallets(telegram_id)
    return [
        {
            "wallet_id": w["id"],
            "chain": w["chain"],
            "label": w["label"],
            "address": w["address"],
            "address_masked": _truncate_address(w["address"]),
            "created_at": w["created_at"],
        }
        for w in wallets
    ]
