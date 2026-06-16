from flask import Flask, render_template, request, jsonify, session, redirect
import yfinance as yf
import json
import os
import math
from datetime import datetime, timedelta
import anthropic
from dotenv import load_dotenv

from gamification import update_streak, award_xp, get_gamification_data
from nse_stocks import NSE_STOCK_NAMES

load_dotenv()

app = Flask(__name__)
app.secret_key = "finlit-family-secret-2024"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
STARTING_BALANCE = 100000
_movers_cache = {"data": None, "time": None}

from db import load_json, save_json

import time
import requests as req

_yf_session = req.Session()
_yf_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
})

def get_price(symbol, retries=2):
    for attempt in range(retries):
        try:
            ticker = yf.Ticker(symbol + ".NS", session=_yf_session)
            data = ticker.history(period="1d")
            if not data.empty:
                return round(float(data["Close"].iloc[-1]), 2)
        except Exception as e:
            print(f"get_price attempt {attempt+1} failed for {symbol}:", e)
        if attempt < retries - 1:
            time.sleep(1)
    return None

def get_price_and_prev(symbol, retries=2):
    for attempt in range(retries):
        try:
            ticker = yf.Ticker(symbol + ".NS", session=_yf_session)
            hist = ticker.history(period="5d")
            if not hist.empty:
                closes = hist["Close"].dropna()
                if len(closes) >= 1:
                    current = round(float(closes.iloc[-1]), 2)
                    prev = round(float(closes.iloc[-2]), 2) if len(closes) > 1 else current
                    if not math.isnan(current) and not math.isnan(prev):
                        return current, prev
        except Exception as e:
            print(f"get_price_and_prev attempt {attempt+1} failed for {symbol}:", e)
        if attempt < retries - 1:
            time.sleep(1)
    return None, None

def get_ist_time():
    return datetime.utcnow() + timedelta(hours=5, minutes=30)

def is_market_open():
    now = get_ist_time()
    if now.weekday() >= 5:
        return False
    market_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close

@app.route("/api/market-status")
def api_market_status():
    open_now = is_market_open()
    now = get_ist_time()
    if open_now:
        msg = "Market is open — orders execute instantly"
    elif now.weekday() >= 5:
        msg = "Market closed (weekend) — orders will be placed as AMO and execute on next trading day"
    else:
        msg = "Market closed — orders will be placed as AMO (After Market Order) and execute when market opens at 9:00 AM"
    return jsonify({"open": open_now, "message": msg, "ist_time": now.strftime("%H:%M, %a")})

def get_portfolio_value(username):
    users = load_json("data/users.json")
    trades = load_json("data/trades.json")
    user = users.get(username, {})

    holdings = {}
    for trade in trades.get(username, []):
        sym = trade["symbol"]
        if sym not in holdings:
            holdings[sym] = {"qty": 0, "total_cost": 0}
        if trade["action"] == "buy":
            holdings[sym]["qty"] += trade["qty"]
            holdings[sym]["total_cost"] += trade["total"]
        else:
            if holdings[sym]["qty"] > 0:
                avg = holdings[sym]["total_cost"] / holdings[sym]["qty"]
                holdings[sym]["qty"] -= trade["qty"]
                holdings[sym]["total_cost"] -= avg * trade["qty"]

    portfolio_value = 0
    total_invested = 0
    day_pnl_total = 0
    holdings_detail = []

    for sym, data in holdings.items():
        if data["qty"] > 0:
            current, prev = get_price_and_prev(sym)
            if current is None or prev is None:
                continue
            if math.isnan(current) or math.isnan(prev):
                continue
            qty = data["qty"]
            invested = round(data["total_cost"], 2)
            avg_buy_price = round(data["total_cost"] / qty, 2)
            current_value = round(qty * current, 2)
            pnl = round(current_value - invested, 2)
            pnl_pct = round((pnl / invested) * 100, 2) if invested > 0 else 0
            day_change = round((current - prev) * qty, 2)
            day_change_pct = round(((current - prev) / prev) * 100, 2) if prev else 0

            portfolio_value += current_value
            total_invested += invested
            day_pnl_total += day_change

            holdings_detail.append({
                "symbol": sym,
                "qty": qty,
                "avg_buy_price": avg_buy_price,
                "current_price": current,
                "invested": invested,
                "current_value": current_value,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "day_change": day_change,
                "day_change_pct": day_change_pct
            })

    total_pnl = round(portfolio_value - total_invested, 2)
    total_pnl_pct = round((total_pnl / total_invested) * 100, 2) if total_invested > 0 else 0
    prev_day_value = portfolio_value - day_pnl_total
    day_pnl_pct = round((day_pnl_total / prev_day_value) * 100, 2) if prev_day_value > 0 else 0

    return {
        "cash": round(user.get("balance", STARTING_BALANCE), 2),
        "portfolio_value": round(portfolio_value, 2),
        "total": round(user.get("balance", STARTING_BALANCE) + portfolio_value, 2),
        "total_invested": round(total_invested, 2),
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "day_pnl": round(day_pnl_total, 2),
        "day_pnl_pct": day_pnl_pct,
        "holdings": holdings_detail
    }

STOCK_UNIVERSE = {
    "RELIANCE": {"name": "Reliance Industries", "cap": "large"},
    "TCS": {"name": "Tata Consultancy Services", "cap": "large"},
    "HDFCBANK": {"name": "HDFC Bank", "cap": "large"},
    "ICICIBANK": {"name": "ICICI Bank", "cap": "large"},
    "INFY": {"name": "Infosys Ltd", "cap": "large"},
    "ITC": {"name": "ITC Limited", "cap": "large"},
    "SBIN": {"name": "State Bank of India", "cap": "large"},
    "BHARTIARTL": {"name": "Bharti Airtel", "cap": "large"},
    "HINDUNILVR": {"name": "Hindustan Unilever", "cap": "large"},
    "LT": {"name": "Larsen and Toubro", "cap": "large"},

    "WIPRO": {"name": "Wipro Ltd", "cap": "mid"},
    "TATAMOTORS": {"name": "Tata Motors", "cap": "mid"},
    "FEDERALBNK": {"name": "Federal Bank", "cap": "mid"},
    "IDFCFIRSTB": {"name": "IDFC First Bank", "cap": "mid"},
    "GODREJPROP": {"name": "Godrej Properties", "cap": "mid"},
    "AUROPHARMA": {"name": "Aurobindo Pharma", "cap": "mid"},
    "MPHASIS": {"name": "Mphasis Ltd", "cap": "mid"},
    "COFORGE": {"name": "Coforge Ltd", "cap": "mid"},
    "IRCTC": {"name": "Indian Railway Catering and Tourism", "cap": "mid"},
    "PAGEIND": {"name": "Page Industries", "cap": "mid"},

    "TANLA": {"name": "Tanla Platforms", "cap": "small"},
    "HAPPSTMNDS": {"name": "Happiest Minds Technologies", "cap": "small"},
    "CAMS": {"name": "Computer Age Management Services", "cap": "small"},
    "ROUTE": {"name": "Route Mobile", "cap": "small"},
    "CDSL": {"name": "Central Depository Services", "cap": "small"},
    "SUZLON": {"name": "Suzlon Energy", "cap": "small"},
    "YESBANK": {"name": "Yes Bank", "cap": "small"},
    "IDEA": {"name": "Vodafone Idea", "cap": "small"},
    "RAILTEL": {"name": "RailTel Corporation", "cap": "small"},
    "METROPOLIS": {"name": "Metropolis Healthcare", "cap": "small"}
}
STOCK_NAMES = {**NSE_STOCK_NAMES, **{sym: info["name"] for sym, info in STOCK_UNIVERSE.items()}}

STOCK_TAKES = {
    "RELIANCE": "India's largest company by market cap, spanning oil, telecom (Jio), and retail. Considered relatively stable for beginners due to its size and diversification.",
    "TCS": "India's largest IT services company. Earns most revenue from global clients in dollars. IT stocks are sensitive to the US economy and rupee-dollar movements.",
    "INFY": "India's second largest IT company. Similar drivers to TCS — global demand for tech services and currency movements affect its performance.",
    "HDFCBANK": "One of India's most trusted private banks, known for consistent growth. Banking stocks are sensitive to RBI interest rate decisions.",
    "ICICIBANK": "A large private bank with strong digital banking presence. Like HDFC Bank, performance is linked to interest rates and loan growth.",
    "SBIN": "India's largest public sector bank. Often more volatile than private banks but benefits from government backing and large market share.",
    "ITC": "A diversified company spanning cigarettes, FMCG, hotels, and paper. Known for steady dividends — popular among conservative investors.",
    "WIPRO": "A major IT services company, smaller than TCS and Infosys. Similar sector dynamics — global tech spending drives its growth.",
    "TATAMOTORS": "Owns Jaguar Land Rover and is a major player in Indian commercial and electric vehicles. More volatile — linked to auto sector cycles.",
    "BHARTIARTL": "India's second largest telecom operator. Telecom stocks are influenced by subscriber growth, tariffs, and competition with Jio."
}

def get_stock_stats(symbol):
    try:
        ticker = yf.Ticker(symbol + ".NS")
        info = ticker.info
        hist = ticker.history(period="6mo")
        if hist.empty:
            return None
        return {
            "symbol": symbol,
            "name": STOCK_NAMES.get(symbol, info.get("longName", symbol)),
            "current_price": round(float(hist["Close"].iloc[-1]), 2),
            "prev_close": round(info.get("previousClose", 0) or 0, 2),
            "open": round(info.get("open", 0) or 0, 2),
            "day_high": round(info.get("dayHigh", 0) or 0, 2),
            "day_low": round(info.get("dayLow", 0) or 0, 2),
            "year_high": round(info.get("fiftyTwoWeekHigh", 0) or 0, 2),
            "year_low": round(info.get("fiftyTwoWeekLow", 0) or 0, 2),
            "pe_ratio": round(info.get("trailingPE", 0), 2) if info.get("trailingPE") else None,
            "chart_data": [round(float(p), 2) for p in hist["Close"].tail(30).tolist()],
            "chart_dates": [d.strftime("%d %b") for d in hist.index[-30:]],
            "ai_take": STOCK_TAKES.get(symbol, "This stock is not in our quick-reference list yet, but you can research it on the company's investor relations page.")
        }
    except Exception as e:
        print("Error fetching stock stats:", e)
        return None

def execute_trade(username, symbol, action, qty, price):
    users = load_json("data/users.json")
    trades = load_json("data/trades.json")
    user = users[username]
    total_cost = price * qty

    if action == "buy":
        if user["balance"] < total_cost:
            return {"error": f"Insufficient funds. Need ₹{total_cost:,.2f}"}
        user["balance"] -= total_cost
    elif action == "sell":
        holdings = {}
        for t in trades.get(username, []):
            sym = t["symbol"]
            q = t["qty"] if t["action"] == "buy" else -t["qty"]
            holdings[sym] = holdings.get(sym, 0) + q
        if holdings.get(symbol, 0) < qty:
            return {"error": f"You don't hold {qty} shares of {symbol}"}
        user["balance"] += total_cost
    else:
        return {"error": "Action must be buy or sell"}

    trades[username].append({
        "symbol": symbol,
        "action": action,
        "qty": qty,
        "price": price,
        "total": total_cost,
        "time": datetime.now().isoformat(),
        "status": "executed"
    })

    save_json("data/users.json", users)
    save_json("data/trades.json", trades)

    award_xp(username, 15)

    return {
        "success": True,
        "message": f"{'Bought' if action == 'buy' else 'Sold'} {qty} shares of {symbol} at ₹{price}",
        "new_balance": round(user["balance"], 2)
    }

def load_pending_orders():
    return load_json("data/pending_orders.json")

def save_pending_orders(data):
    save_json("data/pending_orders.json", data)

def get_next_market_close(created_at_str):
    """Return the datetime of the next market close after an order was created."""
    created = datetime.fromisoformat(created_at_str)
    candidate = created.replace(hour=15, minute=30, second=0, microsecond=0)
    if created.hour >= 15 and created.minute >= 30:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate

def get_same_day_market_close(created_at_str):
    """Return 3:30 PM on the same calendar day the order was created."""
    created = datetime.fromisoformat(created_at_str)
    return created.replace(hour=15, minute=30, second=0, microsecond=0)

def check_pending_orders(username):
    pending = load_pending_orders()
    user_orders = pending.get(username, [])
    if not user_orders:
        return []

    executed = []
    market_open_now = is_market_open()
    now = get_ist_time().replace(tzinfo=None)

    for order in user_orders:
        if order["status"] != "pending":
            continue

        if order["order_type"] == "amo":
            expiry = get_next_market_close(order["created_at"])
            if now > expiry:
                order["status"] = "expired"
                continue
        else:
            same_day_close = get_same_day_market_close(order["created_at"])
            if now > same_day_close:
                order["status"] = "expired"
                continue

        triggered = False
        exec_price = None

        if order["order_type"] == "amo":
            if market_open_now:
                exec_price = get_price(order["symbol"])
                if exec_price is not None:
                    triggered = True
        else:
            current_price = get_price(order["symbol"])
            if current_price is None:
                continue
            exec_price = current_price
            if order["order_type"] == "limit":
                if order["action"] == "buy" and current_price <= order["trigger_price"]:
                    triggered = True
                elif order["action"] == "sell" and current_price >= order["trigger_price"]:
                    triggered = True
            elif order["order_type"] == "stoploss":
                if order["action"] == "sell" and current_price <= order["trigger_price"]:
                    triggered = True

        if triggered and exec_price is not None:
            result = execute_trade(username, order["symbol"], order["action"], order["qty"], exec_price)
            if result.get("success"):
                order["status"] = "executed"
                order["executed_price"] = exec_price
                order["executed_at"] = datetime.now().isoformat()
                executed.append(order)

    pending[username] = user_orders
    save_pending_orders(pending)
    return executed

@app.route("/")
def index():
    if "user" in session:
        return redirect("/dashboard")
    return render_template("index.html")

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    users = load_json("data/users.json")
    name = data.get("name", "").strip().lower()
    pin = data.get("pin", "").strip()

    if name in users and users[name]["pin"] == pin:
        session["user"] = name
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Wrong name or PIN"})

@app.route("/register", methods=["POST"])
def register():
    data = request.json
    users = load_json("data/users.json")
    name = data.get("name", "").strip().lower()
    pin = data.get("pin", "").strip()
    recovery_answer = data.get("recovery_answer", "").strip().lower()

    if name in users:
        return jsonify({"success": False, "error": "Name already taken"})
    if len(pin) < 4:
        return jsonify({"success": False, "error": "PIN must be 4+ digits"})
    if not recovery_answer:
        return jsonify({"success": False, "error": "Please answer the recovery question"})

    users[name] = {
        "pin": pin,
        "recovery_answer": recovery_answer,
        "balance": STARTING_BALANCE,
        "joined": datetime.now().isoformat(),
        "watchlist": []
    }
    save_json("data/users.json", users)

    trades = load_json("data/trades.json")
    trades[name] = []
    save_json("data/trades.json", trades)

    session["user"] = name
    return jsonify({"success": True})

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")
@app.route("/api/recover-check", methods=["POST"])
def api_recover_check():
    data = request.json
    name = data.get("name", "").strip().lower()
    answer = data.get("answer", "").strip().lower()

    users = load_json("data/users.json")
    if name not in users:
        return jsonify({"success": False, "error": "No account found with that name"})

    stored_answer = users[name].get("recovery_answer", "")
    if not stored_answer:
        return jsonify({"success": False, "error": "This account has no recovery answer set. Please contact Akshit."})

    if stored_answer != answer:
        return jsonify({"success": False, "error": "That answer doesn't match our records"})

    return jsonify({"success": True})

@app.route("/api/reset-pin", methods=["POST"])
def api_reset_pin():
    data = request.json
    name = data.get("name", "").strip().lower()
    answer = data.get("answer", "").strip().lower()
    new_pin = data.get("new_pin", "").strip()

    users = load_json("data/users.json")
    if name not in users:
        return jsonify({"success": False, "error": "No account found with that name"})

    stored_answer = users[name].get("recovery_answer", "")
    if stored_answer != answer:
        return jsonify({"success": False, "error": "Recovery answer does not match"})

    if len(new_pin) < 4:
        return jsonify({"success": False, "error": "New PIN must be 4+ digits"})

    users[name]["pin"] = new_pin
    save_json("data/users.json", users)
    return jsonify({"success": True})

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")
    return render_template("dashboard.html", username=session["user"])

@app.route("/learn")
def learn():
    if "user" not in session:
        return redirect("/")
    return render_template("learn.html", username=session["user"])
@app.route("/about")
def about():
    if "user" in session:
        return render_template("about.html", username=session["user"], logged_in=True)
    return render_template("about.html", username=None, logged_in=False)

@app.route("/api/portfolio")
def api_portfolio():
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401
    return jsonify(get_portfolio_value(session["user"]))

@app.route("/api/gamification")
def api_gamification():
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401
    username = session["user"]
    streak, xp_awarded = update_streak(username)
    data = get_gamification_data(username)
    data["xp_awarded_today"] = xp_awarded
    return jsonify(data)

@app.route("/api/price/<symbol>")
def api_price(symbol):
    price = get_price(symbol.upper())
    if price:
        return jsonify({"price": price, "symbol": symbol.upper()})
    return jsonify({"error": "Symbol not found"}), 404
@app.route("/api/trade", methods=["POST"])
def api_trade():
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.json
    username = session["user"]
    symbol = data.get("symbol", "").upper()
    action = data.get("action")
    qty = int(data.get("qty", 0))

    if qty <= 0:
        return jsonify({"error": "Quantity must be positive"})

    price = get_price(symbol)
    if not price:
        return jsonify({"error": f"Could not get price for {symbol}"})

    if action not in ["buy", "sell"]:
        return jsonify({"error": "Action must be buy or sell"})

    if not is_market_open():
        if action == "sell":
            portfolio = get_portfolio_value(username)
            held = next((h["qty"] for h in portfolio["holdings"] if h["symbol"] == symbol), 0)
            if held < qty:
                return jsonify({"error": f"You only hold {held} shares of {symbol}"})

        pending = load_pending_orders()
        if username not in pending:
            pending[username] = []

        order_id = f"{username}_{int(datetime.now().timestamp())}"
        pending[username].append({
            "id": order_id,
            "symbol": symbol,
            "action": action,
            "order_type": "amo",
            "trigger_price": price,
            "qty": qty,
            "status": "pending",
            "created_at": datetime.now().isoformat()
        })
        save_pending_orders(pending)

        return jsonify({
            "success": True,
            "amo": True,
            "message": f"Market is closed. Your {action.upper()} order for {qty} {symbol} has been placed as an After Market Order (AMO) and will execute when the market opens (Mon-Fri, 9:00 AM IST)."
        })

    result = execute_trade(username, symbol, action, qty, price)
    return jsonify(result)

@app.route("/api/leaderboard")
def api_leaderboard():
    users = load_json("data/users.json")
    board = []
    for name in users:
        pf = get_portfolio_value(name)
        board.append({
            "name": name.title(),
            "total": pf["total"],
            "gain": round(pf["total"] - STARTING_BALANCE, 2),
            "gain_pct": round((pf["total"] - STARTING_BALANCE) / STARTING_BALANCE * 100, 2)
        })
    board.sort(key=lambda x: x["total"], reverse=True)
    return jsonify(board)

@app.route("/api/ask-claude", methods=["POST"])
def ask_claude():
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.json
    question = data.get("question", "").lower()

    responses = {
        "pe ratio": "P/E ratio (Price to Earnings) tells you how much investors are paying for every rupee of a company's profit. A lower P/E can mean a stock is cheaper. Nifty 50 average P/E is around 20-22.",
        "what is": "Great question! Investing means putting your money to work so it grows over time. In the stock market, you buy a small piece of a company and benefit when that company grows.",
        "reliance": "Reliance Industries is India's largest company by market cap. It operates in oil, telecom (Jio), and retail. It is part of Nifty 50 and considered a relatively stable large-cap stock.",
        "tcs": "TCS (Tata Consultancy Services) is India's largest IT company. It earns most revenue from global clients. IT stocks tend to be affected by the US economy and rupee-dollar exchange rate.",
        "hdfc": "HDFC Bank is one of India's most trusted private sector banks. It is known for consistent growth and strong management. Banking stocks are sensitive to interest rate changes by RBI.",
        "nifty": "Nifty 50 is an index of India's top 50 companies listed on NSE. When people say 'the market is up', they usually mean Nifty went up. It is a good benchmark for your portfolio performance.",
        "sensex": "Sensex is BSE's index of top 30 Indian companies. It is older than Nifty and often moves in the same direction. Both are good indicators of overall market health.",
        "diversif": "Diversification means not putting all your money in one stock or sector. If you hold 10 different stocks across 5 sectors, one bad stock won't ruin your portfolio.",
        "stop loss": "A stop-loss is an automatic sell order triggered when a stock falls to a certain price. For example, buy at 100, set stop-loss at 90. This limits your maximum loss to 10 percent.",
        "limit order": "A limit order lets you set the exact price at which you want to buy or sell. Example, if Infosys is at 1500 but you want to buy only if it drops to 1400, you place a limit order at 1400.",
        "dividend": "A dividend is when a company shares its profits with shareholders. If you hold 100 shares and the company declares a 5 rupee dividend per share, you receive 500 rupees just for holding the stock.",
        "market cap": "Market cap equals share price multiplied by total number of shares. It tells you the total value of a company. Large-cap stocks above 20,000 crore are generally more stable than small-cap stocks.",
        "ipo": "IPO, or Initial Public Offering, is when a company lists on the stock exchange for the first time. Retail investors can apply for shares at the issue price before trading begins.",
        "mutual fund": "A mutual fund pools money from many investors and a professional fund manager invests it. It is a good option for beginners who don't want to pick individual stocks.",
        "sip": "SIP, or Systematic Investment Plan, means investing a fixed amount every month in a mutual fund. Even 500 rupees a month compounded over 20 years can create significant wealth.",
        "bull": "A bull market means stock prices are rising and investor confidence is high. India had a strong bull run from 2020 to 2024 post-COVID recovery.",
        "bear": "A bear market means stock prices are falling, usually by 20 percent or more from recent highs. Bear markets are temporary, every bear market in history has eventually recovered.",
        "inflation": "Inflation means the purchasing power of money reduces over time. If inflation is 6 percent and your savings account gives 4 percent, you are actually losing money in real terms. Investing helps beat inflation.",
        "rbi": "RBI, the Reserve Bank of India, controls interest rates and money supply. When RBI raises rates, borrowing becomes expensive and stock markets often fall. When RBI cuts rates, markets tend to rise.",
        "sebi": "SEBI, the Securities and Exchange Board of India, is the regulator of Indian stock markets. It protects investors and ensures fair trading. All brokers must be registered with SEBI.",
        "amo": "AMO stands for After Market Order. If you place a trade outside market hours (Mon-Fri 9:00 AM to 3:30 PM IST), it gets queued and automatically executes when the market opens next.",
        "market hours": "Indian stock markets (NSE and BSE) are open Monday to Friday, 9:00 AM to 3:30 PM IST. They are closed on weekends and public holidays."
    }

    reply = None
    for keyword, response in responses.items():
        if keyword in question:
            reply = response
            break

    if not reply:
        reply = ("Good question! Here are some topics I can explain right now: "
                 "PE ratio, diversification, stop-loss, limit order, dividend, "
                 "market cap, IPO, mutual fund, SIP, bull market, bear market, "
                 "inflation, RBI, SEBI, Nifty, Sensex, Reliance, TCS, HDFC, AMO, market hours. "
                 "Type any of these words to learn more!")

    return jsonify({"reply": reply})

@app.route("/orders")
def orders():
    if "user" not in session:
        return redirect("/")
    return render_template("orders.html", username=session["user"])

@app.route("/api/orders")
def api_orders():
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401

    username = session["user"]
    trades = load_json("data/trades.json")
    user_trades = trades.get(username, [])

    executed_orders = []
    for t in user_trades:
        executed_orders.append({
            "symbol": t["symbol"],
            "action": t["action"],
            "qty": t["qty"],
            "price": t["price"],
            "total": t["total"],
            "time": t["time"],
            "order_type": t.get("order_type", "market"),
            "status": "Executed"
        })

    check_pending_orders(username)
    pending = load_pending_orders()
    user_pending = pending.get(username, [])

    for o in user_pending:
        status_map = {
            "pending": "Placed",
            "executed": "Executed",
            "expired": "Expired",
            "cancelled": "Cancelled"
        }
        executed_orders.append({
            "id": o.get("id", ""),
            "symbol": o["symbol"],
            "action": o["action"],
            "qty": o["qty"],
            "price": o.get("executed_price") or o.get("trigger_price", 0),
            "total": o["qty"] * (o.get("executed_price") or o.get("trigger_price", 0)),
            "time": o.get("executed_at") or o["created_at"],
            "order_type": o["order_type"],
            "status": status_map.get(o["status"], o["status"].title())
        })

    executed_orders.sort(key=lambda x: x["time"], reverse=True)
    return jsonify(executed_orders)

@app.route("/watchlist")
def watchlist():
    if "user" not in session:
        return redirect("/")
    return render_template("watchlist.html", username=session["user"])

@app.route("/api/watchlist", methods=["GET"])
def api_get_watchlist():
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401
    users = load_json("data/users.json")
    user = users.get(session["user"], {})
    symbols = user.get("watchlist", [])

    result = []
    for sym in symbols:
        current, prev = get_price_and_prev(sym)

        if current is None or math.isnan(current):
            current = get_price(sym)

        if current is None or math.isnan(current):
            continue

        if prev is None or math.isnan(prev) or prev == 0:
            change_pct = 0
            change_val = 0
        else:
            change_pct = round(((current - prev) / prev) * 100, 2)
            change_val = round(current - prev, 2)

        result.append({
            "symbol": sym,
            "name": STOCK_NAMES.get(sym, sym),
            "price": round(current, 2),
            "change_pct": change_pct,
            "change_val": change_val
        })
    return jsonify(result)

@app.route("/api/watchlist/add", methods=["POST"])
def api_add_watchlist():
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json
    symbol = data.get("symbol", "").upper().strip()

    price = get_price(symbol)
    if not price:
        return jsonify({"error": f"Could not find stock {symbol}"})

    users = load_json("data/users.json")
    user = users[session["user"]]
    if "watchlist" not in user:
        user["watchlist"] = []
    if symbol not in user["watchlist"]:
        user["watchlist"].append(symbol)
        save_json("data/users.json", users)
        award_xp(session["user"], 5)
    else:
        save_json("data/users.json", users)
    return jsonify({"success": True})

@app.route("/api/watchlist/remove", methods=["POST"])
def api_remove_watchlist():
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json
    symbol = data.get("symbol", "").upper().strip()

    users = load_json("data/users.json")
    user = users[session["user"]]
    if "watchlist" in user and symbol in user["watchlist"]:
        user["watchlist"].remove(symbol)
    save_json("data/users.json", users)
    return jsonify({"success": True})
@app.route("/api/search-stocks")
def api_search_stocks():
    q = request.args.get("q", "").upper().strip()
    if not q or len(q) < 2:
        return jsonify([])

    results = []
    seen = set()

    for sym, info in STOCK_UNIVERSE.items():
        if q in sym or q in info["name"].upper():
            results.append({"symbol": sym, "name": info["name"], "cap": info["cap"]})
            seen.add(sym)

    for sym, name in NSE_STOCK_NAMES.items():
        if sym in seen:
            continue
        if q in sym or q in name.upper():
            results.append({"symbol": sym, "name": name, "cap": "other"})
            seen.add(sym)
        if len(results) >= 30:
            break

    results.sort(key=lambda x: (not x["symbol"].startswith(q), len(x["symbol"]), x["symbol"]))
    return jsonify(results[:10])

@app.route("/api/market-movers")
def api_market_movers():
    now = datetime.now()
    if _movers_cache["data"] and _movers_cache["time"] and (now - _movers_cache["time"]).seconds < 300:
        return jsonify(_movers_cache["data"])

    categories = {"large": [], "mid": [], "small": []}
    for sym, info in STOCK_UNIVERSE.items():
        current, prev = get_price_and_prev(sym)
        if current is None or prev is None:
            continue
        if math.isnan(current) or math.isnan(prev) or prev == 0:
            continue
        change_pct = round(((current - prev) / prev) * 100, 2)
        categories[info["cap"]].append({
            "symbol": sym, "name": info["name"], "price": round(current, 2), "change_pct": change_pct
        })

    result = {}
    for cap, stocks in categories.items():
        if not stocks:
            result[cap] = {"gainer": None, "loser": None}
            continue
        gainer = max(stocks, key=lambda x: x["change_pct"])
        loser = min(stocks, key=lambda x: x["change_pct"])
        result[cap] = {"gainer": gainer, "loser": loser}

    _movers_cache["data"] = result
    _movers_cache["time"] = now
    return jsonify(result)
@app.route("/stock/<symbol>")
def stock_detail(symbol):
    if "user" not in session:
        return redirect("/")
    return render_template("stock.html", username=session["user"], symbol=symbol.upper())

@app.route("/api/stock/<symbol>")
def api_stock_detail(symbol):
    stats = get_stock_stats(symbol.upper())
    if not stats:
        return jsonify({"error": "Could not fetch stock data"}), 404
    return jsonify(stats)

@app.route("/api/place-order", methods=["POST"])
def api_place_order():
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.json
    username = session["user"]
    symbol = data.get("symbol", "").upper()
    action = data.get("action")
    order_type = data.get("order_type")
    trigger_price = float(data.get("trigger_price", 0))
    qty = int(data.get("qty", 0))

    if qty <= 0 or trigger_price <= 0:
        return jsonify({"error": "Enter valid quantity and trigger price"})

    if order_type not in ["limit", "stoploss"]:
        return jsonify({"error": "Invalid order type"})

    if order_type == "stoploss" and action != "sell":
        return jsonify({"error": "Stop-loss orders are only for selling"})

    if action == "sell":
        portfolio = get_portfolio_value(username)
        held = next((h["qty"] for h in portfolio["holdings"] if h["symbol"] == symbol), 0)
        if held < qty:
            return jsonify({"error": f"You only hold {held} shares of {symbol}"})

    pending = load_pending_orders()
    if username not in pending:
        pending[username] = []

    order_id = f"{username}_{int(datetime.now().timestamp())}"
    pending[username].append({
        "id": order_id,
        "symbol": symbol,
        "action": action,
        "order_type": order_type,
        "trigger_price": trigger_price,
        "qty": qty,
        "status": "pending",
        "created_at": datetime.now().isoformat()
    })
    save_pending_orders(pending)

    label = "Limit" if order_type == "limit" else "Stop-loss"
    return jsonify({"success": True, "message": f"{label} order placed: {action.upper()} {qty} {symbol} @ Rs {trigger_price}"})

@app.route("/api/pending-orders")
def api_pending_orders():
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401

    username = session["user"]
    executed = check_pending_orders(username)

    pending = load_pending_orders()
    user_orders = pending.get(username, [])
    pending_list = [o for o in user_orders if o["status"] == "pending"]

    for o in pending_list:
        o["current_price"] = get_price(o["symbol"])

    return jsonify({"pending": pending_list, "executed_now": executed})

@app.route("/api/cancel-order", methods=["POST"])
def api_cancel_order():
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.json
    order_id = data.get("id")
    username = session["user"]

    pending = load_pending_orders()
    user_orders = pending.get(username, [])
    for o in user_orders:
        if o["id"] == order_id:
            o["status"] = "cancelled"
    pending[username] = user_orders
    save_pending_orders(pending)

    return jsonify({"success": True})

@app.route("/positions")
def positions():
    if "user" not in session:
        return redirect("/")
    return render_template("positions.html", username=session["user"])

@app.route("/api/positions")
def api_positions():
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401

    username = session["user"]
    trades = load_json("data/trades.json")
    user_trades = trades.get(username, [])

    today = datetime.now().date()
    today_trades = [t for t in user_trades if datetime.fromisoformat(t["time"]).date() == today]

    positions_data = {}
    for t in today_trades:
        sym = t["symbol"]
        if sym not in positions_data:
            positions_data[sym] = {"buy_qty": 0, "buy_value": 0, "sell_qty": 0, "sell_value": 0}
        if t["action"] == "buy":
            positions_data[sym]["buy_qty"] += t["qty"]
            positions_data[sym]["buy_value"] += t["total"]
        else:
            positions_data[sym]["sell_qty"] += t["qty"]
            positions_data[sym]["sell_value"] += t["total"]

    result = []
    for sym, p in positions_data.items():
        net_qty = p["buy_qty"] - p["sell_qty"]
        current_price = get_price(sym) or 0

        realized_pnl = 0
        if p["sell_qty"] > 0 and p["buy_qty"] > 0:
            avg_buy = p["buy_value"] / p["buy_qty"]
            realized_pnl = round(p["sell_value"] - (avg_buy * p["sell_qty"]), 2)

        unrealized_pnl = 0
        if net_qty > 0:
            avg_buy = p["buy_value"] / p["buy_qty"]
            unrealized_pnl = round((current_price - avg_buy) * net_qty, 2)
        elif net_qty < 0:
            avg_sell = p["sell_value"] / p["sell_qty"]
            unrealized_pnl = round((avg_sell - current_price) * abs(net_qty), 2)

        result.append({
            "symbol": sym,
            "net_qty": net_qty,
            "buy_qty": p["buy_qty"],
            "sell_qty": p["sell_qty"],
            "current_price": current_price,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "total_pnl": round(realized_pnl + unrealized_pnl, 2)
        })

    return jsonify(result)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
