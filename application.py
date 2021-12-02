import os
import sqlite3
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

#DATABASE name for this app
DATABASE = './finance.db'

# Configure sqlite3 libraray to connect to Database, to return reponse in dict form rather than tuple
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

# Calculate share counts user owns using stockes database rows
def calc_shares(rows):
    scounts = {}
    for row in rows:
        if not scounts.get(row["symbol"], 0):
            scounts[row["symbol"]] = 0
        scounts[row["symbol"]] += row["shares"]
    return scounts

@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Connect to database to query for required information to display
    conn = get_db_connection() 
    cursor = conn.cursor()

    # Query database for current user's all transactions and integrate them in dict with symbol and total shares for the symbol
    cursor.execute("SELECT * FROM stockes WHERE user_id = (?)", [session["user_id"]])
    rows = cursor.fetchall()
    
    # Dict of share counts
    scounts = calc_shares(rows)

    # Total cash that user owns
    cursor.execute("SELECT cash FROM users WHERE username = (?)", [session["username"]])
    rows = cursor.fetchall()
    users_cash = rows[0]["cash"]
    
    # Lookup company name, current price for each symbol in user's transaction
    used_cash = 0
    result = []
    for symbol in scounts.keys():
        vals = lookup(symbol)
        obj = {}
        obj["name"] = vals["name"]
        obj["price"] = vals["price"]
        obj["symbol"] = symbol
        obj["shares"] = scounts[symbol]
        obj["total"] = vals["price"] * scounts[symbol]
        used_cash += obj["total"]  
        result.append(obj)   

    remain_cash = users_cash - used_cash
    total_cash = users_cash + used_cash

    conn.close()
    return render_template("index.html", result=result, remain_cash=remain_cash, total_cash=total_cash)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide symbol", 403)

        # Ensure shares were submitted
        elif not request.form.get("shares"):
            return apology("must provide shares", 403)

        res = lookup(request.form.get("symbol"))
        # Ensure shares submitted were positive integers

        if int(request.form.get("shares")) <= 0:
            return apology("must provide valid shares", 403)
        elif not res:
            return apology("must provide valid symbol", 403)

        current_share_price = float(res["price"])
        number_of_shares = int(request.form.get("shares"))

        # Connect to database
        conn = get_db_connection() 
        cursor = conn.cursor()
        cursor.execute("SELECT cash FROM users WHERE username = (?)", [session["username"]])
        rows = cursor.fetchall()

        # Check if user is eligible to buy stocks
        current_balance = int(rows[0]["cash"])
        if current_balance < current_share_price * number_of_shares:
            return apology("Sorry! You cannot afford the number of shares at the current price.", 400)
        
        symbol = res["symbol"]
        tdate = datetime.now().strftime('%Y/%m/%d %H:%M:%S')

        # Store new purchase data into database 
        cursor.execute("INSERT INTO stockes(symbol, shares, price, user_id, date) VALUES (?, ?, ?, ?, ?)", [symbol, number_of_shares, current_share_price, session["user_id"], tdate])
        conn.commit()

        remain_cash = current_balance -  (number_of_shares * current_share_price)

        # Make changes in user to show current available cash
        cursor.execute("UPDATE users SET cash = (?) WHERE id = (?)", [remain_cash, session["user_id"]])
        conn.commit()        

        conn.close()
        
        # Flash user message
        flash("Bought!")

        # Redirect user to index
        return redirect("/")    
    else:
        return render_template("buy.html")



@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Connect to database
    conn = get_db_connection() 
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM stockes WHERE user_id = (?)", [session["user_id"]])
    rows = cursor.fetchall()
    return render_template("history.html", rows=rows)
    
@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        conn = get_db_connection() 
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = (?)", [request.form.get("username")])
        rows = cursor.fetchall()
        conn.close()

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]
        session["username"] = rows[0]["username"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    if request.method == "GET":
        return render_template("quote.html")

    else:
        res = lookup(request.form.get("symbol"))

        # If symbol does not exits, render apology
        if not res:
            return apology("Symbol doesn't exit", 404)
        else:
            return render_template("quoted.html", res=res)

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":

        equal = request.form.get("password") == request.form.get("confirm_password")

        # Connect to database
        conn = get_db_connection() 
        cursor = conn.cursor()

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password and confirm password were submitted  and are equal
        elif not request.form.get("password") or not request.form.get("confirm_password") or not equal:
            return apology("must provide password", 403)
        
        username = request.form.get("username")
        hash = generate_password_hash(request.form.get("password"))

        # Check if username already exists
        cursor.execute("SELECT * FROM users WHERE username = (?)", [username])
        rows = cursor.fetchall()
        if len(rows) == 1:
            return apology("username already taken", 403)

        # Store new user's data into database 
        cursor.execute("INSERT INTO users (username, hash) VALUES (?, ?)", [username, hash])
        conn.commit()

        # Flash user message
        flash("Registered!")

        # Extract user'id to login
        cursor.execute("SELECT * FROM users WHERE username = (?)", [username])
        rows = cursor.fetchall()

        # Log user in and redirect to "/"
        session["user_id"] = rows[0]["id"]
        session["username"] = rows[0]["username"]

        conn.close()
        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "GET":
        # Connect to database
        conn = get_db_connection() 
        cursor = conn.cursor()

        # Query for stocks and shares for stocks that user owns
        cursor.execute("SELECT * FROM stockes WHERE user_id = (?)", [session["user_id"]])
        rows = cursor.fetchall()

        # Dict of share counts
        scounts = calc_shares(rows)

        # Send list of stockes that user owns
        stockes = list(scounts.keys())
        conn.close()
        return render_template("sell.html", stockes=stockes)
    else:
         # Connect to database
        conn = get_db_connection() 
        cursor = conn.cursor()

        # Query for stocks and shares for stocks that user owns
        cursor.execute("SELECT * FROM stockes WHERE user_id = (?)", [session["user_id"]])
        rows = cursor.fetchall()

        # Dict of share counts
        scounts = calc_shares(rows)
        
        share_to_sell = int(request.form.get("shares"))
        symbol = request.form.get("symbol")

        # Ensure symbol was submitted
        if not symbol:
            return apology("must provide symbol", 403)

        # Ensure shares were submitted
        elif not share_to_sell:
            return apology("must provide shares", 403)

        # Check shares count is positive and user owns <= share_count provided
        if share_to_sell <= 0 or share_to_sell > scounts[symbol]:
            return apology("must provide valid shares", 403)

        tdate = datetime.now().strftime('%Y/%m/%d %H:%M:%S')

        # Current cash available with user
        cursor.execute("SELECT cash FROM users WHERE id = (?)", [session["user_id"]])
        rows = cursor.fetchall()
        current_cash = rows[0]["cash"]

        current_price = lookup(symbol)["price"]
        remain_cash = share_to_sell * current_price + current_cash


        # Make changes to stockes database
        cursor.execute("INSERT INTO stockes(symbol, shares, price, user_id, date) VALUES (?, ?, ?, ?, ?)", [symbol, -share_to_sell, current_price, session["user_id"], tdate])
        conn.commit()

        # Make changes in user to show current available cash
        cursor.execute("UPDATE users SET cash = (?) WHERE id = (?)", [remain_cash, session["user_id"]])
        conn.commit()

        conn.close()

        # Flask message
        flash("Sold!")

        return redirect("/")
    
@app.route("/change_password", methods=["GET", "POST"])
def change_password():
    """ Change password """

    # User reached route via GET
    if request.method == "GET":
        return render_template("change_password.html")
        
    else:
        # User reached route via POST (as by submitting a form via POST)
        if request.method == "POST":

            # Ensure username was submitted
            if not request.form.get("username"):
                return apology("must provide username", 403)

            # Ensure new password was submitted
            elif not request.form.get("newpassword"):
                return apology("must provide new password", 403)

            # Ensure password was submitted
            elif not request.form.get("password"):
                return apology("must provide password", 403)

            # Query database for username
            conn = get_db_connection() 
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = (?)", [request.form.get("username")])
            rows = cursor.fetchall()

            # Ensure username exists and password is correct
            if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
                return apology("invalid username and/or password", 403)

            username = request.form.get("username")
            hash = generate_password_hash(request.form.get("newpassword"))

            # Store new password into database 
            cursor.execute("UPDATE users SET hash = (?) WHERE username = (?)", [hash, username])
            conn.commit()

            # Flash user message
            flash("Your password is changed!")

            # Redirect user to home page
            return redirect("/")

@app.route("/add_cash", methods=["GET", "POST"])
@login_required
def add_cash():
    """Add cash"""
    if request.method == "POST":

        # Ensure valid addcash was submitted
        if not request.form.get("addcash"):
            return apology("must provide value", 403)
        elif int(request.form.get("addcash")) <= 0:
            return apology("must provide valid value", 403)

        # Connect to database
        conn = get_db_connection() 
        cursor = conn.cursor()

        # Extract current cash value for this user
        cursor.execute("SELECT cash FROM users WHERE username = (?)", [session["username"]])
        rows = cursor.fetchall()

        current_cash = rows[0]["cash"]
        updated_cash = current_cash + int(request.form.get("addcash"))

        # Store new cash data into user's into database 
        cursor.execute("UPDATE users SET cash = (?) WHERE username = (?)", [updated_cash, session["username"]])
        conn.commit()
        conn.close()
        return redirect("/")
    else:
        return render_template("add_cash.html")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
