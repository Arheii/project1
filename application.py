import os

from flask import Flask, session, render_template, request
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    # Forget any user id
    session.clear()
    if request.method == "GET":
        return render_template("login.html", message="")

    # Request form
    email = request.form.get("email")
    password = request.form.get("password")
    if not all((email, password)):
        return render_template("login.html",  message="All fields must be filled"), 406

    # Check email is exist
    ans = db.execute("SELECT id, username, pass_hash FROM users WHERE email = :email",
                             {"email": email}).fetchone()
    if ans is None:
        print(f"ANS = {ans}")
        return render_template("login.html",  message="User not found")

    # Check password
    user_id, username, pass_hash = ans
    if not check_password_hash(pass_hash, password):
        return render_template("login.html",  message="Incorrect password")

    # Finish log in, write user to session
    session['user_id'], session['username'] = user_id, username
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def registration():
    session.clear()
    if request.method == "GET":
        return render_template("register.html", message="")

    email = request.form.get("email")
    password = request.form.get("password")
    username = request.form.get("username")
    if not all((email, password, username)):
        return render_template("register.html",  message="All fields must be filled"), 406

    # Check lenght of data
    if len(email) > 50 or len(password) > 128 or len(username) > 128:
        return render_template("register.html",  message="Too long, be shorter ^^"), 406

    # Email is exist
    if db.execute("SELECT id FROM users WHERE email = :email", {"email": email}).rowcount:
        return render_template("register.html",  message=f"{email} is busy, mb is it you?"), 406

    pass_hash = generate_password_hash(password)
    db.execute("INSERT INTO users (email, pass_hash, username) VALUES (:email, :pass_hash, :username)",
            {"email": email, "pass_hash": pass_hash, "username": username})
    db.commit()
    session['user_id'] = db.execute("SELECT id FROM users WHERE email = :email",
                             {"email": email}).fetchone()[0]
    session['username'] = username
    return render_template("index.html")


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return render_template("index.html")


@app.route("/result", methods=["GET"])
def result():
    q = request.args.get("q")
    print("query=", q)
    books = db.execute("SELECT * FROM books WHERE title LIKE :q OR isbn LIKE :q OR author LIKE :q LIMIT 30",
                             {"q": '%' + q + '%'}).fetchall()
    return render_template("result.html", books=books, q=q)