CREATE DATABASE IF NOT EXISTS airline;
USE airline;

CREATE TABLE IF NOT EXISTS passenger (
    passenger_id INT AUTO_INCREMENT PRIMARY KEY,
    name         VARCHAR(100) NOT NULL,
    email        VARCHAR(120) NOT NULL UNIQUE,
    phone        VARCHAR(10)  NOT NULL
);

CREATE TABLE IF NOT EXISTS flight (
    flight_id    INT AUTO_INCREMENT PRIMARY KEY,
    flight_no    VARCHAR(10)  NOT NULL UNIQUE,
    origin       VARCHAR(50)  NOT NULL,
    destination  VARCHAR(50)  NOT NULL,
    departure    VARCHAR(16)  NOT NULL,
    price        INT NOT NULL CHECK (price > 0),
    total_seats  INT NOT NULL CHECK (total_seats > 0)
);

CREATE TABLE IF NOT EXISTS booking (
    booking_id   INT AUTO_INCREMENT PRIMARY KEY,
    passenger_id INT NOT NULL,
    flight_id    INT NOT NULL,
    seat_no      INT NULL,
    status       VARCHAR(10) NOT NULL DEFAULT 'CONFIRMED' CHECK (status IN ('CONFIRMED','CANCELLED')),
    booked_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (passenger_id) REFERENCES passenger(passenger_id),
    FOREIGN KEY (flight_id) REFERENCES flight(flight_id),
    UNIQUE (flight_id, seat_no)
)
