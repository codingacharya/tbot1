from kiteconnect import KiteConnect
import datetime
import config
import logging

# =====================================================
# LOGGING
# =====================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# =====================================================
# KITE SESSION
# =====================================================
kite = KiteConnect(api_key=config.API_KEY)
kite.set_access_token(config.ACCESS_TOKEN)

# =====================================================
# GLOBAL CACHE (to avoid repeated API hits)
# =====================================================
_INSTRUMENTS = None


def load_instruments():
    global _INSTRUMENTS
    if _INSTRUMENTS is None:
        _INSTRUMENTS = kite.instruments("NFO")
    return _INSTRUMENTS


# =====================================================
# GET NIFTY SPOT PRICE
# =====================================================
def get_nifty_spot():
    ltp = kite.ltp("NSE:NIFTY 50")
    return ltp["NSE:NIFTY 50"]["last_price"]


# =====================================================
# GET CURRENT WEEKLY EXPIRY
# =====================================================
def get_current_expiry():
    instruments = load_instruments()
    expiries = sorted(
        list({i["expiry"] for i in instruments if i["name"] == "NIFTY"})
    )
    return expiries[0]  # nearest expiry


# =====================================================
# OPTION SYMBOL RESOLUTION (ATM)
# =====================================================
def get_atm_option_symbol(side: str):
    """
    side = 'CALL' or 'PUT'
    """
    spot = get_nifty_spot()
    strike = round(spot / 50) * 50
    expiry = get_current_expiry()

    instruments = load_instruments()

    for ins in instruments:
        if (
            ins["name"] == "NIFTY"
            and ins["expiry"] == expiry
            and ins["strike"] == strike
            and ins["instrument_type"] == ("CE" if side == "CALL" else "PE")
        ):
            return ins["tradingsymbol"]

    raise Exception("Option symbol not found")


# =====================================================
# PLACE ENTRY ORDER
# =====================================================
def place_entry(side: str):
    symbol = get_atm_option_symbol(side)

    if not config.AUTO_TRADE:
        logging.info(f"PAPER ENTRY → {symbol}")
        return {"status": "paper", "symbol": symbol}

    order_id = kite.place_order(
        variety=kite.VARIETY_REGULAR,
        exchange=config.EXCHANGE,
        tradingsymbol=symbol,
        transaction_type=kite.TRANSACTION_TYPE_BUY,
        quantity=config.ORDER_QTY,
        product=config.PRODUCT,
        order_type=kite.ORDER_TYPE_MARKET,
    )

    logging.info(f"LIVE ENTRY → {symbol} | Order ID: {order_id}")
    return {"status": "live", "symbol": symbol, "order_id": order_id}


# =====================================================
# EXIT POSITION (MARKET)
# =====================================================
def exit_position(tradingsymbol: str, qty: int):
    if not config.AUTO_TRADE:
        logging.info(f"PAPER EXIT → {tradingsymbol}")
        return

    kite.place_order(
        variety=kite.VARIETY_REGULAR,
        exchange=config.EXCHANGE,
        tradingsymbol=tradingsymbol,
        transaction_type=kite.TRANSACTION_TYPE_SELL,
        quantity=qty,
        product=config.PRODUCT,
        order_type=kite.ORDER_TYPE_MARKET,
    )

    logging.info(f"LIVE EXIT → {tradingsymbol}")


# =====================================================
# FETCH OPEN POSITIONS
# =====================================================
def get_open_positions():
    positions = kite.positions()["net"]
    return [p for p in positions if p["quantity"] != 0]


# =====================================================
# AUTO EXIT LOGIC (CALLED FROM app.py)
# =====================================================
def auto_exit(exit_signal: bool):
    if not exit_signal:
        return

    positions = get_open_positions()
    for pos in positions:
        exit_position(pos["tradingsymbol"], abs(pos["quantity"]))


# =====================================================
# UTILITY: IS POSITION OPEN?
# =====================================================
def has_open_position():
    return len(get_open_positions()) > 0
