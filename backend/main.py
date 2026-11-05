import asyncio
import json
import logging
import os
import sqlite3
import threading
from contextlib import asynccontextmanager
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from web3 import Web3

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=True)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("brickshare")

RPC = os.getenv("SEPOLIA_RPC_URL", "")
ADDRESS = os.getenv("CONTRACT_ADDRESS", "")
ABI_PATH = Path(os.getenv("CONTRACT_ABI_PATH", "../contracts/BrickShare.json"))
if not ABI_PATH.is_absolute():
    ABI_PATH = ROOT / ABI_PATH
DB = Path(os.getenv("DATABASE_URL", "events.db"))
if not DB.is_absolute():
    DB = ROOT / DB
EXPECTED_CHAIN_ID = 11155111

try:
    abi = json.loads(ABI_PATH.read_text(encoding="utf-8"))["abi"]
except (OSError, json.JSONDecodeError, KeyError) as exc:
    logger.exception("Could not load contract ABI from %s", ABI_PATH)
    abi = []

w3 = Web3(Web3.HTTPProvider(RPC, request_kwargs={"timeout": 15})) if RPC else None
contract = None
if w3 and Web3.is_address(ADDRESS):
    contract = w3.eth.contract(address=Web3.to_checksum_address(ADDRESS), abi=abi)

clients: set[WebSocket] = set()
event_sync_lock = threading.Lock()
EVENT_NAMES = ["InvestorApproved", "InvestorVerified", "TokensPurchased", "DocumentUpdated", "SaleStatusChanged", "Withdrawn"]


def configured_start_block() -> int:
    try:
        return int(os.getenv("START_BLOCK", "12068071"))
    except ValueError as exc:
        raise RuntimeError("START_BLOCK must be an integer") from exc


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS events (
            tx TEXT NOT NULL,
            log_index INTEGER NOT NULL,
            block INTEGER NOT NULL,
            name TEXT NOT NULL,
            data TEXT NOT NULL,
            timestamp INTEGER,
            UNIQUE(tx, log_index)
        )"""
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
    if "timestamp" not in columns:
        conn.execute("ALTER TABLE events ADD COLUMN timestamp INTEGER")
    conn.execute("CREATE TABLE IF NOT EXISTS checkpoint (id INTEGER PRIMARY KEY CHECK (id = 1), last_block INTEGER NOT NULL)")
    conn.commit()
    return conn


def require_chain():
    if not RPC or not ADDRESS or not abi or not contract:
        raise HTTPException(503, "BrickShare backend is not configured. Check backend/.env and the ABI path.")
    try:
        chain_id = w3.eth.chain_id
        if chain_id != EXPECTED_CHAIN_ID:
            raise HTTPException(502, f"RPC is connected to chain {chain_id}; Ethereum Sepolia ({EXPECTED_CHAIN_ID}) is required.")
        if len(w3.eth.get_code(Web3.to_checksum_address(ADDRESS))) == 0:
            raise HTTPException(502, "No contract bytecode exists at CONTRACT_ADDRESS on Sepolia.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Blockchain validation failed: %s", type(exc).__name__)
        raise HTTPException(503, "Sepolia RPC request failed.") from exc
    return contract


def addr(value: str) -> str:
    if not Web3.is_address(value):
        raise HTTPException(400, "Invalid Ethereum address")
    return Web3.to_checksum_address(value)


def contract_read_errors(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("%s contract read failed: %s", function.__name__, type(exc).__name__)
            raise HTTPException(502, "Contract state could not be read from Sepolia.") from exc
    return wrapped


def prop() -> dict:
    c = require_chain()
    try:
        sold = c.functions.totalSupply().call()
        cap = c.functions.totalSupplyCap().call()
        price = c.functions.pricePerShare().call()
        return {
            "contract": ADDRESS,
            "name": c.functions.name().call(),
            "symbol": c.functions.symbol().call(),
            "priceWei": str(price),
            "priceEth": str(Web3.from_wei(price, "ether")),
            "supplyCap": cap,
            "sold": sold,
            "remaining": c.functions.sharesRemaining().call(),
            "saleActive": c.functions.saleActive().call(),
            "documentCid": c.functions.documentCid().call(),
            "owner": c.functions.owner().call(),
            "admins": [c.functions.adminA().call(), c.functions.adminB().call()],
        }
    except Exception as exc:
        logger.error("Property read failed: %s", type(exc).__name__)
        raise HTTPException(502, "Contract state could not be read from Sepolia.") from exc


@asynccontextmanager
async def lifespan(app: FastAPI):
    db().close()
    try:
        if w3:
            logger.info("Connected to chain %s", w3.eth.chain_id)
        else:
            logger.error("Sepolia RPC is unreachable")
    except Exception as exc:
        logger.error("Startup blockchain validation failed: %s", type(exc).__name__)
    task = asyncio.create_task(poll_events())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="BrickShare API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    connected = False
    chain_id = None
    bytecode = False
    block = None
    try:
        if w3:
            chain_id = w3.eth.chain_id
            block = w3.eth.block_number
            bytecode = bool(ADDRESS and Web3.is_address(ADDRESS) and w3.eth.get_code(Web3.to_checksum_address(ADDRESS)))
            connected = True
    except Exception as exc:
        logger.error("Health check RPC read failed: %s", type(exc).__name__)
    return {
        "status": "ok" if connected and chain_id == EXPECTED_CHAIN_ID and bytecode else "unavailable",
        "rpcConnected": connected,
        "network": "sepolia" if chain_id == EXPECTED_CHAIN_ID else None,
        "chainId": chain_id,
        "contractConnected": bytecode,
        "block": block,
    }


@app.get("/property")
def property():
    return prop()


@app.get("/demo/role/{address}")
def demo_role(address: str):
    investor = addr(address)
    c = require_chain()
    reads = (
        ("owner", c.functions.owner, ()),
        ("adminA", c.functions.adminA, ()),
        ("adminB", c.functions.adminB, ()),
        ("isVerified", c.functions.isVerified, (investor,)),
        ("balanceOf", c.functions.balanceOf, (investor,)),
        ("approvalCount", c.functions.approvalCount, (investor,)),
    )
    values = {}
    for name, function, args in reads:
        try:
            values[name] = function(*args).call()
        except AttributeError as exc:
            logger.error("Demo role ABI read failed at %s: %s", name, type(exc).__name__)
            raise HTTPException(502, "BrickShare ABI does not match the deployed contract.") from exc
        except Exception as exc:
            logger.error("Demo role contract read failed at %s: %s", name, type(exc).__name__)
            raise HTTPException(502, f"Contract read failed for {name} on Sepolia.") from exc

    address_lower = investor.lower()
    role = "unknown"
    if address_lower == values["owner"].lower():
        role = "owner"
    elif address_lower == values["adminA"].lower():
        role = "adminA"
    elif address_lower == values["adminB"].lower():
        role = "adminB"
    elif values["isVerified"] or values["balanceOf"] > 0:
        role = "investor"
    return {
        "wallet": investor,
        "address": investor,
        "role": role,
        "isVerified": values["isVerified"],
        "balance": str(values["balanceOf"]),
        "approvalCount": values["approvalCount"],
        "demoMode": "read-only",
    }


@app.get("/holdings/{address}")
@contract_read_errors
def holdings(address: str):
    investor = addr(address)
    c = require_chain()
    admins = [c.functions.adminA().call(), c.functions.adminB().call()]
    balance = c.functions.balanceOf(investor).call()
    cap = c.functions.totalSupplyCap().call()
    price = c.functions.pricePerShare().call()
    remaining = c.functions.sharesRemaining().call()
    verified = c.functions.isVerified(investor).call()
    return {
        "address": investor,
        "shares": balance,
        "percentOfSupply": round(balance * 100 / cap, 6) if cap else 0,
        "valueEth": str(Web3.from_wei(balance * price, "ether")),
        "verified": verified,
        "approvals": c.functions.approvalCount(investor).call(),
        "adminAApproved": c.functions.hasApproved(investor, admins[0]).call(),
        "adminBApproved": c.functions.hasApproved(investor, admins[1]).call(),
        "canPurchase": verified and c.functions.saleActive().call() and remaining > 0,
    }


@app.get("/investors/{address}/status")
@contract_read_errors
def investor_status(address: str):
    investor = addr(address)
    c = require_chain()
    admin_a, admin_b = c.functions.adminA().call(), c.functions.adminB().call()
    verified = c.functions.isVerified(investor).call()
    return {
        "address": investor,
        "isVerified": verified,
        "approvalCount": c.functions.approvalCount(investor).call(),
        "adminAApproved": c.functions.hasApproved(investor, admin_a).call(),
        "adminBApproved": c.functions.hasApproved(investor, admin_b).call(),
        "canPurchase": verified and c.functions.saleActive().call() and c.functions.sharesRemaining().call() > 0,
    }


@app.get("/events")
def events(limit: int = 50):
    try:
        sync_events_once()
    except Exception as exc:
        logger.error("Event refresh failed: %s", type(exc).__name__)
        raise HTTPException(503, "Sepolia event indexer is temporarily unavailable.") from exc
    conn = db()
    try:
        rows = conn.execute(
            "SELECT block, name, data, tx, timestamp FROM events ORDER BY block DESC, log_index DESC LIMIT ?",
            (min(max(limit, 1), 1000),),
        ).fetchall()
        result = []
        for row in rows:
            timestamp = row[4]
            if timestamp is None and w3:
                try:
                    timestamp = w3.eth.get_block(row[0]).timestamp
                    conn.execute("UPDATE events SET timestamp = ? WHERE block = ? AND timestamp IS NULL", (timestamp, row[0]))
                    conn.commit()
                except Exception:
                    logger.warning("Could not backfill timestamp for block %s", row[0])
            result.append({"event": row[1], "transactionHash": row[3], "blockNumber": row[0], "timestamp": timestamp, "args": json.loads(row[2])})
        return result
    finally:
        conn.close()


@app.websocket("/ws/events")
async def ws(socket: WebSocket):
    await socket.accept()
    clients.add(socket)
    try:
        while True:
            await socket.receive_text()
    except (WebSocketDisconnect, Exception):
        clients.discard(socket)


def json_value(value):
    if isinstance(value, int):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


async def broadcast(message: dict):
    for client in list(clients):
        try:
            await client.send_json(message)
        except Exception:
            clients.discard(client)


def sync_events_once() -> list[dict]:
    if not w3 or not contract or w3.eth.chain_id != EXPECTED_CHAIN_ID:
        raise RuntimeError("Sepolia RPC is unavailable")
    with event_sync_lock:
        latest = w3.eth.block_number
        conn = db()
        messages = []
        try:
            checkpoint = conn.execute("SELECT last_block FROM checkpoint WHERE id = 1").fetchone()
            start = checkpoint[0] + 1 if checkpoint else configured_start_block()
            if start <= latest:
                # Alchemy's configured Sepolia endpoint rejects larger eth_getLogs windows.
                for block_number in range(start, latest + 1, 10):
                    end = min(block_number + 9, latest)
                    for event_name in EVENT_NAMES:
                        event = getattr(contract.events, event_name)()
                        for log in event.get_logs(from_block=block_number, to_block=end):
                            transaction_hash = log["transactionHash"].hex()
                            args = {key: json_value(value) for key, value in dict(log["args"]).items()}
                            timestamp = w3.eth.get_block(log["blockNumber"]).timestamp
                            cursor = conn.execute(
                                "INSERT OR IGNORE INTO events(tx, log_index, block, name, data, timestamp) VALUES(?,?,?,?,?,?)",
                                (transaction_hash, log["logIndex"], log["blockNumber"], event_name, json.dumps(args), timestamp),
                            )
                            conn.commit()
                            if cursor.rowcount == 1:
                                messages.append({"event": event_name, "transactionHash": transaction_hash, "blockNumber": log["blockNumber"], "timestamp": timestamp, "args": args})
                    conn.execute("INSERT OR REPLACE INTO checkpoint(id, last_block) VALUES(1, ?)", (end,))
                    conn.commit()
            return messages
        finally:
            conn.close()


async def poll_events():
    retry_delay = 10
    while True:
        try:
            for message in await asyncio.to_thread(sync_events_once):
                await broadcast(message)
            retry_delay = 10
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Event polling failed; will retry: %s", type(exc).__name__)
            retry_delay = min(retry_delay * 2, 120)
        await asyncio.sleep(retry_delay)
