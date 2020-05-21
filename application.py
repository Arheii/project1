import os

from flask import Flask, session, render_template, request, jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.security import check_password_hash, generate_password_hash
import requests

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
    # Check forms and create user in database
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
    # return result for search <list book>
    q = request.args.get("q").lower()
    p = request.args.get("p")
    if p is not None and p.isdigit():
        p = max(int(p), 1)
    else:
        p = 1
    print("p", p)
    books = db.execute("SELECT * FROM books WHERE LOWER(title) LIKE :q OR LOWER(isbn) LIKE :q OR LOWER(author) LIKE :q \
                      LIMIT 10 OFFSET :p",
                      {"q": '%' + q + '%', "p": 10 * (p-1)}).fetchall()
    max_p = db.execute("SELECT * FROM books WHERE LOWER(title) LIKE :q OR LOWER(isbn) LIKE :q OR LOWER(author) LIKE :q",
                      {"q": '%' + q + '%', "p": 10 * (p-1)}).rowcount
    return render_template("result.html", books=books, q=q, p=p, max_p=int(max_p/10) + 1)


@app.route("/book/<string:isbn>", methods=['GET', 'POST'])
def book(isbn):
    # return single book page, with info and reviews
    book = db.execute("SELECT * FROM books WHERE LOWER(isbn) = :isbn",
                     {"isbn": isbn.lower()}).fetchone()
    if book is None:
        return render_template("error.html", message=f"<h3>404</h3><br> Book with isbn={isbn} not found."), 404

    reviews = db.execute("SELECT reviews.*, users.username FROM reviews JOIN users \
                        ON reviews.user_id = users.id WHERE book_id = :id LIMIT 30",\
                        {"id": book.id}).fetchall()

    # Create variable if the user has already left a review
    user_ids = [review.user_id for review in reviews]
    user_id = session.get('user_id')
    if (user_id is not None) and (user_id in user_ids):
        is_left_review = True
    else:
        is_left_review = False

    # Get average rating from Goodread.com
    api_rews = lookup(isbn)

    # if user left review via 'POST'
    if request.method == "POST":
        rate = request.form.get("rate")
        review_text = request.form.get("review_text")

        if rate is None or rate not in '12345':
            return render_template("book.html", book=book, api_rews=api_rews, is_left_review=is_left_review, rate_err="Please rate first"), 406

        if is_left_review:
            return render_template("book.html", book=book, api_rews=api_rews, reviews=reviews, is_left_review=is_left_review, rate_err="You already left a review"), 406

        db.execute("INSERT INTO reviews (book_id, user_id, date, review_text, mark) \
                VALUES (:book_id, :user_id, now(), :review_text, :mark)",
                {"book_id": book.id, "user_id": user_id, "review_text": review_text, "mark": rate})
        db.commit()

        reviews = db.execute("SELECT reviews.*, users.username FROM reviews JOIN users \
                             ON reviews.user_id = users.id WHERE book_id = :id LIMIT 30 ",
                             {"id": book.id}).fetchall()
        is_left_review = True

    return render_template("book.html", book=book, api_rews=api_rews, reviews=reviews, is_left_review=is_left_review)


@app.route("/api/<string:isbn>", methods=['GET'])
def api(isbn):
    # return info about book in JSON
    book = db.execute("SELECT * FROM books WHERE LOWER(isbn) = :isbn",
                     {"isbn": isbn.lower()}).fetchone()
    if book is None:
        return render_template("error.html", message=f"<h3>404</h3><br> Book with isbn={isbn} not found."), 404

    reviews = db.execute("SELECT mark FROM reviews WHERE book_id = :id",
                         {"id": book.id}).fetchall()
    count = len(reviews)
    average = 0
    if count:
        average = sum(review.mark for review in reviews) / count

    ans = {"title": book.title,
           "author": book.author,
           "year": book.year,
           "isbn": book.isbn,
           "review_count": count,
           "average_score": average}
    return jsonify(ans)


def lookup(isbn):
    """Request to googleread, return average sqore of book"""
    # Contact API
    try:
        # print("zapros, isbn=", isbn)
        key = os.environ.get("GOODKEY_KEY")
        response = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": key, "isbns": isbn})
        response.raise_for_status()
    except requests.RequestException:
        return None

    # Parse response
    try:
        q = response.json()
        # print(q)
        return {
            "reviews_count": q["books"][0]['work_reviews_count'],
            "average_rating": float(q["books"][0]['average_rating'])
        }
    except (KeyError, TypeError, ValueError):
        return None