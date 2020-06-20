USE booking;

CREATE TABLE if not exists clients (
  client_id SERIAL PRIMARY KEY,
  name VARCHAR(80) NOT NULL,
  surname VARCHAR(80) NOT NULL,
  dob DATE,
  phone_1 VARCHAR(25),
  phone_2 VARCHAR(25),
  address_1 VARCHAR(150),
  address_2 VARCHAR(150),
  address_3 VARCHAR(150),
  city VARCHAR(80),
  county VARCHAR(50),
  postcode VARCHAR(10)
);
INSERT IGNORE INTO clients (client_id, name, surname, dob, phone_1, phone_2, address_1, address_2, address_3, city, county, postcode)
VALUES(1, 'John', 'Doe', '1980-12-17', '07923424294', NULL, '13 Place Road', NULL, NULL, 'Edinburgh', NULL, 'RH16 4RF');

CREATE TABLE if not exists practitioners (
  prac_id SERIAL PRIMARY KEY,
  name VARCHAR(80) NOT NULL,
  surname VARCHAR(80) NOT NULL,
  phone VARCHAR(25) NOT NULL
);
INSERT IGNORE INTO practitioners (prac_id, name, surname, phone)
VALUES(1, 'Wesley', 'Connellan', '030587598479'),
(2, 'Ellie', 'Gorham', '0338236893462');

CREATE TABLE if not exists treatments (
  treat_id SERIAL PRIMARY KEY,
  name VARCHAR(150) NOT NULL,
  price DECIMAL(18,2) NOT NULL,
  duration DECIMAL(18,2) NOT NULL
);
TRUNCATE treatments;
INSERT IGNORE INTO treatments (treat_id, name, price, duration)
VALUES(1, 'First appointment', 55.00, 1.00),
(2, 'Follow-up appointment', 45.00, 0.30),
(3, 'Infant first appointment', 65.00, 1.00),
(4, 'Infant Follow-up appointment', 55.00, 0.30);

CREATE TABLE if not exists bookings (
  booking_id SERIAL PRIMARY KEY,
  prac_id BIGINT UNSIGNED NOT NULL,
  client_id BIGINT UNSIGNED NOT NULL,
  treat_id BIGINT UNSIGNED NOT NULL,
  name DATE NOT NULL,
  descr VARCHAR(50) NOT NULL,
  start TIME NOT NULL,
  end TIME NOT NULL,
  price DECIMAL(18,2) NOT NULL,
  pay_status ENUM('not paid', 'cash', 'card', 'invoice', 'insurance') NOT NULL,
  pay_timestamp DATETIME,
  FOREIGN KEY (prac_id) REFERENCES practitioners(prac_id),
  FOREIGN KEY (client_id) REFERENCES clients(client_id),
  FOREIGN KEY (treat_id) REFERENCES treatments(treat_id)
);

DELIMITER //
DROP TRIGGER IF EXISTS booking_conflict;
CREATE TRIGGER booking_conflict
BEFORE INSERT
  ON bookings FOR EACH ROW
BEGIN
  DECLARE vCnt INT ;
  SELECT COUNT(*) INTO vCnt FROM bookings
  WHERE (prac_id = NEW.prac_id)
  AND name = NEW.name
  AND ((start <= NEW.start AND end > NEW.start)
  OR (start >= NEW.start AND start < NEW.end));
  IF vCnt > 0 THEN
    SET @s = 'Error: Booking clash';
    SIGNAL SQLSTATE '45001' SET MESSAGE_TEXT = @s;
  END IF;
END; //
DELIMITER ;

CREATE TABLE if not exists freqs (
  freq_id SERIAL PRIMARY KEY,
  name VARCHAR(30) NOT NULL
);

TRUNCATE freqs;
INSERT IGNORE INTO freqs (name)
VALUES ('weekly'), ('biweekly'), ('biweekly-odd');

CREATE TABLE if not exists avails (
  avail_id SERIAL PRIMARY KEY,
  prac_id BIGINT UNSIGNED NOT NULL,
  day ENUM('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'),
  start TIME NOT NULL,
  end TIME NOT NULL,
  freq_id BIGINT UNSIGNED NOT NULL,
  FOREIGN KEY (prac_id) REFERENCES practitioners(prac_id),
  FOREIGN KEY (freq_id) REFERENCES freqs(freq_id)
);

DELIMITER //
DROP TRIGGER IF EXISTS avail_conflict;
CREATE TRIGGER avail_conflict
BEFORE INSERT
  ON avails FOR EACH ROW
BEGIN
  DECLARE vCnt INT;
  SELECT COUNT(*) INTO vCnt FROM avails
  WHERE (prac_id = NEW.prac_id)
  AND day = NEW.day
  AND ((start <= NEW.start AND end > NEW.start)
  OR (start >= NEW.start AND start < NEW.end));
  IF vCnt > 0 THEN
    SET @s = 'Avail time overlap';
    SIGNAL SQLSTATE '45001' SET MESSAGE_TEXT = @s;
  END IF;
END; //
DELIMITER ;

TRUNCATE avails;
INSERT IGNORE INTO avails (prac_id, day, start, end, freq_id)
VALUES (1, 'Tuesday', '16:00', '20:00', 1),
       (1, 'Thursday', '9:00', '16:00', 1),
       (1, 'Saturday', '9:00', '16:00', 1),
       (2, 'Monday', '9:00', '17:00', 2),
       (2, 'Friday', '9:00', '13:30', 1);

CREATE TABLE if not exists blocked_periods (
  bp_id SERIAL PRIMARY KEY,
  prac_id BIGINT UNSIGNED NOT NULL,
  date DATE NOT NULL,
  start TIME NOT NULL,
  end TIME NOT NULL,
  FOREIGN KEY (prac_id) REFERENCES practitioners(prac_id)
);

INSERT IGNORE INTO blocked_periods (bp_id, prac_id, date, start, end)
VALUES (1, 1, '2019-12-30', '9:00', '10:30');

CREATE TABLE if not exists users (
  user_id SERIAL PRIMARY KEY,
  email VARCHAR(150) NOT NULL,
  password VARCHAR(80) NOT NULL,
  access_lvl INT DEFAULT 0,
  auth_key VARCHAR(36),
  client_id BIGINT UNSIGNED,
  prac_id BIGINT UNSIGNED,
  FOREIGN KEY (client_id) REFERENCES clients(client_id),
  FOREIGN KEY (prac_id) REFERENCES practitioners(prac_id)
);

INSERT IGNORE INTO users (user_id, email, password, access_lvl, client_id, prac_id)
VALUES(1, 'wesleyconnellan@gmail.com', MD5('admin'), 2, NULL, 1);

CREATE TABLE if not exists notes (
  note_id SERIAL PRIMARY KEY,
  note BLOB,
  image LONGBLOB,
  timestamp DATETIME NOT NULL,
  client_id BIGINT UNSIGNED NOT NULL,
  prac_id BIGINT UNSIGNED NOT NULL,
  booking_id BIGINT UNSIGNED,
  draft BOOLEAN NOT NULL,
  FOREIGN KEY (client_id) REFERENCES clients(client_id),
  FOREIGN KEY (prac_id) REFERENCES practitioners(prac_id),
  FOREIGN KEY (booking_id) REFERENCES bookings(booking_id)
);
