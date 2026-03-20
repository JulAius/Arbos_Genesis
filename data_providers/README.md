# Bittensor Data Providers

This module provides CLI tools for accessing off-chain Bittensor-related data from Taostats and Taomarketcap.

## Tools

### taostats

Query network statistics, block emissions, miner reports, subnet info, and validator performance.

**Examples:**

```bash
# List all subnets
taostats list-subnets

# Get subnet 1 info
taostats subnet-info 1

# Get blocks emitted in last 24 hours on subnet 1
taostats blocks-emitted --start $(date -d '24 hours ago' -Iseconds) --netuid 1

# Get report for a specific miner
taostats miner-report --hotkey 5Hotkey... --netuid 1

# Get validator performance
taostats validator-performance 5Hotkey... --netuid 1

# Get token economics
taostats token-economics
```

### taomarketcap

Query TAO token market data including price, market cap, volume, supply, and exchange information.

**Examples:**

```bash
# Get current price
taomarketcap price

# Get market cap
taomarketcap market-cap

# Get 24h volume
taomarketcap volume --interval 24h

# Get token supply
taomarketcap supply

# Get 30-day historical prices
taomarketcap historical $(date -d '30 days ago' -Iseconds) --interval 1d --metric price

# List exchanges
taomarketcap exchanges

# Get exchange volume
taomarketcap exchange-volume binance
```

## Configuration

Set API keys in `.env`:

```bash
TAOSTATS_API_KEY="your-taostats-api-key"
TAOMARKETCAP_API_KEY="your-taomarketcap-api-key"
```

Get API keys:
- Taostats: https://docs.taostats.io/docs/api
- Taomarketcap: https://api.taomarketcap.com/developer/documentation/

## Verification

Run the check script to verify installation and configuration:

```bash
./tools/check_data_providers.sh
```

## Architecture

Each tool is implemented as a Python module with a CLI entrypoint. They are installed as executable scripts in `tools/` and added to PATH via `.arbos-launch.sh`.

The tools output JSON to stdout, making them easy to parse programmatically (e.g., with `jq` or within Python scripts).

## Error Handling

If an API key is missing, the tool will exit with an error. HTTP errors from the API are returned as JSON with `error` and optional `status_code` fields.

## Rate Limits

Be mindful of rate limits. For heavy queries that need multiple API calls (e.g., fetching data for many subnets), it's better to write a Python script that uses the underlying module functions directly rather than invoking the CLI repeatedly.

## Notes

- All timestamps must be in ISO 8601 format (e.g., `2024-01-01T00:00:00Z`).
- For time ranges, use `--start` alone to get data from that time to now.
- Data from these APIs may be slightly delayed compared to real-time chain state. For absolute accuracy, use `agcli` or `btcli` when possible.
