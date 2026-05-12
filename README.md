# LLM JSON Fixer & Agent Reliability Suite

An autonomous, Model Context Protocol (MCP) compliant server designed for the Machine-to-Machine (M2M) economy. This suite provides deterministic JSON repair, server registry payloads, and a built-in cryptographic Trust Auditor.

It is secured by a hardened **x402 M2M Payment Gate** that verifies real-time USDC micro-payments on the Base Layer 2 blockchain.

## 🛠️ Available Tools (0.001 USDC per Session)

1. **`repair_llm_json`**: A highly deterministic utility that fixes malformed LLM JSON. It natively handles markdown blocks, trailing commas, single quotes, unquoted keys, Python literals, bareword values, and comments.
2. **`generate_server_card`**: Generates a valid `/.well-known/mcp/server-card.json` payload for publishing an MCP server to registries like Smithery.
3. **`audit_trust_manifest`**: The ecosystem's first automated compliance node. It audits a target MCP server's `/trust.json` to verify compliance with M2M transparency standards, complete with SSRF protection and active runtime probes to catch mock-mode spoofing.

## 🔒 Security & M2M Payments

This server requires a `Payment-Signature` header for all `/mcp/sse` connections.

* **Validation Level**: Full On-Chain Settlement Verification (Base L2)
* **Binding Policy**: One Transaction = One Session (24-hour TTL)
* **Replay Protection**: Global and persistent via Redis. Nonces and Tx Hashes cannot be replayed across workers or restarts.
* **Failure Contract**: RPC errors do *not* consume the payment. Missing or invalid payments return a strict `402 Payment Required`.

## 🚀 Configuration & Deployment

### Environment Variables
Copy `.env.example` to `.env` and configure:
```env
# Base L2 address where payments should be sent
RECIPIENT_ADDRESS=0xYourBaseAddressHere

# Payment Gate Mode (mock | format | onchain)
PAYMENT_MODE=onchain

# Base RPC URL (e.g., Alchemy, Infura, Coinbase)
RPC_URL=[https://mainnet.base.org](https://mainnet.base.org)

# Redis URL for global replay protection
REDIS_URL=redis://...

```

### Local Testing

To run the server locally with format-only validation (bypassing on-chain checks):

```bash
PAYMENT_MODE=format uvicorn main:app --host 127.0.0.1 --port 8000

```

### Manifest Transparency

This server natively hosts its own transparent metadata:

* `/.well-known/mcp.json`
* `/.well-known/mcp/server-card.json`
* `/trust.json`
* `/pricing.json`

