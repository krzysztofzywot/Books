import os
import requests

from flask import Flask, session, render_template, request, redirect, url_for, jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

from utils import login_required

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

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


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html", displayForm=True)
    else:
        # Get data
        username = request.form["username"].rstrip()
        password = request.form["password"].rstrip()
        pass_repeat = request.form["passRepeat"].rstrip()

        # Validate data
        username_exists = db.execute("SELECT username FROM users WHERE username = :username", {"username": username}).fetchone()

        if not username:
            return render_template("register.html", displayForm=True, alertUsername="You must enter your username!")
        elif username_exists:
            return render_template("register.html", displayForm=True, alertUsername="Username is already taken!")
        elif not password:
            return render_template("register.html", displayForm=True, alertPassword="You must enter your password!")
        elif len(password) < 8:
            return render_template("register.html", displayForm=True, alertPassword="Password must be at least 8 characters long!")
        elif not pass_repeat:
            return render_template("register.html", displayForm=True, alertPassRepeat="You must repeat your password!")
        elif password != pass_repeat:
            return render_template("register.html", displayForm=True, alertPassRepeat="Password do not match!")
        else:
            password_hash = generate_password_hash(password)
            # Insert data into database
            try:
                db.execute("INSERT INTO users (username, password) VALUES (:username, :password)",
                {"username": username, "password": password_hash})
                db.commit()
            except:
                return render_template("register.html", displayForm=True, alertUsername="There was a problem. Please try again later.")

            return render_template("register.html", displayForm=False, successMessage="You have been successfully registered \
            <b>" + username + "</b>.")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    else:
        # Get input data
        username = request.form["username"].rstrip()
        password = request.form["password"].rstrip()

        # Check database for the user
        verify_user = db.execute("SELECT id, username, password FROM users WHERE username = :username",
        {"username": username}).fetchone()

        if not verify_user or not check_password_hash(verify_user["password"], password):
            return render_template("login.html", error=True)
        else:
            # Remember which user has logged in
            session["user_id"] = verify_user["id"]
            session["username"] = verify_user["username"]

            return render_template("index.html")
        return "TODO"


@app.route("/logout")
def logout():
    session.clear()
    return render_template("index.html")


@app.route("/search", methods=["GET", "POST"])
def search():
    """Alow the user to search for a book"""
    if request.method == "GET":
        return render_template("search.html")
    else:
        isbn = request.form["isbn"].rstrip()
        author = request.form["author"].rstrip()
        title = request.form["title"].rstrip()

        if not isbn and not author and not title:
            return render_template("search.html", error=True)

        query = f'{isbn},{author},{title}'
        return redirect(url_for("search_results", query=query))


@app.route("/search/<query>")
def search_results(query):
    """Show table with book titles and authors for the selected query"""
    query = query.split(',')
    # Query user results
    values = {"isbn": f"%{query[0]}%".lower(), # Format values appropriately so that it can search with %
              "author": f"%{query[1]}%".lower(),
              "title": f"%{query[2]}%".lower()}
    results = db.execute("SELECT books.id, books.title, authors.name FROM books INNER JOIN authors ON books.author = authors.id WHERE LOWER(isbn) LIKE :isbn AND LOWER(title) LIKE :title \
    AND author IN (SELECT id FROM authors WHERE LOWER(name) LIKE :author)", values)
    if results.rowcount < 1: # If there are no results return None
        return render_template("search_results.html", query=None)

    return render_template("search_results.html", query=results)


@app.route("/book/<int:id>")
def book(id):
    """Show information about the book with selected id"""
    book = db.execute("SELECT * FROM books INNER JOIN authors ON books.author = authors.id WHERE books.id = :id", {"id": id}).fetchone()
    # Get user ratings and reviews
    reviews = db.execute("SELECT reviews.rating, reviews.review, reviews.date, users.username FROM reviews INNER JOIN users ON reviews.user_id = users.id \
    WHERE reviews.book_id = :book_id ORDER BY reviews.date DESC", {"book_id": id}).fetchall()
    # Calculate average ratings
    rating = db.execute("SELECT AVG(rating) as avg_rating, COUNT(*) as number_of_ratings FROM reviews WHERE book_id = :book_id", {"book_id": id}).fetchone()
    # Round average rating
    avg_rating = round(rating[0], 2)
    # Get GoodReads API ratings
    res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": "yiqSOwHn8Me1puvVuyFaQ", "isbns": book["isbn"]})
    if res.status_code != 200:
        return render_template("error.html", errorMessage="Couldn't read the api data.")
    else:
        gr_ratings_count = res.json()["books"][0]["ratings_count"]
        gr_avg_rating = res.json()["books"][0]["average_rating"]

    return render_template("book.html", book=book, id=id, reviews=reviews, avg_rating=avg_rating, number_of_ratings=rating[1], gr_avg_rating=gr_avg_rating, gr_number_of_ratings=gr_ratings_count)


@app.route("/book/<int:id>/review", methods=["GET", "POST"])
@login_required
def review(id):
    """Allow the user to submit rating and review for the book"""
    if request.method == "GET":
        # Check if user has already submitted a review for this book. If so, display an error message.
        check = db.execute("SELECT * FROM reviews WHERE user_id = :user_id AND book_id = :book_id",
        {"user_id": session["user_id"], "book_id": id}).fetchone()

        if check:
            return render_template("error.html", errorMessage="You have already submitted a review for this book.")
        else:
            return render_template("review.html", id=id)
    else:
        rating = int(request.form["rating"])
        review = request.form["review"].rstrip()

        if not review:
            return render_template("review.html", id=id, alert="You must type in your review.")

        # Sumbit the review into database
        db.execute("INSERT INTO reviews(rating, review, user_id, book_id) VALUES (:rating, :review, :user_id, :book_id)",
        {"rating": rating, "review": review, "user_id": session["user_id"], "book_id": id})
        db.commit()

        return redirect(url_for("book", id=id))


@app.route("/api/<isbn>")
def api(isbn):
    """Returns a JSON response containing the book’s title, author, publication date, ISBN number, review count, and average score"""
    book = db.execute("SELECT books.id, books.isbn, books.title, books.publication_year, authors.name as author FROM books INNER JOIN authors ON books.author = authors.id WHERE books.isbn = :isbn", {"isbn": isbn}).fetchone()
    if not book:
        return jsonify({"error": "book with that isbn was not found"}), 404
    else:
        reviews = db.execute("SELECT COUNT(*) as review_count, ROUND(AVG(rating), 2) as average_score FROM reviews WHERE book_id = :book_id", {"book_id": book[0]}).fetchone()
        if not reviews[1]: # If there are no reviews change null to 0
            reviews = (reviews[0], 0)
        return jsonify({"title": book[2], "author": book[4], "year": book[3], "isbn": book[1], "review_count": reviews[0], "average_score": reviews[1]})


@app.template_filter("datetimeformat")
def datetimeformat(value, format):
    return value.strftime(format)
