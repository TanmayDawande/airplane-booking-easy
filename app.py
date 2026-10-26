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
    for stmt in open("schema.sql").read().split(";"):   
        if stmt.strip():
            cur.execute(stmt)
    cur.execute("SELECT COUNT(*) FROM flight")
    if cur.fetchone()[0] == 0:
        base = datetime.now().replace(minute=0, second=0, microsecond=0)
        seed = [
    # Original Flights
    ("AI101", "Chennai", "Delhi", 2, 6, 6500, 60),
    ("AI102", "Delhi", "Chennai", 3, 9, 6400, 60),
    ("6E205", "Chennai", "Mumbai", 2, 14, 4200, 40),
    ("6E310", "Mumbai", "Bengaluru", 4, 11, 3100, 40),
    ("UK512", "Bengaluru", "Kolkata", 5, 17, 5300, 50),
    ("AI340", "Chennai", "Bengaluru", 1, 8, 2400, 30),
    ("6E415", "Bengaluru", "Chennai", 6, 19, 2500, 30),
    ("UK820", "Mumbai", "Delhi", 1, 7, 4800, 50),
    ("AI505", "Delhi", "Mumbai", 5, 16, 4900, 60),
    ("SG112", "Kolkata", "Delhi", 3, 10, 5100, 40),
    ("6E708", "Hyderabad", "Bengaluru", 2, 12, 2200, 30),
    ("UK611", "Bengaluru", "Hyderabad", 4, 20, 2300, 30),
    ("AI677", "Chennai", "Kolkata", 6, 15, 4600, 50),
    ("QP134", "Mumbai", "Goa", 5, 13, 2800, 40),
    ("6E892", "Goa", "Bengaluru", 7, 18, 2900, 40),
    ("UK945", "Delhi", "Ahmedabad", 1, 9, 3400, 50),
    ("AI422", "Ahmedabad", "Mumbai", 2, 11, 2600, 40),
    ("SG401", "Chennai", "Hyderabad", 4, 7, 2700, 30),
    ("6E553", "Hyderabad", "Delhi", 7, 21, 5600, 50),
    ("QP210", "Kolkata", "Mumbai", 3, 14, 5800, 60),
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

# ---------- AUTHENTICATION (Assessment 10) ----------
@app.route("/api/login", methods=["POST"])
def login():
    d = request.json
    email, phone = d.get("email", "").strip().lower(), d.get("phone", "").strip()
    if not email or not phone:
        return fail("Email and phone are required.")
    
    user = one("SELECT * FROM passenger WHERE email = %s AND phone = %s", (email, phone))
    if user:
        return jsonify(user)
    return fail("Invalid credentials.", 401)

@app.route("/api/register", methods=["POST"])
def register():
    d = request.json
    name, email, phone = d.get("name", "").strip(), d.get("email", "").strip().lower(), d.get("phone", "").strip()
    if not name or "@" not in email or not (phone.isdigit() and len(phone) == 10):
        return fail("Enter a valid name, email, and 10-digit phone.")
    
    try:
        pid = run("INSERT INTO passenger(name,email,phone) VALUES(%s,%s,%s)", (name, email, phone)).lastrowid
        db().commit()
        return jsonify({"passenger_id": pid, "name": name, "email": email, "phone": phone})
    except IntegrityError:
        return fail("Email already exists.")

# ---------- flights ----------
@app.route("/api/flights")
def list_flights():
    sql = """SELECT f.*, f.total_seats - COUNT(b.booking_id) AS available
             FROM flight f
             LEFT JOIN booking b ON b.flight_id = f.flight_id AND b.status = 'CONFIRMED'
             WHERE f.origin LIKE %s AND f.destination LIKE %s AND f.departure LIKE %s
             GROUP BY f.flight_id
             ORDER BY f.departure"""
    a = request.args
    return jsonify(query(sql, (f"%{a.get('origin','')}%", f"%{a.get('destination','')}%", f"{a.get('date','')}%")))

# ---------- bookings ----------
@app.route("/api/book", methods=["POST"])
def book():
    d = request.json
    pid = d.get("passenger_id")
    fid = d.get("flight_id")
    
    # ASSESSMENT 10: Explicit Transactions & Exception Handling
    try:
        db().start_transaction()

        flight = one("SELECT * FROM flight WHERE flight_id = %s", (fid,))
        if not flight:
            return fail("Flight not found.", 404)

        if one("SELECT 1 FROM booking WHERE passenger_id=%s AND flight_id=%s AND status='CONFIRMED'", (pid, fid)):
            db().rollback()
            return fail("You already have a confirmed booking on this flight.")

        taken = {r["seat_no"] for r in query("SELECT seat_no FROM booking WHERE flight_id=%s AND status='CONFIRMED'", (fid,))}
        seat = next((n for n in range(1, flight["total_seats"] + 1) if n not in taken), None)
        if seat is None:
            db().rollback()
            return fail("This flight is full.")

        bid = run("INSERT INTO booking(passenger_id,flight_id,seat_no,status) VALUES(%s,%s,%s,'CONFIRMED')", (pid, fid, seat)).lastrowid
        db().commit()
        return jsonify(booking_id=bid, seat_no=seat)
        
    except Exception as e:
        db().rollback()
        return fail(f"Transaction Failed: {str(e)}", 500)

@app.route("/api/bookings")
def my_bookings():
    sql = """SELECT b.booking_id, b.seat_no, b.status, 
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
    # ASSESSMENT 9: Physical Hard DELETE
    cur = run("DELETE FROM booking WHERE booking_id=%s", (bid,))
    db().commit()
    return jsonify(ok=True) if cur.rowcount else fail("Booking not found.")

@app.route("/api/passengers/<int:pid>", methods=["PUT"])
def update_passenger(pid):
    # ASSESSMENT 9: UPDATE
    d = request.json
    new_phone = d.get("phone", "").strip()
    if not (new_phone.isdigit() and len(new_phone) == 10):
        return fail("Enter a valid 10-digit phone number.")
    
    run("UPDATE passenger SET phone=%s WHERE passenger_id=%s", (new_phone, pid))
    db().commit()
    return jsonify(ok=True)

# ---------- report ----------
@app.route("/api/report")
def report():
    # ASSESSMENT 9/10: JOINS AND AGGREGATIONS
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