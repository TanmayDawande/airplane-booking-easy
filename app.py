import sqlite3
from datetime import datetime, timedelta
from flask import Flask, g, jsonify, request, render_template

app = Flask(__name__)
DB = "airline.db"


# ---------- database helpers ----------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_):
    con = g.pop("db", None)
    if con:
        con.close()


def query(sql, args=()):
    return [dict(r) for r in db().execute(sql, args).fetchall()]


def fail(msg, code=400):
    return jsonify(error=msg), code


def init_db():
    con = sqlite3.connect(DB)
    con.executescript(open("schema.sql").read())
    if con.execute("SELECT COUNT(*) FROM flight").fetchone()[0] == 0:
        base = datetime.now().replace(minute=0, second=0, microsecond=0)
        seed = [  # flight_no, origin, destination, days ahead, hour, price, seats
            ("AI101", "Chennai", "Delhi", 2, 6, 6500, 60),
            ("AI102", "Delhi", "Chennai", 3, 9, 6400, 60),
            ("6E205", "Chennai", "Mumbai", 2, 14, 4200, 40),
            ("6E310", "Mumbai", "Bengaluru", 4, 11, 3100, 40),
            ("UK512", "Bengaluru", "Kolkata", 5, 17, 5300, 50),
            ("AI340", "Chennai", "Bengaluru", 1, 8, 2400, 30),
        ]
        for no, o, d, days, hr, price, seats in seed:
            dep = (base + timedelta(days=days)).replace(hour=hr).strftime("%Y-%m-%d %H:%M")
            con.execute("INSERT INTO flight(flight_no,origin,destination,departure,price,total_seats) VALUES(?,?,?,?,?,?)",
                        (no, o, d, dep, price, seats))
        con.commit()
    con.close()


# ---------- pages ----------
@app.route("/")
def home():
    return render_template("index.html")


# ---------- flights ----------
@app.route("/api/flights")
def list_flights():
    # SELECT with LEFT JOIN + GROUP BY: seats left = total seats - confirmed bookings
    sql = """SELECT f.*, f.total_seats - COUNT(b.booking_id) AS available
             FROM flight f
             LEFT JOIN booking b ON b.flight_id = f.flight_id AND b.status = 'CONFIRMED'
             WHERE f.origin LIKE ? AND f.destination LIKE ? AND f.departure LIKE ?
             GROUP BY f.flight_id
             ORDER BY f.departure"""
    a = request.args
    return jsonify(query(sql, (f"%{a.get('origin','')}%", f"%{a.get('destination','')}%", f"{a.get('date','')}%")))


@app.route("/api/flights", methods=["POST"])
def add_flight():
    d = request.json
    try:
        db().execute("INSERT INTO flight(flight_no,origin,destination,departure,price,total_seats) VALUES(?,?,?,?,?,?)",
                     (d["flight_no"].strip().upper(), d["origin"].strip().title(), d["destination"].strip().title(),
                      d["departure"].replace("T", " "), int(d["price"]), int(d["total_seats"])))
        db().commit()
    except sqlite3.IntegrityError as e:
        return fail("Could not add flight. Check that the flight number is new, cities differ and numbers are positive.")
    except (KeyError, ValueError):
        return fail("Fill in all flight fields.")
    return jsonify(ok=True)


@app.route("/api/flights/<int:fid>", methods=["DELETE"])
def delete_flight(fid):
    try:
        db().execute("DELETE FROM flight WHERE flight_id = ?", (fid,))
        db().commit()
    except sqlite3.IntegrityError:
        return fail("This flight has bookings and cannot be deleted.")
    return jsonify(ok=True)


# ---------- bookings ----------
@app.route("/api/book", methods=["POST"])
def book():
    d = request.json
    name, email, phone = d.get("name", "").strip(), d.get("email", "").strip().lower(), d.get("phone", "").strip()
    fid = d.get("flight_id")
    if not name or "@" not in email or not (phone.isdigit() and len(phone) == 10):
        return fail("Enter a name, a valid email and a 10-digit phone number.")

    con = db()
    flight = con.execute("SELECT * FROM flight WHERE flight_id = ?", (fid,)).fetchone()
    if not flight:
        return fail("Flight not found.", 404)

    # Find the passenger by email, or create a new one
    p = con.execute("SELECT passenger_id FROM passenger WHERE email = ?", (email,)).fetchone()
    if p:
        pid = p["passenger_id"]
    else:
        pid = con.execute("INSERT INTO passenger(name,email,phone) VALUES(?,?,?)", (name, email, phone)).lastrowid

    if con.execute("SELECT 1 FROM booking WHERE passenger_id=? AND flight_id=? AND status='CONFIRMED'", (pid, fid)).fetchone():
        return fail("This passenger already has a confirmed booking on this flight.")

    # Give the lowest free seat number
    taken = {r["seat_no"] for r in con.execute("SELECT seat_no FROM booking WHERE flight_id=? AND status='CONFIRMED'", (fid,))}
    seat = next((n for n in range(1, flight["total_seats"] + 1) if n not in taken), None)
    if seat is None:
        return fail("This flight is full.")

    bid = con.execute("INSERT INTO booking(passenger_id,flight_id,seat_no) VALUES(?,?,?)", (pid, fid, seat)).lastrowid
    con.commit()
    return jsonify(booking_id=bid, seat_no=seat)


@app.route("/api/bookings")
def my_bookings():
    sql = """SELECT b.booking_id, b.seat_no, b.status, b.booked_at,
                    p.passenger_id, p.name, p.phone,
                    f.flight_no, f.origin, f.destination, f.departure, f.price
             FROM booking b
             JOIN passenger p ON p.passenger_id = b.passenger_id
             JOIN flight f    ON f.flight_id = b.flight_id
             WHERE p.email = ?
             ORDER BY b.booking_id DESC"""
    return jsonify(query(sql, (request.args.get("email", "").strip().lower(),)))


@app.route("/api/bookings/<int:bid>", methods=["DELETE"])
def cancel(bid):
    # UPDATE: cancelling frees the seat, but keeps the record for history
    cur = db().execute("UPDATE booking SET status='CANCELLED' WHERE booking_id=? AND status='CONFIRMED'", (bid,))
    db().commit()
    return jsonify(ok=True) if cur.rowcount else fail("Booking is already cancelled.")


@app.route("/api/passengers/<int:pid>", methods=["PUT"])
def update_passenger(pid):
    d = request.json
    name, phone = d.get("name", "").strip(), d.get("phone", "").strip()
    if not name or not (phone.isdigit() and len(phone) == 10):
        return fail("Enter a name and a 10-digit phone number.")
    db().execute("UPDATE passenger SET name=?, phone=? WHERE passenger_id=?", (name, phone, pid))
    db().commit()
    return jsonify(ok=True)


# ---------- report ----------
@app.route("/api/report")
def report():
    # Aggregation: confirmed bookings and revenue per flight
    sql = """SELECT f.flight_no, f.origin, f.destination, f.total_seats,
                    COUNT(b.booking_id) AS bookings,
                    COALESCE(SUM(f.price), 0) AS revenue
             FROM flight f
             LEFT JOIN booking b ON b.flight_id = f.flight_id AND b.status = 'CONFIRMED'
             GROUP BY f.flight_id
             ORDER BY revenue DESC"""
    return jsonify(query(sql))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
