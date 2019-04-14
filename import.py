import csv
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

def main():
    f = open("books.csv", "r")
    reader = csv.reader(f)
    next(reader) # skip the headers

    for isbn, title, author, year in reader:
        # Check if author is already in the database
        query = db.execute("SELECT id FROM authors WHERE name = :author", {"author": author}).fetchone()

        if query:
            db.execute("INSERT INTO books (isbn, title, publication_year, author) VALUES (:isbn, :title, :publication_year, :author)",
            {"isbn": isbn, "title": title, "publication_year": year, "author": query["id"]})
        else:
            # Create a new record for the author
            db.execute("INSERT INTO authors (name) VALUES (:author)", {"author": author})
            db.commit()
            # Get the authors ID
            query = db.execute("SELECT id FROM authors WHERE name = :author", {"author": author}).fetchone()
            # Insert the book
            db.execute("INSERT INTO books (isbn, title, publication_year, author) VALUES (:isbn, :title, :publication_year, :author)",
            {"isbn": isbn, "title": title, "publication_year": year, "author": query["id"]})
            db.commit()

    f.close()


if __name__ == "__main__":
    main()
