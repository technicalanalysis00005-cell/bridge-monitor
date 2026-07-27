#!/usr/bin/env python3
"""
Cross-Chain Bridge Monitor
Tracks bridge transactions across major Ethereum L2 bridges using
public block explorers and RPC endpoints. No API keys required for
basic usage.

Supported Bridges:
  - Stargate (LayerZero)
  - Across Protocol
  - Hop Protocol

Monitors bridge contract activity, pending transfers, volume stats,
and detects anomalous patterns (large transfers, unusual gas, failed txs).
"""

import json
import time
import sys
import argparse
import statistics
from datetime import datetime, timezone
from collections import defaultdict, deque
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode


# ─── Chain Configuration ─────────────────────────────────────────────
CHAINS = {
    "ethereum": {
        "chain_id": 1,
        "rpc": "https://eth.llamarpc.com",
        "explorer_api": "https://api.etherscan.io/api",
        "explorer": "https://etherscan.io",
        "native_symbol": "ETH",
    },
    "arbitrum": {
        "chain_id": 42161,
        "rpc": "https://arb1.arbitrum.io/rpc",
        "explorer_api": "https://api.arbiscan.io/api",
        "explorer": "https://arbiscan.io",
        "native_symbol": "ETH",
    },
    "optimism": {
        "chain_id": 10,
        "rpc": "https://mainnet.optimism.io",
        "explorer_api": "https://api-optimistic.etherscan.io/api",
        "explorer": "https://optimistic.etherscan.io",
        "native_symbol": "ETH",
    },
    "base": {
        "chain_id": 8453,
        "rpc": "https://mainnet.base.org",
        "explorer_api": "https://api.basescan.org/api",
        "explorer": "https://basescan.org",
        "native_symbol": "ETH",
    },
    "polygon": {
        "chain_id": 137,
        "rpc": "https://polygon-rpc.com",
        "explorer_api": "https://api.polygonscan.com/api",
        "explorer": "https://polygonscan.com",
        "native_symbol": "MATIC",
    },
    "bsc": {
        "chain_id": 56,
        "rpc": "https://bsc-dataseed1.binance.org",
        "explorer_api": "https://api.bscscan.com/api",
        "explorer": "https://bscscan.com",
        "native_symbol": "BNB",
    },
}


# ─── Bridge Contract Addresses ───────────────────────────────────────
BRIDGE_CONTRACTS = {
    "stargate": {
        "name": "Stargate (LayerZero)",
        "ethereum": {
            "stargate_router": "0x8731d54E9D02c286767d56ac03e8037C07e01e98",
        },
        "arbitrum": {
            "stargate_router": "0x53Bf833A5d6c4dda888F69c22C88C9f356a41614",
        },
        "optimism": {
            "stargate_router": "0xB0D502E938ed5f4df2E681fE6E419ff29631d62b",
        },
        "polygon": {
            "stargate_router": "0x45A01E4e04F14f7A4a6702c74187c5F6222033cd",
        },
    },
    "across": {
        "name": "Across Protocol",
        "ethereum": {
            "spoke_pool": "0x5c7BCd6E7De5423a257D81B442095A1a6ced35C5",
        },
        "arbitrum": {
            "spoke_pool": "0xe35e9842fceaCA96570B734083f4a58e8F7C5f2A",
        },
        "optimism": {
            "spoke_pool": "0x6f26Bf09B1C792e3228e5467807a900A503c0281",
        },
        "base": {
            "spoke_pool": "0x09aea4b2242abC8bb4BB78D537A67a245A7bEC64",
        },
        "polygon": {
            "spoke_pool": "0x9295ee1d8C5b022Be115A2AD3c30C72E34e7F096",
        },
    },
    "hop": {
        "name": "Hop Protocol",
        "ethereum": {
            "hop_bridge": "0xb8901acB165ed027E32754E0FFe830802919727f",
        },
        "arbitrum": {
            "hop_bridge": "0x3E4c382a13e2Dc1D4B0E3F8b0E5b1a2c1A9f6D2b",
        },
        "optimism": {
            "hop_bridge": "0xb98454270065A31d71Bf635F827E8B8C05A9f1d5",
        },
        "polygon": {
            "hop_bridge": "0x25D8039bB044dC227f741a9e381CA4cEAE2E6aE8",
        },
    },
}

# Known ERC-20 tokens for value display
KNOWN_TOKENS = {
    "0xdac17f958d2ee523a2206206994597c13d831ec7": {"symbol": "USDT", "decimals": 6},
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": {"symbol": "USDC", "decimals": 6},
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": {"symbol": "WBTC", "decimals": 8},
    "0x6b175474e89094c44da98b954eedeac495271d0f": {"symbol": "DAI", "decimals": 18},
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": {"symbol": "WETH", "decimals": 18},
    "0x514910771af9ca656af840dff83e8264ecf986ca": {"symbol": "LINK", "decimals": 18},
    "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984": {"symbol": "UNI", "decimals": 18},
}


# ─── RPC / Explorer API Layer ────────────────────────────────────────

def rpc_call(method, params, rpc_url):
    """JSON-RPC call with timeout."""
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    try:
        req = Request(rpc_url, data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json"})
        resp = urlopen(req, timeout=15)
        data = json.loads(resp.read())
        return data.get("result")
    except Exception:
        return None


def get_eth_block_number(chain):
    """Get latest block number for a chain."""
    result = rpc_call("eth_blockNumber", [], CHAINS[chain]["rpc"])
    return int(result, 16) if result else None


def get_eth_block(chain, block_num, full_tx=False):
    """Fetch block data."""
    return rpc_call(
        "eth_getBlockByNumber", [hex(block_num), full_tx],
        CHAINS[chain]["rpc"],
    )


def get_eth_logs(chain, address, from_block, to_block=None, topics=None):
    """Get event logs from a contract address."""
    params = {
        "address": address,
        "fromBlock": hex(from_block),
        "toBlock": hex(to_block) if to_block else "latest",
    }
    if topics:
        params["topics"] = topics
    return rpc_call("eth_getLogs", [params], CHAINS[chain]["rpc"])


def explorer_api(chain, **params):
    """Call Etherscan-compatible explorer API (free tier: 5 req/s)."""
    api_url = CHAINS[chain]["explorer_api"]
    # Include API key if available in env
    import os
    api_key = os.environ.get("ETHERSCAN_API_KEY", "")
    if api_key:
        params["apikey"] = api_key
    url = f"{api_url}?{urlencode(params)}"
    try:
        req = Request(url, headers={"User-Agent": "bridge-monitor/1.0"})
        resp = urlopen(req, timeout=15)
        data = json.loads(resp.read())
        if data.get("status") == "1":
            return data.get("result", [])
    except Exception:
        pass
    return None


def get_contract_txs(chain, address, start_block=0, page=1, offset=100):
    """Get recent transactions for a contract via explorer API."""
    return explorer_api(
        chain,
        module="account",
        action="txlist",
        address=address,
        startblock=start_block,
        endblock=99999999,
        page=page,
        offset=offset,
        sort="desc",
    )


def get_token_transfers(chain, address, start_block=0, page=1, offset=100):
    """Get ERC-20 token transfers involving an address."""
    return explorer_api(
        chain,
        module="account",
        action="tokentx",
        address=address,
        startblock=start_block,
        endblock=99999999,
        page=page,
        offset=offset,
        sort="desc",
    )


# ─── Bridge Activity Scanner ─────────────────────────────────────────

class BridgeScanner:
    """Scans bridge contracts for recent activity across chains."""

    def __init__(self, bridge_name, chains=None):
        self.bridge_name = bridge_name
        self.bridge_config = BRIDGE_CONTRACTS.get(bridge_name, {})
        self.bridge_label = self.bridge_config.get("name", bridge_name)
        self.chains = chains or [
            c for c in self.bridge_config if c != "name"
        ]
        # Filter to chains that exist in CHAINS config
        self.chains = [c for c in self.chains if c in CHAINS]
        self.results = defaultdict(list)
        self.stats = defaultdict(lambda: {
            "tx_count": 0,
            "total_value_eth": 0.0,
            "unique_senders": set(),
            "failed_txs": 0,
            "avg_gas": [],
        })

    def scan_chain(self, chain, blocks_back=100, delay=0.25):
        """Scan bridge contracts on a single chain."""
        chain_config = self.bridge_config.get(chain, {})
        if not chain_config:
            return []

        latest = get_eth_block_number(chain)
        if not latest:
            print(f"  [!] Cannot get block number for {chain}", file=sys.stderr)
            return []

        start_block = latest - blocks_back
        txs_found = []

        for contract_label, contract_addr in chain_config.items():
            time.sleep(delay)  # Rate limit
            txs = get_contract_txs(
                chain, contract_addr,
                start_block=start_block, offset=50,
            )
            if not txs:
                continue

            for tx in txs:
                value_eth = int(tx.get("value", "0")) / 1e18
                gas_price = int(tx.get("gasPrice", "0")) / 1e9
                is_error = tx.get("isError") == "1"

                entry = {
                    "bridge": self.bridge_name,
                    "chain": chain,
                    "contract": contract_label,
                    "contract_addr": contract_addr[:10] + "...",
                    "tx_hash": tx.get("hash", ""),
                    "from": tx.get("from", ""),
                    "to": tx.get("to", ""),
                    "value_eth": round(value_eth, 6),
                    "gas_price_gwei": round(gas_price, 2),
                    "block": int(tx.get("blockNumber", 0)),
                    "timestamp": int(tx.get("timeStamp", 0)),
                    "is_error": is_error,
                    "method": tx.get("functionName", "transfer")[:40],
                }
                txs_found.append(entry)

                # Update stats
                stat_key = f"{chain}/{contract_label}"
                s = self.stats[stat_key]
                s["tx_count"] += 1
                s["total_value_eth"] += value_eth
                s["unique_senders"].add(tx.get("from", "").lower())
                if is_error:
                    s["failed_txs"] += 1
                s["avg_gas"].append(gas_price)

        self.results[chain] = txs_found
        return txs_found

    def scan_all(self, blocks_back=100, delay=0.3):
        """Scan all configured chains."""
        all_txs = []
        for chain in self.chains:
            print(
                f"  Scanning {self.bridge_label} on {chain}...",
                file=sys.stderr,
            )
            txs = self.scan_chain(chain, blocks_back, delay)
            all_txs.extend(txs)
            time.sleep(delay)
        return all_txs

    def get_stats(self):
        """Compile stats for all chains."""
        result = {}
        for key, s in self.stats.items():
            gas_list = s["avg_gas"]
            result[key] = {
                "tx_count": s["tx_count"],
                "total_value_eth": round(s["total_value_eth"], 4),
                "unique_senders": len(s["unique_senders"]),
                "failed_txs": s["failed_txs"],
                "avg_gas_gwei": (
                    round(statistics.mean(gas_list), 2) if gas_list else 0
                ),
                "max_gas_gwei": (
                    round(max(gas_list), 2) if gas_list else 0
                ),
            }
        return result


# ─── Volume Tracker ──────────────────────────────────────────────────

class VolumeTracker:
    """Tracks bridge volume over time using token transfer data."""

    def __init__(self, bridge_name):
        self.bridge_name = bridge_name
        self.bridge_config = BRIDGE_CONTRACTS.get(bridge_name, {})
        self.volume_by_token = defaultdict(float)
        self.transfer_count = 0
        self.large_transfers = []

    def track_ethereum(self, blocks_back=200, delay=0.3):
        """Track token transfers to/from bridge contracts on Ethereum."""
        eth_config = self.bridge_config.get("ethereum", {})
        latest = get_eth_block_number("ethereum")
        if not latest:
            print("  [!] Cannot get Ethereum block number", file=sys.stderr)
            return

        start_block = latest - blocks_back
        for label, addr in eth_config.items():
            print(f"  Tracking {label} transfers...", file=sys.stderr)
            time.sleep(delay)
            transfers = get_token_transfers(
                "ethereum", addr, start_block=start_block,
            )
            if not transfers:
                continue

            for t in transfers:
                contract = t.get("contractAddress", "").lower()
                token_info = KNOWN_TOKENS.get(contract, {})
                decimals = int(
                    t.get("tokenDecimal", token_info.get("decimals", 18))
                )
                value = int(t.get("value", "0")) / (10 ** decimals)
                symbol = t.get(
                    "tokenSymbol", token_info.get("symbol", "UNKNOWN")
                )
                self.volume_by_token[symbol] += value
                self.transfer_count += 1

                # Flag large transfers
                # (>10k stablecoins, >5 ETH, >0.5 WBTC)
                if symbol in ("USDT", "USDC", "DAI"):
                    threshold = 10000
                elif symbol == "WBTC":
                    threshold = 0.5
                else:
                    threshold = 5

                if value >= threshold:
                    self.large_transfers.append({
                        "token": symbol,
                        "value": round(value, 4),
                        "from": t.get("from", "")[:10] + "...",
                        "to": t.get("to", "")[:10] + "...",
                        "tx": t.get("hash", "")[:16] + "...",
                        "block": int(t.get("blockNumber", 0)),
                    })

    def summary(self):
        """Volume summary."""
        return {
            "bridge": self.bridge_name,
            "total_transfers": self.transfer_count,
            "volume_by_token": {
                k: round(v, 4)
                for k, v in sorted(
                    self.volume_by_token.items(), key=lambda x: -x[1]
                )
            },
            "large_transfers": self.large_transfers[:10],
        }


# ─── Anomaly Detector ────────────────────────────────────────────────

class AnomalyDetector:
    """Detects unusual bridge activity patterns."""

    def __init__(self):
        self.alerts = []

    def check_transactions(self, txs, bridge_name):
        """Analyze transactions for anomalies."""
        if not txs:
            return

        values = [t["value_eth"] for t in txs if not t["is_error"]]
        if len(values) < 2:
            return

        avg_val = statistics.mean(values)
        std_val = statistics.stdev(values)
        threshold = avg_val + 3 * std_val if std_val > 0 else avg_val * 4

        for tx in txs:
            # Large transfer anomaly (>3 sigma from mean)
            if tx["value_eth"] > threshold and tx["value_eth"] > 0.01:
                self.alerts.append({
                    "type": "large_transfer",
                    "bridge": bridge_name,
                    "chain": tx["chain"],
                    "value_eth": tx["value_eth"],
                    "avg_eth": round(avg_val, 4),
                    "std_eth": round(std_val, 4),
                    "tx_hash": tx["tx_hash"][:16] + "...",
                    "block": tx["block"],
                })

            # Failed transaction
            if tx["is_error"]:
                self.alerts.append({
                    "type": "failed_tx",
                    "bridge": bridge_name,
                    "chain": tx["chain"],
                    "tx_hash": tx["tx_hash"][:16] + "...",
                    "block": tx["block"],
                })

            # High gas price (>100 Gwei)
            if tx["gas_price_gwei"] > 100:
                self.alerts.append({
                    "type": "high_gas",
                    "bridge": bridge_name,
                    "chain": tx["chain"],
                    "gas_gwei": tx["gas_price_gwei"],
                    "tx_hash": tx["tx_hash"][:16] + "...",
                    "block": tx["block"],
                })

    def report(self):
        """Get anomaly alerts."""
        return self.alerts


# ─── RPC-based Direct Log Scan ───────────────────────────────────────

class RpcLogScanner:
    """
    Scan bridge contracts via direct RPC eth_getLogs.
    Works without explorer API keys — uses only public RPC.
    Tracks deposit/withdraw events by monitoring ETH value transfers
    and ERC-20 Transfer events to bridge contracts.
    """

    ERC20_TRANSFER_TOPIC = (
        "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    )

    def __init__(self, bridge_name, chain="ethereum"):
        self.bridge_name = bridge_name
        self.chain = chain
        self.bridge_config = BRIDGE_CONTRACTS.get(bridge_name, {})
        self.chain_config = self.bridge_config.get(chain, {})
        self.bridge_label = self.bridge_config.get("name", bridge_name)
        self.erc20_transfers = []
        self.native_transfers = []

    def scan_erc20_transfers(self, blocks_back=200):
        """Scan ERC-20 Transfer events sent to bridge contracts."""
        latest = get_eth_block_number(self.chain)
        if not latest:
            print(
                f"  [!] Cannot get block number for {self.chain}",
                file=sys.stderr,
            )
            return []

        from_block = latest - blocks_back
        found = []

        for label, addr in self.chain_config.items():
            # Topic[1] = from address (indexed), Topic[2] = to (indexed)
            # We want transfers TO the bridge contract
            padded_addr = "0x" + addr.lower()[2:].zfill(64)
            topics = [self.ERC20_TRANSFER_TOPIC, None, padded_addr]

            print(
                f"  Scanning ERC-20 transfers to {label} "
                f"({addr[:10]}...) on {self.chain}...",
                file=sys.stderr,
            )

            # Split into chunks to avoid RPC limits
            chunk_size = 2000
            current = from_block
            while current <= latest:
                end = min(current + chunk_size - 1, latest)
                logs = get_eth_logs(
                    self.chain, None, current, end, topics
                )
                if logs:
                    for log in logs:
                        token_addr = log.get("address", "").lower()
                        token_info = KNOWN_TOKENS.get(token_addr, {})
                        decimals = token_info.get("decimals", 18)
                        symbol = token_info.get("symbol", "UNKNOWN")

                        # Decode value from data field
                        data = log.get("data", "0x")
                        if len(data) >= 66:
                            value_raw = int(data[:66], 16)
                        else:
                            value_raw = int(data, 16) if data != "0x" else 0
                        value = value_raw / (10 ** decimals)

                        # Decode from address from topic[1]
                        from_topic = log.get("topics", ["", ""])[1]
                        from_addr = (
                            "0x" + from_topic[-40:]
                            if len(from_topic) >= 42
                            else "unknown"
                        )

                        entry = {
                            "bridge": self.bridge_name,
                            "chain": self.chain,
                            "contract": label,
                            "token": symbol,
                            "token_addr": token_addr,
                            "from": from_addr,
                            "to": addr,
                            "value": round(value, 6),
                            "tx_hash": log.get("transactionHash", ""),
                            "block": int(log.get("blockNumber", "0x0"), 16),
                            "log_index": int(log.get("logIndex", "0x0"), 16),
                        }
                        found.append(entry)
                current = end + 1
                time.sleep(0.2)

        self.erc20_transfers = found
        return found

    def summarize(self):
        """Summarize RPC scan results."""
        by_token = defaultdict(float)
        for t in self.erc20_transfers:
            by_token[t["token"]] += t["value"]

        return {
            "bridge": self.bridge_name,
            "chain": self.chain,
            "total_erc20_transfers": len(self.erc20_transfers),
            "volume_by_token": {
                k: round(v, 4)
                for k, v in sorted(by_token.items(), key=lambda x: -x[1])
            },
            "unique_tokens": list(by_token.keys()),
            "block_range": (
                (
                    min(t["block"] for t in self.erc20_transfers),
                    max(t["block"] for t in self.erc20_transfers),
                )
                if self.erc20_transfers
                else (0, 0)
            ),
        }


# ─── Display ─────────────────────────────────────────────────────────

def print_bridge_stats(bridge_name, stats):
    """Print bridge activity stats."""
    label = BRIDGE_CONTRACTS.get(bridge_name, {}).get("name", bridge_name)
    print(f"\n{'=' * 60}")
    print(f"  {label.upper()} — Activity Summary")
    print(f"{'=' * 60}")

    if not stats:
        print("  No activity found in scanned blocks.")
        return

    total_txs = 0
    total_value = 0.0
    total_failed = 0

    for chain_contract, s in sorted(stats.items()):
        total_txs += s["tx_count"]
        total_value += s["total_value_eth"]
        total_failed += s["failed_txs"]

        print(f"\n  {chain_contract}")
        print(f"    Transactions:  {s['tx_count']}")
        print(f"    Value:         {s['total_value_eth']:.4f} ETH")
        print(f"    Unique Users:  {s['unique_senders']}")
        print(f"    Failed:        {s['failed_txs']}")
        print(f"    Avg Gas:       {s['avg_gas_gwei']:.2f} Gwei")
        print(f"    Max Gas:       {s['max_gas_gwei']:.2f} Gwei")

    print(f"\n  {'─' * 40}")
    print(f"  TOTAL: {total_txs} txs | {total_value:.4f} ETH | "
          f"{total_failed} failed")


def print_volume(vol_summary):
    """Print volume summary."""
    print(f"\n{'=' * 60}")
    print(f"  {vol_summary['bridge'].upper()} — Token Volume (Ethereum)")
    print(f"{'=' * 60}")
    print(f"  Total transfers: {vol_summary['total_transfers']}")

    if vol_summary["volume_by_token"]:
        print(f"\n  Volume by token:")
        for token, vol in vol_summary["volume_by_token"].items():
            print(f"    {token:>8}: {vol:>18,.4f}")

    if vol_summary["large_transfers"]:
        print(f"\n  Large transfers:")
        for t in vol_summary["large_transfers"]:
            print(
                f"    {t['value']:>18,.4f} {t['token']} "
                f"from {t['from']} to {t['to']}  [{t['tx']}]"
            )


def print_rpc_summary(summary):
    """Print RPC scan summary."""
    print(f"\n{'=' * 60}")
    print(
        f"  {summary['bridge'].upper()} / {summary['chain'].upper()}"
        f" — RPC Scan"
    )
    print(f"{'=' * 60}")
    print(f"  ERC-20 Transfers: {summary['total_erc20_transfers']}")
    print(f"  Block range: {summary['block_range'][0]} → "
          f"{summary['block_range'][1]}")

    if summary["volume_by_token"]:
        print(f"\n  Volume by token:")
        for token, vol in summary["volume_by_token"].items():
            print(f"    {token:>8}: {vol:>18,.4f}")

    if summary["unique_tokens"]:
        print(f"\n  Tokens seen: {', '.join(summary['unique_tokens'])}")


def print_alerts(alerts):
    """Print anomaly alerts."""
    if not alerts:
        print("\n  No anomalies detected.")
        return

    print(f"\n{'=' * 60}")
    print(f"  ANOMALY ALERTS ({len(alerts)} found)")
    print(f"{'=' * 60}")

    for a in alerts[:20]:
        if a["type"] == "large_transfer":
            print(
                f"  [LARGE] {a['bridge']}/{a['chain']}: "
                f"{a['value_eth']:.4f} ETH "
                f"(avg: {a['avg_eth']:.4f}, σ: {a['std_eth']:.4f}) "
                f"[{a['tx_hash']}]"
            )
        elif a["type"] == "failed_tx":
            print(
                f"  [FAIL]  {a['bridge']}/{a['chain']}: "
                f"Failed tx [{a['tx_hash']}]"
            )
        elif a["type"] == "high_gas":
            print(
                f"  [GAS]   {a['bridge']}/{a['chain']}: "
                f"{a['gas_gwei']:.2f} Gwei [{a['tx_hash']}]"
            )


# ─── Main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Cross-chain bridge monitor — track bridge transactions "
            "across EVM chains"
        ),
    )
    sub = parser.add_subparsers(dest="command")

    # Scan command (via explorer API)
    p_scan = sub.add_parser(
        "scan", help="Scan bridge activity via explorer API",
    )
    p_scan.add_argument(
        "--bridge", choices=list(BRIDGE_CONTRACTS.keys()),
        default="across", help="Bridge to scan (default: across)",
    )
    p_scan.add_argument(
        "--blocks", type=int, default=200,
        help="Blocks to scan back (default: 200)",
    )
    p_scan.add_argument(
        "--chain", choices=list(CHAINS.keys()),
        help="Single chain only",
    )
    p_scan.add_argument(
        "--delay", type=float, default=0.3,
        help="Delay between API calls (default: 0.3s)",
    )

    # RPC scan (no explorer API needed)
    p_rpc = sub.add_parser(
        "rpc-scan", help="Scan via direct RPC eth_getLogs (no API key)",
    )
    p_rpc.add_argument(
        "--bridge", choices=list(BRIDGE_CONTRACTS.keys()),
        default="across", help="Bridge to scan",
    )
    p_rpc.add_argument(
        "--chain", choices=list(CHAINS.keys()),
        default="ethereum", help="Chain to scan (default: ethereum)",
    )
    p_rpc.add_argument(
        "--blocks", type=int, default=500,
        help="Blocks to scan back (default: 500)",
    )

    # Multi-bridge scan
    p_all = sub.add_parser("scan-all", help="Scan all bridges")
    p_all.add_argument(
        "--blocks", type=int, default=100,
        help="Blocks to scan back (default: 100)",
    )

    # Volume tracker
    p_vol = sub.add_parser("volume", help="Track bridge token volume")
    p_vol.add_argument(
        "--bridge", choices=list(BRIDGE_CONTRACTS.keys()),
        default="across", help="Bridge to track",
    )
    p_vol.add_argument(
        "--blocks", type=int, default=200,
        help="Blocks to scan (default: 200)",
    )

    # Chains info
    sub.add_parser("chains", help="List supported chains")

    # Bridges info
    sub.add_parser("bridges", help="List supported bridges")

    # JSON output
    parser.add_argument("--json", action="store_true", help="JSON output")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "chains":
        print("\nSupported Chains:")
        print(f"  {'Chain':<12} {'ID':<8} {'Symbol':<6} {'Explorer'}")
        print(f"  {'─' * 60}")
        for name, cfg in CHAINS.items():
            print(
                f"  {name:<12} {cfg['chain_id']:<8} "
                f"{cfg['native_symbol']:<6} {cfg['explorer']}"
            )
        return

    if args.command == "bridges":
        print("\nSupported Bridges:")
        for key, cfg in BRIDGE_CONTRACTS.items():
            chains = [c for c in cfg if c != "name" and c in CHAINS]
            print(
                f"  {key:<12} {cfg['name']:<25} "
                f"chains: {', '.join(chains)}"
            )
        return

    if args.command == "scan":
        chains = [args.chain] if args.chain else None
        scanner = BridgeScanner(args.bridge, chains)
        txs = scanner.scan_all(blocks_back=args.blocks, delay=args.delay)
        stats = scanner.get_stats()

        detector = AnomalyDetector()
        detector.check_transactions(txs, args.bridge)

        if args.json:
            print(json.dumps({
                "bridge": args.bridge,
                "stats": stats,
                "transactions": txs[:50],
                "alerts": detector.report(),
            }, indent=2, default=str))
        else:
            print_bridge_stats(args.bridge, stats)
            print_alerts(detector.report())

    elif args.command == "rpc-scan":
        scanner = RpcLogScanner(args.bridge, args.chain)
        transfers = scanner.scan_erc20_transfers(blocks_back=args.blocks)
        summary = scanner.summarize()

        if args.json:
            print(json.dumps({
                "summary": summary,
                "transfers": transfers[:50],
            }, indent=2))
        else:
            print_rpc_summary(summary)
            if transfers:
                print(f"\n  Recent transfers (first 10):")
                for t in transfers[:10]:
                    print(
                        f"    {t['value']:>15,.4f} {t['token']} "
                        f"from {t['from'][:10]}... "
                        f"[{t['tx_hash'][:16]}...]"
                    )

    elif args.command == "scan-all":
        all_stats = {}
        all_alerts = []
        for bridge_name in BRIDGE_CONTRACTS:
            scanner = BridgeScanner(bridge_name)
            txs = scanner.scan_all(blocks_back=args.blocks, delay=0.4)
            all_stats[bridge_name] = scanner.get_stats()
            detector = AnomalyDetector()
            detector.check_transactions(txs, bridge_name)
            all_alerts.extend(detector.report())
            time.sleep(1)

        if args.json:
            print(json.dumps(
                {"bridges": all_stats, "alerts": all_alerts},
                indent=2, default=str,
            ))
        else:
            for bridge_name, stats in all_stats.items():
                print_bridge_stats(bridge_name, stats)
            if all_alerts:
                print_alerts(all_alerts)

    elif args.command == "volume":
        tracker = VolumeTracker(args.bridge)
        tracker.track_ethereum(blocks_back=args.blocks)
        summary = tracker.summary()
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print_volume(summary)


if __name__ == "__main__":
    main()
