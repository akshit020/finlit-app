from flask import Flask, render_template, request, jsonify, session, redirect
import yfinance as yf
import json
import os
from datetime import datetime
import anthropic
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = "finlit-family-secret-2024"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
STARTING_BALANCE = 100000

# ─── helpers ──────────────────────────────────────────────────────────────────

def load_json(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return {}
    with open(path) as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def get_price(symbol):
    """Fetch live price from Yahoo Finance. NSE stocks need .NS suffix."""
    try:
        ticker = yf.Ticker(symbol + ".NS")
        data = ticker.history(period="1d")
        if data.empty:
            return None
        return round(float(data["Close"].iloc[-1]), 2)
    except:
        return None
def get_price_and_prev(symbol):
    """Get current price and previous day's close — needed for day's P&L."""
    try:
        ticker = yf.Ticker(symbol + ".NS")
        hist = ticker.history(period="5d")
        if hist.empty:
            return None, None
        current = round(float(hist["Close"].iloc[-1]), 2)
        prev = round(float(hist["Close"].iloc[-2]), 2) if len(hist) > 1 else current
        return current, prev
    except:
        return None, None

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
            if current is None:
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
# ─── routes ───────────────────────────────────────────────────────────────────

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
    
    if name in users:
        return jsonify({"success": False, "error": "Name already taken"})
    if len(pin) < 4:
        return jsonify({"success": False, "error": "PIN must be 4+ digits"})
    
    users[name] = {
        "pin": pin,
        "balance": STARTING_BALANCE,
        "joined": datetime.now().isoformat()
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

@app.route("/api/portfolio")
def api_portfolio():
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401
    return jsonify(get_portfolio_value(session["user"]))

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
    action = data.get("action")  # "buy" or "sell"
    qty = int(data.get("qty", 0))
    
    if qty <= 0:
        return jsonify({"error": "Quantity must be positive"})
    
    price = get_price(symbol)
    if not price:
        return jsonify({"error": f"Could not get price for {symbol}"})
    
    users = load_json("data/users.json")
    trades = load_json("data/trades.json")
    user = users[username]
    total_cost = price * qty
    
    if action == "buy":
        if user["balance"] < total_cost:
            return jsonify({"error": f"Insufficient funds. Need ₹{total_cost:,.2f}"})
        user["balance"] -= total_cost
    elif action == "sell":
        # check if user holds enough
        holdings = {}
        for t in trades.get(username, []):
            sym = t["symbol"]
            q = t["qty"] if t["action"] == "buy" else -t["qty"]
            holdings[sym] = holdings.get(sym, 0) + q
        if holdings.get(symbol, 0) < qty:
            return jsonify({"error": f"You don't hold {qty} shares of {symbol}"})
        user["balance"] += total_cost
    else:
        return jsonify({"error": "Action must be buy or sell"})
    
    trades[username].append({
        "symbol": symbol,
        "action": action,
        "qty": qty,
        "price": price,
        "total": total_cost,
        "time": datetime.now().isoformat()
    })
    
    save_json("data/users.json", users)
    save_json("data/trades.json", trades)
    
    return jsonify({
        "success": True,
        "message": f"{'Bought' if action == 'buy' else 'Sold'} {qty} shares of {symbol} at ₹{price}",
        "new_balance": round(user["balance"], 2)
    })

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
    """Claude explains stock concepts, debriefs trades, answers questions."""
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.json
    question = data.get("question", "")
    context = data.get("context", "")  # optional trade context
    username = session["user"]
    
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    
    system_prompt = """You are FinSaathi, a friendly Indian financial literacy tutor.
You are helping Indian families learn about investing in a safe, virtual environment.
Keep responses short (3-5 sentences max), encouraging, and use simple language.
Use Indian context (NSE stocks, ₹ currency, Indian companies like Reliance, TCS, HDFC).
Never say 'buy this stock' as advice — always frame as education.
If asked about a trade the user made, explain what was good/bad about the decision educationally."""
    
    user_message = question
    if context:
        user_message = f"Context: {context}\n\nQuestion: {question}"
    
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",  # cheapest model, perfect for this
        max_tokens=300,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )
    
    return jsonify({"reply": message.content[0].text})
# ─── stock info helper ─────────────────────────────────────────────────────

STOCK_NAMES = {
    "RELIANCE": "Reliance Industries",
    "TCS": "Tata Consultancy Services",
    "INFY": "Infosys Ltd",
    "HDFCBANK": "HDFC Bank",
    "ICICIBANK": "ICICI Bank",
    "SBIN": "State Bank of India",
    "ITC": "ITC Limited",
    "WIPRO": "Wipro Ltd",
    "TATAMOTORS": "Tata Motors",
    "BHARTIARTL": "Bharti Airtel"
}

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
    """Get extended stats for a stock."""
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

# ─── watchlist routes ───────────────────────────────────────────────────────

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
        price = get_price(sym)
        if price:
            result.append({
                "symbol": sym,
                "name": STOCK_NAMES.get(sym, sym),
                "price": price
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

# ─── stock detail route ─────────────────────────────────────────────────────

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

if __name__ == "__main__":
    app.run(debug=True, port=5000)