#!/usr/bin/env python3
"""
Cross-Chain Bridge Monitor
Tracks bridge transactions across major Ethereum L2 bridges:
deposits, withdrawals, fund flows, latency, and failure detection.

Uses public RPC endpoints — no API key required.
"""

import json
import time
import sys
import argparse
import statistics
from datetime import datetime, timezone
from collections import defaultdict
from urllib.request import Request, urlopen
from urllib.error import URLError

# ─── Public RPC Endpoints ────────────────────────────────────────────

RPC = {
    "ethereum": [
        "https://eth.llamarpc.com",
        "https://rpc.ankr.com/eth",
        "https://ethereum.publicnode.com",
    ],
    "arbitrum": [
        "https://arb1.arbitrum.io/rpc",
        "https://rpc.ankr.com/arbitrum",
    ],
    "optimism": [
        "https://mainnet.optimism.io",
        "https://rpc.ankr.com/optimism",
    ],
    "base": [
        "https://mainnet.base.org",
        "https://rpc.ankr.com/base",
    ],
    "polygon": [
        "https://polygon-rpc.com",
        "https://rpc.ankr.com/polygon",
    ],
}

# ─── Known Bridge Contracts ──────────────────────────────────────────

BRIDGE_CONTRACTS = {
    "optimism_portal": {
        "address": "0x4Dbd4fc535Ac27206064B68FfCf827b0A60BAB3f",
        "chain": "ethereum",
        "name": "Optimism Portal (legacy)",
        "direction": "deposit",
    },
    "optimism_portal2": {
        "address": "0x49048044D57e1C92A77f79988d21Fa8fAF74E97e",
        "chain": "ethereum",
        "name": "Optimism Portal 2",
        "direction": "deposit",
    },
    "arbitrum_inbox": {
        "address": "0x4Dbd4fc535Ac27206064B68FfCf827b0A60BAB3f",
        "chain": "ethereum",
        "name": "Arbitrum Delayed Inbox",
        "direction": "deposit",
    },
    "arbitrum_bridge": {
        "address": "0xa3A7B6F88361F48403514059F1F16C8E78d60EeC",
        "chain": "ethereum",
        "name": "Arbitrum Bridge",
        "direction": "deposit",
    },
    "base_portal": {
        "address": "0x3154Cf16ccdb4C6d922629664174b904d80F2C35",
        "chain": "ethereum",
        "name": "Base Portal",
        "direction": "deposit",
    },
    "polygon_bridge": {
        "address": "0xA0c68C638235ee32657e8f720a23ceC1bFc77C77",
        "chain": "ethereum",
        "name": "Polygon PoS Bridge",
        "direction": "deposit",
    },
    "optimism_l2_bridge": {
        "address": "0x4200000000000000000000000000000000000010",
        "chain": "optimism",
        "name": "Optimism L2 Standard Bridge",
        "direction": "withdrawal",
    },
    "base_l2_bridge": {
        "address": "0x4200000000000000000000000000000000000010",
        "chain": "base",
        "name": "Base L2 Standard Bridge",
        "direction": "withdrawal",
    },
    "arbitrum_outbox": {
        "address": "0x0B9857ae2D4A3DBe70ffEeC5fC4f4e8dAe660d88",
        "chain": "ethereum",
        "name": "Arbitrum Outbox",
        "direction": "withdrawal",
    },
}


def rpc_call(chain, method, params=None, endpoint=None):
    """Send JSON-RPC request with endpoint failover."""
    payload = {"jsonrpc": "2.0", "method": method, "params": params or [], "id": 1}
    endpoints = [endpoint] if endpoint else RPC.get(chain, [])
    for ep in endpoints:
        try:
            req = Request(ep, data=json.dumps(payload).encode(),
                          headers={"Content-Type": "application/json"})
            resp = urlopen(req, timeout=15)
            data = json.loads(resp.read())
            if "result" in data:
                return data["result"]
        except Exception:
            continue
    return None


def get_block_number(chain):
    """Get latest block number for a chain."""
    result = rpc_call(chain, "eth_blockNumber")
    return int(result, 16) if result else None


def get_block(chain, block_num, full_tx=True):
    """Fetch block with transaction data."""
    return rpc_call(chain, "eth_getBlockByNumber", [hex(block_num), full_tx])


def get_block_range(chain, start, end, delay=0.15):
    """Fetch multiple blocks with progress output."""
    blocks = []
    total = end - start + 1
    for i, num in enumerate(range(start, end + 1)):
        block = get_block(chain, num, full_tx=True)
        if block:
            blocks.append(block)
        if (i + 1) % 20 == 0 or i == total - 1:
            print(f"  [{i+1}/{total}] block {num}", file=sys.stderr)
        time.sleep(delay)
    return blocks


def wei_to_eth(wei_hex):
    """Convert hex wei to ETH float."""
    return int(wei_hex, 16) / 1e18


def wei_to_gwei(wei_hex):
    """Convert hex wei to Gwei float."""
    return int(wei_hex, 16) / 1e9


# ─── Scanning ────────────────────────────────────────────────────────

def scan_bridge_deposits(chain, start_block, end_block, delay=0.15):
    """Scan for bridge deposit transactions on L1."""
    bridge_addrs = {v["address"].lower(): v for v in BRIDGE_CONTRACTS.values()
                    if v["chain"] == chain and v["direction"] == "deposit"}

    results = []
    blocks = get_block_range(chain, start_block, end_block, delay)

    for block in blocks:
        block_num = int(block["number"], 16)
        timestamp = int(block["timestamp"], 16)
        for tx in block.get("transactions", []):
            if isinstance(tx, str):
                continue
            to_addr = (tx.get("to") or "").lower()
            if to_addr in bridge_addrs:
                bridge_info = bridge_addrs[to_addr]
                value_eth = wei_to_eth(tx.get("value", "0x0"))
                gas_price = wei_to_gwei(tx.get("gasPrice", "0x0"))
                results.append({
                    "type": "deposit",
                    "bridge": bridge_info["name"],
                    "target_chain": bridge_info["name"].split()[0].lower(),
                    "tx_hash": tx["hash"],
                    "from": tx["from"],
                    "to": to_addr,
                    "value_eth": round(value_eth, 6),
                    "gas_price_gwei": round(gas_price, 2),
                    "block": block_num,
                    "timestamp": timestamp,
                    "datetime": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
                    "input_size": len(tx.get("input", "0x")),
                })

    return results


def scan_withdrawals(chain, start_block, end_block, delay=0.15):
    """Scan for withdrawal-related transactions on L2."""
    bridge_addrs = {v["address"].lower(): v for v in BRIDGE_CONTRACTS.values()
                    if v["chain"] == chain and v["direction"] == "withdrawal"}

    results = []
    blocks = get_block_range(chain, start_block, end_block, delay)

    for block in blocks:
        block_num = int(block["number"], 16)
        timestamp = int(block["timestamp"], 16)
        for tx in block.get("transactions", []):
            if isinstance(tx, str):
                continue
            to_addr = (tx.get("to") or "").lower()
            if to_addr in bridge_addrs:
                bridge_info = bridge_addrs[to_addr]
                value_eth = wei_to_eth(tx.get("value", "0x0"))
                results.append({
                    "type": "withdrawal",
                    "bridge": bridge_info["name"],
                    "source_chain": chain,
                    "tx_hash": tx["hash"],
                    "from": tx["from"],
                    "to": to_addr,
                    "value_eth": round(value_eth, 6),
                    "block": block_num,
                    "timestamp": timestamp,
                    "datetime": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
                })

    return results


# ─── Analysis ────────────────────────────────────────────────────────

def aggregate_bridge_stats(txs):
    """Aggregate statistics from bridge transactions."""
    if not txs:
        return {"total_txs": 0, "total_eth": 0, "unique_senders": 0,
                "by_bridge": {}, "by_hour": {}, "top_senders": [],
                "gas_stats": {}, "avg_tx_value_eth": 0}

    by_bridge = defaultdict(lambda: {"count": 0, "total_eth": 0})
    by_hour = defaultdict(int)
    senders = defaultdict(int)
    total_eth = 0

    for tx in txs:
        bridge = tx["bridge"]
        by_bridge[bridge]["count"] += 1
        by_bridge[bridge]["total_eth"] += tx["value_eth"]
        total_eth += tx["value_eth"]

        hour = datetime.fromtimestamp(tx["timestamp"], timezone.utc).strftime("%Y-%m-%d %H:00")
        by_hour[hour] += 1
        senders[tx["from"].lower()] += 1

    top_senders = sorted(senders.items(), key=lambda x: x[1], reverse=True)[:10]

    gas_prices = [tx["gas_price_gwei"] for tx in txs if tx.get("gas_price_gwei", 0) > 0]
    gas_stats = {}
    if gas_prices:
        gas_stats = {
            "avg_gwei": round(statistics.mean(gas_prices), 2),
            "median_gwei": round(statistics.median(gas_prices), 2),
            "max_gwei": round(max(gas_prices), 2),
        }

    for k in by_bridge:
        by_bridge[k]["total_eth"] = round(by_bridge[k]["total_eth"], 4)

    return {
        "total_txs": len(txs),
        "total_eth": round(total_eth, 4),
        "unique_senders": len(senders),
        "by_bridge": dict(by_bridge),
        "by_hour": dict(sorted(by_hour.items())),
        "top_senders": [{"address": a[:10] + "...", "count": c} for a, c in top_senders],
        "gas_stats": gas_stats,
        "avg_tx_value_eth": round(total_eth / len(txs), 4) if txs else 0,
    }


def check_multi_chain(chains=None):
    """Get latest block from multiple chains to verify connectivity."""
    chains = chains or list(RPC.keys())
    status = {}
    for chain in chains:
        t0 = time.time()
        num = get_block_number(chain)
        latency = round((time.time() - t0) * 1000)
        status[chain] = {
            "latest_block": num,
            "connected": num is not None,
            "latency_ms": latency,
        }
    return status


# ─── Output ──────────────────────────────────────────────────────────

def print_report(stats, label="Bridge Activity"):
    """Pretty-print bridge stats."""
    print(f"\n{'='*60}")
    print(f"  {label.upper()} REPORT")
    print(f"{'='*60}")

    print(f"\nTotal transactions: {stats['total_txs']}")
    print(f"Total value: {stats['total_eth']} ETH")
    print(f"Unique senders: {stats['unique_senders']}")
    print(f"Avg tx value: {stats['avg_tx_value_eth']} ETH")

    if stats.get("by_bridge"):
        print(f"\n-- By Bridge --")
        for bridge, data in stats["by_bridge"].items():
            print(f"  {bridge}: {data['count']} txs, {data['total_eth']} ETH")

    if stats.get("by_hour"):
        print(f"\n-- Hourly Activity (last 12h) --")
        for hour, count in list(stats["by_hour"].items())[-12:]:
            bar = "#" * min(count, 50)
            print(f"  {hour} | {bar} {count}")

    if stats.get("top_senders"):
        print(f"\n-- Top Senders --")
        for s in stats["top_senders"][:5]:
            print(f"  {s['address']}: {s['count']} txs")

    if stats.get("gas_stats") and stats["gas_stats"]:
        gs = stats["gas_stats"]
        print(f"\n-- Gas (Deposits) --")
        print(f"  Avg: {gs['avg_gwei']} Gwei")
        print(f"  Median: {gs['median_gwei']} Gwei")
        print(f"  Max: {gs['max_gwei']} Gwei")

    print(f"\n{'='*60}\n")


# ─── CLI ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Cross-Chain Bridge Monitor -- deposits, withdrawals, fund flows")
    sub = parser.add_subparsers(dest="command")

    # status
    p_status = sub.add_parser("status", help="Check chain connectivity")
    p_status.add_argument("--chains", nargs="+", default=None,
                          help="Chains to check (default: all)")

    # deposits
    p_deposit = sub.add_parser("deposits", help="Scan L1 bridge deposits")
    p_deposit.add_argument("--chain", default="ethereum", help="Source chain")
    p_deposit.add_argument("--blocks", type=int, default=100, help="Blocks to scan")
    p_deposit.add_argument("--start", type=int, help="Start block")
    p_deposit.add_argument("--min-eth", type=float, default=0, help="Min ETH filter")
    p_deposit.add_argument("--delay", type=float, default=0.15, help="RPC delay (s)")

    # withdrawals
    p_withdraw = sub.add_parser("withdrawals", help="Scan L2 withdrawals")
    p_withdraw.add_argument("--chain", default="optimism",
                            choices=["optimism", "arbitrum", "base"])
    p_withdraw.add_argument("--blocks", type=int, default=100, help="Blocks to scan")
    p_withdraw.add_argument("--start", type=int, help="Start block")
    p_withdraw.add_argument("--delay", type=float, default=0.15, help="RPC delay")

    # multi-bridge scan
    p_multi = sub.add_parser("scan", help="Scan all bridge contracts on Ethereum")
    p_multi.add_argument("--blocks", type=int, default=50, help="Blocks to scan")
    p_multi.add_argument("--min-eth", type=float, default=1, help="Min ETH threshold")
    p_multi.add_argument("--delay", type=float, default=0.15, help="RPC delay")

    parser.add_argument("--json", action="store_true", help="JSON output")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "status":
        chains = args.chains or list(RPC.keys())
        status = check_multi_chain(chains)
        if args.json:
            print(json.dumps(status, indent=2))
        else:
            print("\nChain Connectivity:")
            for chain, info in status.items():
                icon = "OK" if info["connected"] else "FAIL"
                block = info["latest_block"] or "N/A"
                lat = info["latency_ms"]
                print(f"  [{icon}] {chain:12} block: {block}  latency: {lat}ms")

    elif args.command == "deposits":
        latest = get_block_number(args.chain)
        if not latest:
            print(f"ERROR: Cannot connect to {args.chain} RPC", file=sys.stderr)
            sys.exit(1)
        start = args.start or (latest - args.blocks + 1)
        end = start + args.blocks - 1
        print(f"Scanning {args.chain} blocks {start} -> {end} for bridge deposits...",
              file=sys.stderr)
        txs = scan_bridge_deposits(args.chain, start, end, delay=args.delay)
        if args.min_eth > 0:
            txs = [t for t in txs if t["value_eth"] >= args.min_eth]
        stats = aggregate_bridge_stats(txs)
        if args.json:
            print(json.dumps({"transactions": txs, "stats": stats}, indent=2))
        else:
            print_report(stats, f"Bridge Deposits ({args.chain})")
            if txs:
                print("Recent deposits:")
                for tx in txs[-10:]:
                    print(f"  {tx['value_eth']} ETH via {tx['bridge']}"
                          f"  [{tx['tx_hash'][:16]}...]")
            else:
                print("  No bridge deposits found in this range.")

    elif args.command == "withdrawals":
        latest = get_block_number(args.chain)
        if not latest:
            print(f"ERROR: Cannot connect to {args.chain} RPC", file=sys.stderr)
            sys.exit(1)
        start = args.start or (latest - args.blocks + 1)
        end = start + args.blocks - 1
        print(f"Scanning {args.chain} blocks {start} -> {end} for withdrawals...",
              file=sys.stderr)
        txs = scan_withdrawals(args.chain, start, end, delay=args.delay)
        stats = aggregate_bridge_stats(txs)
        if args.json:
            print(json.dumps({"transactions": txs, "stats": stats}, indent=2))
        else:
            print_report(stats, f"Withdrawals ({args.chain})")

    elif args.command == "scan":
        latest = get_block_number("ethereum")
        if not latest:
            print("ERROR: Cannot connect to Ethereum RPC", file=sys.stderr)
            sys.exit(1)
        start = latest - args.blocks + 1
        end = latest
        print(f"Scanning Ethereum blocks {start} -> {end} for all bridge deposits...",
              file=sys.stderr)
        txs = scan_bridge_deposits("ethereum", start, end, delay=args.delay)
        if args.min_eth > 0:
            txs = [t for t in txs if t["value_eth"] >= args.min_eth]
        stats = aggregate_bridge_stats(txs)
        if args.json:
            print(json.dumps({"transactions": txs, "stats": stats}, indent=2))
        else:
            print_report(stats, "All Bridge Deposits (Ethereum)")


if __name__ == "__main__":
    main()
