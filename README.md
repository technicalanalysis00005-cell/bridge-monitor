# bridge-monitor

Cross-chain bridge transaction monitor for Ethereum L2 ecosystems. Tracks deposits, withdrawals, fund flows, and gas costs across Optimism, Arbitrum, Base, and Polygon bridges.

## Features

- **Deposit Scanning** -- find ETH deposits to L1 bridge contracts (Optimism Portal, Arbitrum Inbox, Base Portal, Polygon PoS Bridge)
- **Withdrawal Tracking** -- monitor L2 withdrawal transactions
- **Large Transfer Detection** -- filter by ETH threshold
- **Bridge Statistics** -- aggregated counts, volumes, hourly activity, top senders
- **Multi-Chain Status** -- verify connectivity to multiple chains simultaneously
- **Latency Measurement** -- RPC response times per chain
- **Zero Dependencies** -- pure Python 3.8+ stdlib

## Install

```bash
git clone https://github.com/technicalanalysis00005-cell/bridge-monitor.git
cd bridge-monitor
# No install needed -- pure stdlib
```

## Usage

### Check Chain Connectivity

```bash
python bridge_monitor.py status
```

Output:
```
Chain Connectivity:
  [OK] ethereum     block: 19150000  latency: 120ms
  [OK] arbitrum     block: 180234567  latency: 95ms
  [OK] optimism     block: 115234567  latency: 88ms
  [OK] base         block: 12345678  latency: 102ms
  [OK] polygon      block: 55234567  latency: 110ms
```

### Scan L1 Bridge Deposits

```bash
# Last 200 blocks, filter deposits > 1 ETH
python bridge_monitor.py deposits --blocks 200 --min-eth 1

# Specific block range
python bridge_monitor.py deposits --start 19000000 --blocks 100 --min-eth 5

# JSON output for piping to jq
python bridge_monitor.py deposits --blocks 100 --json
```

### Scan L2 Withdrawals

```bash
# Optimism withdrawals (last 500 blocks)
python bridge_monitor.py withdrawals --chain optimism --blocks 500

# Arbitrum withdrawals
python bridge_monitor.py withdrawals --chain arbitrum --blocks 200

# Base withdrawals
python bridge_monitor.py withdrawals --chain base --blocks 200
```

### Multi-Bridge Scan

```bash
# Scan all bridge contracts on Ethereum
python bridge_monitor.py scan --blocks 100 --min-eth 1
```

### Sample Report

```
============================================================
  ALL BRIDGE DEPOSITS (ETHEREUM) REPORT
============================================================

Total transactions: 47
Total value: 12,845.32 ETH
Unique senders: 38
Avg tx value: 273.30 ETH

-- By Bridge --
  Optimism Portal 2: 18 txs, 5230.50 ETH
  Base Portal: 14 txs, 4102.22 ETH
  Arbitrum Bridge: 9 txs, 2512.60 ETH
  Polygon PoS Bridge: 6 txs, 1000.00 ETH

-- Hourly Activity (last 12h) --
  2026-08-04 08:00 | ######## 8
  2026-08-04 09:00 | ##### 5
  2026-08-04 10:00 | ########## 10

-- Top Senders --
  0x1234abcd...: 6 txs
  0xdeadbeef...: 4 txs

-- Gas (Deposits) --
  Avg: 14.82 Gwei
  Median: 13.50 Gwei
  Max: 32.10 Gwei

============================================================
```

## Architecture

```
bridge_monitor.py
├── RPC layer           -- multi-chain JSON-RPC with failover
├── Bridge contracts    -- known addresses for OP, ARB, Base, Polygon
├── Deposit scanner     -- L1 tx scanning for bridge interactions
├── Withdrawal scanner  -- L2 withdrawal tx detection
├── Stats aggregator    -- volumes, counts, hourly, top senders
└── CLI                 -- argparse with subcommands
```

## Supported Bridges

| Bridge | L1 Contract | Direction |
|--------|------------|-----------|
| Optimism Portal | `0x4Dbd...BAB3f` | Deposit |
| Optimism Portal 2 | `0x4904...97e` | Deposit |
| Arbitrum Inbox | `0x4Dbd...BAB3f` | Deposit |
| Arbitrum Bridge | `0xa3A7...C77` | Deposit |
| Base Portal | `0x3154...C35` | Deposit |
| Polygon PoS | `0xA0c6...C77` | Deposit |
| OP/ARB/Base L2 Bridge | `0x4200...0010` | Withdrawal |
| Arbitrum Outbox | `0x0B98...0d88` | Withdrawal |

## Public RPCs Used

- `eth.llamarpc.com`, `rpc.ankr.com/eth`, `ethereum.publicnode.com`
- `arb1.arbitrum.io/rpc`, `rpc.ankr.com/arbitrum`
- `mainnet.optimism.io`, `rpc.ankr.com/optimism`
- `mainnet.base.org`, `rpc.ankr.com/base`
- `polygon-rpc.com`, `rpc.ankr.com/polygon`

All free, no API key needed. Rate limits apply -- use `--delay` to throttle.

## Dependencies

None. Pure Python 3.8+ stdlib.

## License

MIT
