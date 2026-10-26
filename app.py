from datetime import datetime, timedelta
import mysql.connector
from mysql.connector import IntegrityError
from flask import Flask, g, jsonify, request, render_template
from dotenv import load_dotenv
import os

app = Flask(__name__)

load_dotenv()
CONFIG = dict(host=os.getenv("DB_HOST"), user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"))


# ---------- database helpers ----------
def db():
    if "db" not in g:
        g.db = mysql.connector.connect(database="airline", **CONFIG)
    return g.db


@app.teardown_appcontext
def close_db(_):
    con = g.pop("db", None)
    if con:
        con.close()


def run(sql, args=()):
    cur = db().cursor(dictionary=True)
    cur.execute(sql, args)
    return cur


def query(sql, args=()):
    return run(sql, args).fetchall()


def one(sql, args=()):
    rows = query(sql, args)
    return rows[0] if rows else None


def fail(msg, code=400):
    return jsonify(error=msg), code


def init_db():
    con = mysql.connector.connect(**CONFIG)
    cur = con.cursor()
    for stmt in open("schema.sql").read().split(";"):   # create database + tables
        if stmt.strip():
            cur.execute(stmt)
    cur.execute("SELECT COUNT(*) FROM flight")
    if cur.fetchone()[0] == 0:
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
            cur.execute("INSERT INTO flight(flight_no,origin,destination,departure,price,total_seats) VALUES(%s,%s,%s,%s,%s,%s)",
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
             WHERE f.origin LIKE %s AND f.destination LIKE %s AND f.departure LIKE %s
             GROUP BY f.flight_id
             ORDER BY f.departure"""
    a = request.args
    return jsonify(query(sql, (f"%{a.get('origin','')}%", f"%{a.get('destination','')}%", f"{a.get('date','')}%")))


@app.route("/api/flights", methods=["POST"])
def add_flight():
    d = request.json
    try:
        origin, dest = d["origin"].strip().title(), d["destination"].strip().title()
        price, seats = int(d["price"]), int(d["total_seats"])
        if not d["flight_no"].strip() or not origin or not dest or not d["departure"]:
            raise KeyError
        if origin == dest or price <= 0 or seats <= 0:
            return fail("Cities must differ, and price and seats must be positive.")
        run("INSERT INTO flight(flight_no,origin,destination,departure,price,total_seats) VALUES(%s,%s,%s,%s,%s,%s)",
            (d["flight_no"].strip().upper(), origin, dest, d["departure"].replace("T", " ")[:16], price, seats))
        db().commit()
    except IntegrityError:
        return fail("This flight number already exists.")
    except (KeyError, ValueError):
        return fail("Fill in all flight fields.")
    return jsonify(ok=True)


@app.route("/api/flights/<int:fid>", methods=["DELETE"])
def delete_flight(fid):
    try:
        run("DELETE FROM flight WHERE flight_id = %s", (fid,))
        db().commit()
    except IntegrityError:
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

    flight = one("SELECT * FROM flight WHERE flight_id = %s", (fid,))
    if not flight:
        return fail("Flight not found.", 404)

    # Find the passenger by email, or create a new one
    p = one("SELECT passenger_id FROM passenger WHERE email = %s", (email,))
    if p:
        pid = p["passenger_id"]
    else:
        pid = run("INSERT INTO passenger(name,email,phone) VALUES(%s,%s,%s)", (name, email, phone)).lastrowid

    if one("SELECT 1 FROM booking WHERE passenger_id=%s AND flight_id=%s AND status='CONFIRMED'", (pid, fid)):
        return fail("This passenger already has a confirmed booking on this flight.")

    # Give the lowest free seat number
    taken = {r["seat_no"] for r in query("SELECT seat_no FROM booking WHERE flight_id=%s AND status='CONFIRMED'", (fid,))}
    seat = next((n for n in range(1, flight["total_seats"] + 1) if n not in taken), None)
    if seat is None:
        return fail("This flight is full.")

    bid = run("INSERT INTO booking(passenger_id,flight_id,seat_no) VALUES(%s,%s,%s)", (pid, fid, seat)).lastrowid
    db().commit()
    return jsonify(booking_id=bid, seat_no=seat)


@app.route("/api/bookings")
def my_bookings():
    sql = """SELECT b.booking_id, b.seat_no, b.status, CAST(b.booked_at AS CHAR) AS booked_at,
                    p.passenger_id, p.name, p.phone,
                    f.flight_no, f.origin, f.destination, f.departure, f.price
             FROM booking b
             JOIN passenger p ON p.passenger_id = b.passenger_id
             JOIN flight f    ON f.flight_id = b.flight_id
             WHERE p.email = %s
             ORDER BY b.booking_id DESC"""
    return jsonify(query(sql, (request.args.get("email", "").strip().lower(),)))


@app.route("/api/bookings/<int:bid>", methods=["DELETE"])
def cancel(bid):
    # UPDATE: cancelling frees the seat (seat_no becomes NULL) but keeps the record for history
    cur = run("UPDATE booking SET status='CANCELLED', seat_no=NULL WHERE booking_id=%s AND status='CONFIRMED'", (bid,))
    db().commit()
    return jsonify(ok=True) if cur.rowcount else fail("Booking is already cancelled.")


@app.route("/api/passengers/<int:pid>", methods=["PUT"])
def update_passenger(pid):
    d = request.json
    name, phone = d.get("name", "").strip(), d.get("phone", "").strip()
    if not name or not (phone.isdigit() and len(phone) == 10):
        return fail("Enter a name and a 10-digit phone number.")
    run("UPDATE passenger SET name=%s, phone=%s WHERE passenger_id=%s", (name, phone, pid))
    db().commit()
    return jsonify(ok=True)


# ---------- report ----------
@app.route("/api/report")
def report():
    # Aggregation: confirmed bookings and revenue per flight
    sql = """SELECT f.flight_no, f.origin, f.destination, f.total_seats,
                    COUNT(b.booking_id) AS bookings,
                    CAST(COALESCE(SUM(f.price), 0) AS SIGNED) AS revenue
             FROM flight f
             LEFT JOIN booking b ON b.flight_id = f.flight_id AND b.status = 'CONFIRMED'
             GROUP BY f.flight_id
             ORDER BY revenue DESC"""
    return jsonify(query(sql))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
