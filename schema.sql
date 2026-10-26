CREATE TABLE IF NOT EXISTS passenger (
    passenger_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    email        TEXT NOT NULL UNIQUE,
    phone        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS flight (
    flight_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    flight_no    TEXT NOT NULL UNIQUE,
    origin       TEXT NOT NULL,
    destination  TEXT NOT NULL,
    departure    TEXT NOT NULL,              -- 'YYYY-MM-DD HH:MM'
    price        INTEGER NOT NULL CHECK (price > 0),
    total_seats  INTEGER NOT NULL CHECK (total_seats > 0),
    CHECK (origin <> destination)
);

CREATE TABLE IF NOT EXISTS booking (
    booking_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    passenger_id INTEGER NOT NULL REFERENCES passenger(passenger_id),
    flight_id    INTEGER NOT NULL REFERENCES flight(flight_id),
    seat_no      INTEGER NOT NULL,
    status       TEXT NOT NULL DEFAULT 'CONFIRMED' CHECK (status IN ('CONFIRMED','CANCELLED')),
    booked_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- A seat can belong to only one confirmed booking per flight
CREATE UNIQUE INDEX IF NOT EXISTS uq_seat ON booking(flight_id, seat_no) WHERE status = 'CONFIRMED';
