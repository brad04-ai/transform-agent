# Data Transform Agent

A headless, zero-UI data transformation service that converts between **55+ format pairs** including aviation weather formats. Discovered by AI agents via [MCP](https://modelcontextprotocol.io), [Google A2A](https://github.com/google/A2A), and OpenAPI. Paid via [x402](https://www.x402.org) (USDC stablecoin) — first 100 requests free.

**Live endpoint:** `https://transform-agent-lingering-surf-8155.fly.dev`

---

## Supported Formats

| Category | Formats |
| --- | --- |
| **Structured** | JSON, CSV, XML, YAML, TOML |
| **Markup** | HTML, Markdown, Plain Text |
| **Documents** | PDF, Excel (.xlsx), DOCX |
| **Encoding** | Base64, URL-encoded, Hex |
| **Aviation** | METAR, TAF, NOTAM, PIREP |

---

## Aviation Features

Purpose-built for aviation AI agents and flight planning workflows. Parses raw aviation weather formats into clean structured data.

### METAR → Markdown
```json
{
  "source_format": "metar",
  "target_format": "markdown",
  "data": "METAR KSFO 061956Z 28015KT 10SM FEW015 BKN030 14/08 A2992"
}
```
Returns:
```
## METAR — KSFO
**Flight Category:** 🟢 VFR
**Wind:** 280° at 15kt
**Visibility:** 10.0 SM
**Sky:** FEW @ 1500ft, BKN @ 3000ft
**Temp/Dew:** 14°C / 8°C
**Altimeter:** 29.92 inHg
```

### PIREP → Markdown
```json
{
  "source_format": "pirep",
  "target_format": "markdown",
  "data": "UA /OV OAK/TM 1530/FL085/TP C172/SK BKN065/TA 05/WV 27015/TB LGT/RM SMOOTH BELOW"
}
```
Returns:
```
## PIREP 🔵 ROUTINE
**Location:** OAK
**Altitude:** 8500 ft
**Aircraft:** C172
**Sky:** BKN065
**Temperature:** 5C
**Wind:** 270deg at 15kt
**Turbulence:** 🟢 LGT
**Remarks:** SMOOTH BELOW
```

All aviation formats also support `json` and `plain_text` as target formats.

---

## Quick Start

### Use via MCP (Claude, Cursor, Windsurf, etc.)

Add to your MCP client config:
```json
{
  "mcpServers": {
    "data-transform-agent": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://transform-agent-lingering-surf-8155.fly.dev/mcp"
      ]
    }
  }
}
```

### Use via REST API
```bash
# 1. Get a free API key (instant, no signup)
curl -X POST https://transform-agent-lingering-surf-8155.fly.dev/auth/provision \
  -H "Content-Type: application/json" \
  -d '{}'

# 2. Convert a METAR to JSON
curl -X POST https://transform-agent-lingering-surf-8155.fly.dev/transform \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "source_format": "metar",
    "target_format": "json",
    "data": "METAR KSFO 061956Z 28015KT 10SM FEW015 BKN030 14/08 A2992"
  }'
```

---

## Discovery Protocols

| Protocol | Endpoint |
| --- | --- |
| **MCP** (Streamable HTTP) | `/mcp` |
| **Google A2A** (Agent Card) | `/.well-known/agent-card.json` |
| **OpenAPI** | `/openapi.json` |
| **Smithery** | [smithery.ai/server/brad04-ai/data-transform](https://smithery.ai/server/brad04-ai/data-transform) |
| **mcp.so** | [mcp.so](https://mcp.so) |

---

## Pricing

| Transform Type | Cost |
| --- | --- |
| Text formats (JSON, CSV, XML, YAML, etc.) | $0.001 |
| Aviation formats (METAR, TAF, NOTAM, PIREP) | $0.001 |
| Documents (PDF, Excel, DOCX) | $0.005 |
| Encoding (Base64, hex, URL) | $0.0005 |

First **100 requests are free** per API key. After that, pay-per-request via [x402](https://www.x402.org) (USDC on Base).

---

## Self-Hosting
```bash
git clone https://github.com/brad04-ai/transform-agent
cd transform-agent
fly launch --copy-config
fly secrets set WALLET_ADDRESS=0xYourAddress ADMIN_API_KEY=your-secret
fly deploy
```

## License

MIT
