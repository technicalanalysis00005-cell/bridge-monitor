# bridge-monitor

Cross-chain bridge transaction monitor for EVM chains. Tracks activity across Stargate, Across, Hop, and other major bridge protocols using public block explorers and RPC endpoints.

## Features

- **Multi-bridge scanning** — Stargate (LayerZero), Across Protocol, Hop Protocol
- **6 chains** — Ethereum, Arbitrum, Optimism, Base, Polygon, BSC
- **Token volume tracking** — ERC-20 transfer volume by token (USDT, USDC, WBTC, DAI, WETH)
- **Anomaly detection** — large transfers (3σ), failed transactions, high gas alerts
- **Activity stats** — tx count, total value, unique senders, gas metrics per contract
- **RPC-only mode** — direct `eth_getLogs` scanning, no explorer API key needed
- **Zero dependencies** — pure Python 3.8+ stdlib

## Install

```bash
git clone https://github.com/technicalanalysis00005-cell/bridge-monitor.git
cd bridge-monitor
# No install needed — pure stdlib
```

## Usage

### Scan Single Bridge (Explorer API)

```bash
# Scan Across Protocol on all chains (last 200 blocks)
python bridge_monitor.py scan --bridge across --blocks 200

# Scan Stargate on Ethereum only
python bridge_monitor.py scan --bridge stargate --chain ethereum --blocks 500

# JSON output for scripting
python bridge_monitor.py scan --bridge hop --json | jq '.stats'
```

### Scan via RPC (No API Key)

```bash
# Direct RPC scan — no explorer API key needed
python bridge_monitor.py rpc-scan --bridge across --chain ethereum --blocks 500

# Stargate on Optimism
python bridge_monitor.py rpc-scan --bridge stargate --chain optimism --blocks 1000 --json
```

### Scan All Bridges

```bash
# Quick overview of all bridges (last 100 blocks)
python bridge_monitor.py scan-all --blocks 100
```

Sample output:
```
============================================================
  ACROSS PROTOCOL — Activity Summary
============================================================

  ethereum/spoke_pool
    Transactions:  47
    Value:         12.5830 ETH
    Unique Users:  31
    Failed:        0
    Avg Gas:       18.42 Gwei
    Max Gas:       45.10 Gwei

  arbitrum/spoke_pool
    Transactions:  83
    Value:         45.2100 ETH
    Unique Users:  52
    Failed:        1
    Avg Gas:       0.15 Gwei
    Max Gas:       1.20 Gwei

  ────────────────────────────────────
  TOTAL: 130 txs | 57.7930 ETH | 1 failed
```

### Track Token Volume

```bash
# Track bridge token transfers on Ethereum
python bridge_monitor.py volume --bridge across --blocks 300
```

Sample output:
```
============================================================
  ACROSS — Token Volume (Ethereum)
============================================================
  Total transfers: 156

  Volume by token:
       USDT:   2,450,000.0000
       USDC:   1,830,500.0000
       WETH:          892.5000
        DAI:     45,200.0000
```

### Anomaly Detection

Anomalies are automatically flagged during scans:
- **Large transfers** — values >3σ above average for that bridge/chain
- **Failed transactions** — reverted or out-of-gas
- **High gas** — >100 Gwei gas price

```
  ANOMALY ALERTS (3 found)
============================================================
  [LARGE] across/arbitrum: 250.5000 ETH (avg: 12.3000, σ: 45.2000) [0xabcd1234...]
  [FAIL]  stargate/ethereum: Failed tx [0x9876fedc...]
  [GAS]   hop/ethereum: 185.20 Gwei [0xdeadbeef...]
```

### List Supported Chains/Bridges

```bash
python bridge_monitor.py chains
python bridge_monitor.py bridges
```

## Architecture

```
bridge_monitor.py
├── CHAINS                    — chain configs (RPC, explorer API, chain ID)
├── BRIDGE_CONTRACTS          — bridge contract addresses per chain
├── KNOWN_TOKENS              — common ERC-20 token registry
├── rpc_call() / explorer_api() — JSON-RPC + Etherscan-compatible API layer
├── BridgeScanner             — multi-chain bridge activity via explorer API
├── RpcLogScanner             — direct RPC eth_getLogs scanning (no API key)
├── VolumeTracker             — ERC-20 token transfer volume tracker
├── AnomalyDetector           — pattern-based anomaly detection (3σ, gas, fails)
└── main()                    — CLI: scan, rpc-scan, scan-all, volume, chains, bridges
```

## Supported Bridges

| Bridge | Protocol | Chains |
|--------|----------|--------|
| Stargate | LayerZero | Ethereum, Arbitrum, Optimism, Polygon |
| Across | UMA | Ethereum, Arbitrum, Optimism, Base, Polygon |
| Hop | Hop | Ethereum, Arbitrum, Optimism, Polygon |

## Rate Limits

Free Etherscan API tier: 5 requests/second. Use `--delay` to control pacing. For heavier scanning, set `ETHERSCAN_API_KEY` env var (optional).

RPC-only mode (`rpc-scan`) uses public RPC endpoints directly — no API key needed, but respects RPC rate limits with built-in delays.

## License

MIT
