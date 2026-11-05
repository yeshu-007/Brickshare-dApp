# BrickShare — Scope

## Product

BrickShare is a read/write dApp for one verified real-estate share contract on Ethereum Sepolia. Verified wallets buy fixed-price shares with ETH; two fixed admin wallets approve investors; the owner controls the sale and records a public IPFS document CID.

## Users and flows

- Public visitors read property data, the public IPFS document link and live contract activity.
- Investors connect MetaMask, see verification and holdings, and buy shares when verified.
- Admin A and Admin B each approve an investor address. The second approval completes verification, and the other admin sees the pending approval in the Admin workspace.
- The owner activates or pauses the sale, records a CID with `setDocument`, and withdraws contract ETH.
- All privileged writes are signed in MetaMask. The backend never holds a wallet private key.

## Screens

- `/` — property overview, price/supply data, purchase flow, public document link and live activity.
- `/holdings` — connected wallet balance, approvals, ownership percentage and indexed purchase history.
- `/admin` — admin-only investor approval workflow and approval events.
- `/owner` — owner-only sale controls, document CID update and withdrawal.

## Responsibilities

| Area | Contract | Backend | Frontend |
|---|---|---|---|
| Price, supply, sale state and balances | Stores/enforces | Reads | Displays |
| Investor approval and verification | Stores/enforces two-admin rule | Reads | Sends approval transactions |
| Share purchase | Executes ETH transaction | Not involved | Sends from MetaMask |
| Property and holdings reads | Exposes view functions | FastAPI JSON | Renders |
| Event history/live activity | Emits events | SQLite indexer + WebSocket | Refreshes and displays |
| Document | Stores CID only | Reads CID | Builds public `ipfs.io` link |

## Contract and deployment

- Network: Ethereum Sepolia (`11155111`).
- Contract: [`0x8c868c908EEA15Be89ef7f092da85bc0739Cd1e0`](https://sepolia.etherscan.io/address/0x8c868c908EEA15Be89ef7f092da85bc0739Cd1e0).
- Deployment block: `12068071`.
- Contract source and ABI are in `contracts/`.
- The deployed contract is not changed by the application. The backend validates chain ID and bytecode before reads.

## Backend API

FastAPI exposes `/health`, `/property`, `/demo/role/{address}`, `/holdings/{address}`, `/investors/{address}/status`, `/events` and `WS /ws/events`. Event indexing starts at the deployment block, persists a checkpoint and refreshes before `/events` responds, so a page refresh can discover recent purchases. The provider is queried in small ten-block windows for compatibility with the configured Sepolia RPC.

## Security and configuration

- Real credentials belong only in ignored `backend/.env` and `frontend/.env.local` files.
- Committed `.env.example` files contain placeholders only.
- The backend uses a read-only RPC provider and does not expose RPC URLs or full exception traces in API responses or normal logs.
- IPFS documents are public by design; a CID is not proof of title, valuation or legal ownership.

## Explicit non-goals

There is no username/password authentication, wallet-signature session system, Pinata upload service, real KYC, rental/dividend system, secondary market, multi-property factory, document sign-off workflow, or legal ownership claim. The owner supplies a CID; the dApp exposes the resulting public gateway link.

## Acceptance checks

- Sepolia chain ID, deployed bytecode and contract reads are valid.
- `/property` returns live deployed contract data.
- Invalid addresses return a clear client error; RPC and ABI failures return a bounded backend error.
- Two-admin approval, MetaMask network/rejection handling and confirmed purchase flows remain functional.
- `/events` and the WebSocket expose newly indexed events without requiring a backend restart.
- Frontend TypeScript, ESLint and production build pass before submission.
