import datetime
import time
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Cache for NFO instruments to avoid repeated heavy API calls
_nifty_options_cache = None
_nifty_options_cache_time = None

def get_nifty_options(client, api_key: str) -> List[Dict[str, Any]]:
    """Fetch NFO NIFTY options and cache them for 1 hour."""
    global _nifty_options_cache, _nifty_options_cache_time
    now = time.time()
    if _nifty_options_cache is not None and _nifty_options_cache_time is not None:
        if now - _nifty_options_cache_time < 3600:
            return _nifty_options_cache

    # Public NFO instruments API is faster and bypasses account proxy routing
    import requests
    import csv
    import io
    
    try:
        logger.info("Fetching NFO instruments directly from Zerodha public API...")
        url = "https://api.kite.trade/instruments/NFO"
        # Explicitly bypass proxies to avoid Cloudflare reputational blocks
        resp = requests.get(url, proxies={"http": None, "https": None}, timeout=15)
        if resp.status_code == 200:
            f = io.StringIO(resp.text)
            reader = csv.DictReader(f)
            options = []
            for row in reader:
                if row.get("name") == "NIFTY" and row.get("instrument_type") in ("CE", "PE"):
                    try:
                        exp_date = datetime.datetime.strptime(row["expiry"], "%Y-%m-%d").date()
                    except Exception:
                        exp_date = row["expiry"]
                    options.append({
                        "tradingsymbol": row["tradingsymbol"],
                        "name": row["name"],
                        "expiry": exp_date,
                        "strike": float(row["strike"]) if row.get("strike") else 0.0,
                        "instrument_type": row["instrument_type"],
                        "lot_size": int(row["lot_size"]) if row.get("lot_size") else 50
                    })
            _nifty_options_cache = options
            _nifty_options_cache_time = now
            return options
    except Exception as exc:
        logger.error("Failed to fetch NFO instruments directly: %s. Falling back to client session...", exc)

    # Fallback to standard client API call if public direct fetch fails
    from cli.api_client import _manager
    kite = _manager._clients.get(api_key)
    if not kite:
        if _nifty_options_cache is not None:
            return _nifty_options_cache
        return []

    try:
        instruments = kite.instruments("NFO")
        options = [
            inst for inst in instruments
            if inst.get("name", "").upper() == "NIFTY"
            and inst.get("instrument_type") in ("CE", "PE")
        ]
        _nifty_options_cache = options
        _nifty_options_cache_time = now
        return options
    except Exception as exc:
        logger.error("Kite fallback instruments fetch failed: %s", exc)
        if _nifty_options_cache is not None:
            return _nifty_options_cache
        return []

def find_option_symbols(options: List[Dict[str, Any]], expiry: datetime.date, strike: float):
    """Find CE and PE symbols for a given expiry and strike."""
    ce_symbol = None
    pe_symbol = None
    for inst in options:
        if inst.get("expiry") == expiry and abs(float(inst.get("strike", 0)) - strike) < 0.1:
            inst_type = inst.get("instrument_type")
            if inst_type == "CE":
                ce_symbol = inst.get("tradingsymbol")
            elif inst_type == "PE":
                pe_symbol = inst.get("tradingsymbol")
    return ce_symbol, pe_symbol

def generate_tuesday_plan(
    client,
    accounts_positions: List[Dict[str, Any]],
    margins_by_api_key: Dict[str, Dict[str, Any]],
    api_key_to_user_id: Dict[str, str],
    nifty_spot: float | None = None
) -> Dict[str, Any]:
    """
    Generate Tuesday strangle advisor plan based on the 50/50 margin split rule.
    """
    plan = {
        "status": "success",
        "nifty_spot": nifty_spot,
        "expiries": {},
        "accounts": []
    }

    if not accounts_positions:
        return {"status": "error", "message": "No account positions data available."}

    # Use first authenticated account's api_key to fetch option instruments
    ref_api_key = None
    for acct in accounts_positions:
        if acct.get("status") == "success" and acct.get("api_key"):
            ref_api_key = acct.get("api_key")
            break

    if not ref_api_key:
        return {"status": "error", "message": "No authenticated accounts available to fetch option database."}

    options = get_nifty_options(client, ref_api_key)
    if not options:
        return {"status": "error", "message": "Failed to fetch NFO options database."}

    # Find expiries (E0, E1, E2)
    today = datetime.date.today()
    all_expiries = sorted(
        set(
            inst["expiry"] for inst in options
            if isinstance(inst.get("expiry"), datetime.date) and inst["expiry"] >= today
        )
    )

    if len(all_expiries) < 3:
        return {"status": "error", "message": "Not enough NIFTY expiries found in database (need at least 3)."}

    E0 = all_expiries[0]
    E1 = all_expiries[1]
    E2 = all_expiries[2]

    plan["expiries"] = {
        "E0": E0.isoformat(),
        "E1": E1.isoformat(),
        "E2": E2.isoformat()
    }

    # If NIFTY spot isn't live yet, try to fetch it
    if nifty_spot is None or nifty_spot <= 0.0:
        try:
            indices = client.get_market_indices()
            nifty_spot = indices.get("nifty")
        except Exception:
            pass

    if not nifty_spot or nifty_spot <= 0.0:
        return {
            "status": "error",
            "message": "NIFTY index spot price is not available. Please verify connection/ticker status."
        }

    plan["nifty_spot"] = nifty_spot

    # Calculate strikes rounded to nearest 100
    strike_e1_ce = round((nifty_spot * 1.05) / 100) * 100
    strike_e1_pe = round((nifty_spot * 0.95) / 100) * 100
    strike_e2_ce = round((nifty_spot * 1.07) / 100) * 100
    strike_e2_pe = round((nifty_spot * 0.93) / 100) * 100

    plan["strikes"] = {
        "E1_CE": strike_e1_ce,
        "E1_PE": strike_e1_pe,
        "E2_CE": strike_e2_ce,
        "E2_PE": strike_e2_pe
    }

    # Resolve target symbols
    e1_ce_sym, _ = find_option_symbols(options, E1, strike_e1_ce)
    _, e1_pe_sym = find_option_symbols(options, E1, strike_e1_pe)
    e2_ce_sym, _ = find_option_symbols(options, E2, strike_e2_ce)
    _, e2_pe_sym = find_option_symbols(options, E2, strike_e2_pe)

    plan["symbols"] = {
        "E1_CE": e1_ce_sym,
        "E1_PE": e1_pe_sym,
        "E2_CE": e2_ce_sym,
        "E2_PE": e2_pe_sym
    }

    for acct in accounts_positions:
        api_key = acct.get("api_key")
        user_id = api_key_to_user_id.get(api_key, "UNKNOWN")
        name = acct.get("name", user_id)
        positions = acct.get("positions", [])

        # Fetch margin details (using live balance and collateral)
        margin_info = margins_by_api_key.get(api_key, {})
        cash = float(margin_info.get("cash") or 0.0)
        collateral = float(margin_info.get("collateral") or 0.0)
        total_capital = cash + collateral

        # Reserve 3 Lakhs buffer
        trading_capital = total_capital - 300000

        # Calculate lots under 50/50 split (1.3 Lakhs margin per strangle lot)
        if trading_capital > 0:
            alloc_per_week = 0.5 * trading_capital
            lots_e1 = int(alloc_per_week // 130000)
            lots_e2 = int(alloc_per_week // 130000)
        else:
            lots_e1 = 0
            lots_e2 = 0

        # Identify existing E0 and E1 positions to exit
        exits_e0 = []
        exits_e1 = []
        for pos in positions:
            symbol = pos.get("tradingsymbol", "")
            # Skip if closed
            if pos.get("quantity", 0) == 0:
                continue
            # Lookup instrument expiry
            inst = next((x for x in options if x.get("tradingsymbol") == symbol), None)
            if inst:
                exp = inst.get("expiry")
                if exp == E0:
                    exits_e0.append(symbol)
                elif exp == E1:
                    exits_e1.append(symbol)

        # Build Stage 1 command
        # Syntax: account <name> && exit <pos1> && exit <pos2> && sell <CE> <lots>L && sell <PE> <lots>L
        stage_1_parts = [f"account {name}"]
        
        # Add exit commands
        for sym in exits_e0:
            stage_1_parts.append(f"exit {sym}")
        for sym in exits_e1:
            stage_1_parts.append(f"exit {sym}")
            
        # Add new E1 entries if lots > 0 and symbols resolved
        if lots_e1 > 0:
            if e1_ce_sym:
                stage_1_parts.append(f"sell {e1_ce_sym} {lots_e1}L")
            if e1_pe_sym:
                stage_1_parts.append(f"sell {e1_pe_sym} {lots_e1}L")

        stage_1_cmd = " && ".join(stage_1_parts) if (len(stage_1_parts) > 1 or lots_e1 > 0) else ""

        # Build Stage 2 command
        stage_2_cmd = ""
        if lots_e2 > 0:
            stage_2_parts = [f"account {name}"]
            if e2_ce_sym:
                stage_2_parts.append(f"sell {e2_ce_sym} {lots_e2}L")
            if e2_pe_sym:
                stage_2_parts.append(f"sell {e2_pe_sym} {lots_e2}L")
            if len(stage_2_parts) > 1:
                stage_2_cmd = " && ".join(stage_2_parts)

        acct_plan = {
            "name": name,
            "user_id": user_id,
            "cash": cash,
            "collateral": collateral,
            "total_capital": total_capital,
            "trading_capital": trading_capital,
            "lots_e1": lots_e1,
            "lots_e2": lots_e2,
            "exits_e0": exits_e0,
            "exits_e1": exits_e1,
            "stage_1_cmd": stage_1_cmd,
            "stage_2_cmd": stage_2_cmd
        }
        plan["accounts"].append(acct_plan)

    return plan
