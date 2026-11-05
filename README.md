# BrickShare dApp

BrickShare is a small real-estate investment dashboard for buying verified fractional shares of one tokenized Dubai property on Ethereum Sepolia.

## Status

The application is wired to the deployed Sepolia contract at `0x8c868c908EEA15Be89ef7f092da85bc0739Cd1e0`. A working Sepolia RPC URL is still required in the local backend environment.

## Features

- FastAPI reads property, holdings and indexed event data from the contract.
- Next.js + TypeScript dashboard with MetaMask and ethers.js v6.
- Exact-ETH share purchase with pending, submitted, confirmed and rejected states.
- Two-admin investor approval extension enforced by Solidity.
- SQLite event history and polling-based live activity feed.
- Sepolia network and missing MetaMask handling.

## Screenshots

![Property overview](<docs/screenshots/Screenshot 2026-11-05 200816.png>)
![Property dashboard](<docs/screenshots/Screenshot 2026-11-05 224931.png>)
![Investor holdings](<docs/screenshots/Screenshot 2026-11-05 225001.png>)
![Admin workspace](<docs/screenshots/Screenshot 2026-11-05 225029.png>)
![Owner controls](<docs/screenshots/Screenshot 2026-11-05 225057.png>)
![Live activity](<docs/screenshots/Screenshot 2026-11-05 225118.png>)

## Quick start

Prerequisites: Python 3.11+, Node.js 20+, MetaMask on Sepolia, a deployed compatible contract and an RPC URL.

```powershell
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env.local
# edit both files with the same deployed contract address
python -m venv backend/venv
backend/venv/Scripts/pip install -r backend/requirements.txt
cd frontend
npm install
```

Run the backend in one terminal:

```powershell
cd backend
venv/Scripts/uvicorn main:app --reload
```

Run the frontend in another:

```powershell
cd frontend
npm run dev
```

Open http://localhost:3000, connect MetaMask on Sepolia, get two admin approvals for the investor wallet, then buy shares.

## Configuration

`backend/.env.example` contains the RPC URL, contract address, ABI path, SQLite path, starting block and frontend origin. `frontend/.env.example` contains the API URL and contract address. Real `.env` files are ignored.

## Documentation

- [Scope](docs/SCOPE.md)
- [Technical design](docs/TECHNICAL.md)

## Backend API

With the backend running at `http://localhost:8000`: `GET /health`, `GET /property`, `GET /demo/role/{address}`, `GET /holdings/{address}`, `GET /investors/{address}/status`, `GET /events?limit=1000`, and `WS /ws/events` are available. The event worker backfills from block `12068071`, stores unique transaction/log pairs in `backend/events.db`, keeps a block checkpoint, and refreshes before `/events` responds so recent purchases appear after a refresh.

## Frontend pages

Run the frontend with `cd frontend; npm run dev` and open `http://localhost:3000`.

- `/` — live property and purchase overview.
- `/holdings` — connected wallet status, approvals and purchase activity.
- `/admin` — Admin A/B investor approval workflow.
- `/owner` — owner-only sale, document CID and withdrawal controls.

MetaMask must be on Sepolia. Transactions are signed in the wallet; the backend never receives a private key.

## Submission notes

The deployed contract and source are linked above. Record the final 3–5 minute walkthrough video and add its link here before submitting the repository to LearnX; those external submission steps cannot be completed from the local workspace.

## Contract

The source and ABI are in `contracts/`. [Sepolia contract](https://sepolia.etherscan.io/address/0x8c868c908EEA15Be89ef7f092da85bc0739Cd1e0), deployed at block `12068071`.

## Acknowledgements

Built with Solidity/OpenZeppelin, web3.py, FastAPI, Next.js, React, TypeScript and ethers.js. AI assistance was used for implementation and documentation; all final code should be reviewed before submission.
