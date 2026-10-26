# SkyDesk – Airline Reservation System

A simple DBMS project for booking airline tickets.

**Stack:** Python (Flask) · MySQL · HTML/CSS/JavaScript

## Features
- Search flights by origin, destination and date
- Book a seat (seat number is assigned automatically)
- View bookings by email, edit passenger details, cancel a booking
- Admin: add and delete flights, view a sales report

## Database
Database `airline` with three tables:
- `passenger` (passenger_id, name, email, phone)
- `flight` (flight_id, flight_no, origin, destination, departure, price, total_seats)
- `booking` (booking_id, passenger_id, flight_id, seat_no, status, booked_at)

## Project structure
```
app.py            backend (Flask routes and SQL queries)
schema.sql        database and table definitions
templates/
  index.html      front end
.env              database login (not committed)
requirements.txt  Python packages
```

## How to run
1. Install MySQL and make sure the server is running.
2. Install the packages:
   ```
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the project folder:
   ```
   DB_HOST=localhost
   DB_USER=root
   DB_PASSWORD=your_password
   ```
4. Start the app:
   ```
   python app.py
   ```
   The database, tables and sample flights are created on the first run.
5. Open http://127.0.0.1:5000 in your browser.

## View the data in MySQL Workbench
Connect to your local server, then run:
```sql
USE airline;
SELECT * FROM flight;
SELECT * FROM passenger;
SELECT * FROM booking;
```
