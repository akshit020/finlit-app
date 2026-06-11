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

def get_portfolio_value(username):
    """Calculate total portfolio value for a user."""
    users = load_json("data/users.json")
    trades = load_json("data/trades.json")
    user = users.get(username, {})
    holdings = {}
    
    for trade in trades.get(username, []):
        sym = trade["symbol"]
        qty = trade["qty"] if trade["action"] == "buy" else -trade["qty"]
        holdings[sym] = holdings.get(sym, 0) + qty
    
    portfolio_value = 0
    holdings_detail = []
    for sym, qty in holdings.items():
        if qty > 0:
            price = get_price(sym) or 0
            value = qty * price
            portfolio_value += value
            holdings_detail.append({
                "symbol": sym, "qty": qty,
                "price": price, "value": round(value, 2)
            })
    
    return {
        "cash": round(user.get("balance", STARTING_BALANCE), 2),
        "portfolio_value": round(portfolio_value, 2),
        "total": round(user.get("balance", STARTING_BALANCE) + portfolio_value, 2),
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

if __name__ == "__main__":
    app.run(debug=True, port=5000)