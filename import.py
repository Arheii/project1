import os
import csv
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

with open("books.csv") as f:
    i = 0
    reader = csv.DictReader(f)
    for row in reader:
        db.execute("INSERT INTO books (isbn, title, author, year) VALUES (:isbn, :title, :author, :year) ",
                    {"isbn": row['isbn'], "title": row['title'], "author": row['author'], "year": int(row['year'])})
        i += 1
        if i % 100 == 0:
            print(f'step {i//100}')
            db.commit()

    db.commit()
