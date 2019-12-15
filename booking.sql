USE booking;

CREATE TABLE if not exists clients (
  client_id SERIAL PRIMARY KEY,
  name VARCHAR(80) NOT NULL,
  surname VARCHAR(80) NOT NULL,
  phone_1 VARCHAR(25) NOT NULL,
  phone_2 VARCHAR(25),
  address_1 VARCHAR(150) NOT NULL,
  address_2 VARCHAR(150),
  address_3 VARCHAR(150),
  city VARCHAR(80) NOT NULL,
  county VARCHAR(50),
  postcode VARCHAR(10) NOT NULL
);
INSERT IGNORE INTO clients (client_id, name, surname, phone_1, phone_2, address_1, address_2, address_3, city, county, postcode)
VALUES(1, 'John', 'Doe', '07923424294', NULL, '13 Place Road', NULL, NULL, 'Edinburgh', NULL, 'RH16 4RF'),
(2, 'Alice', 'Smith', '03835734709', '380476498344', 'Room 23', 'Flat 12', '7 Park Road', 'Perth', 'Perth and Kinross', 'RH14 2RT');

CREATE TABLE if not exists practitioners (
  prac_id SERIAL PRIMARY KEY,
  name VARCHAR(80) NOT NULL,
  surname VARCHAR(80) NOT NULL,
  phone VARCHAR(25) NOT NULL
);
INSERT IGNORE INTO practitioners (prac_id, name, surname, phone)
VALUES(1, 'Wesley', 'Connellan', '030587598479'),
(2, 'Ellie', 'Gorham', '0338236893462');

CREATE TABLE if not exists room_types (
  room_type_id SERIAL PRIMARY KEY,
  name VARCHAR(150) NOT NULL
);
INSERT IGNORE INTO room_types (room_type_id, name)
VALUES(1, 'General room');

CREATE TABLE if not exists treatments (
  treat_id SERIAL PRIMARY KEY,
  name VARCHAR(150) NOT NULL,
  room_type_id BIGINT UNSIGNED NOT NULL,
  price DECIMAL(18,2) NOT NULL,
  duration DECIMAL(18,2) NOT NULL,
  FOREIGN KEY (room_type_id) REFERENCES room_types(room_type_id)
);
TRUNCATE treatments;
INSERT IGNORE INTO treatments (treat_id, name, room_type_id, price, duration)
VALUES(1, 'First appointment', 1, 40.00, 1.00),
(2, 'Follow-up appointment', 1, 30.00, 0.30);

CREATE TABLE if not exists rooms (
  room_id SERIAL PRIMARY KEY,
  name VARCHAR(80) NOT NULL,
  room_type_id BIGINT UNSIGNED NOT NULL,
  FOREIGN KEY (room_type_id) REFERENCES room_types(room_type_id)
);
INSERT IGNORE INTO rooms (room_id, name, room_type_id)
VALUES(1, 'Room 1', 1), (2, 'Room 2', 1);

CREATE TABLE if not exists bookings (
  booking_id SERIAL PRIMARY KEY,
  prac_id BIGINT UNSIGNED NOT NULL,
  client_id BIGINT UNSIGNED NOT NULL,
  room_id BIGINT UNSIGNED NOT NULL,
  name DATE NOT NULL,
  start TIME NOT NULL,
  end TIME NOT NULL,
  price DECIMAL(18,2) NOT NULL,
  FOREIGN KEY (prac_id) REFERENCES practitioners(prac_id),
  FOREIGN KEY (client_id) REFERENCES clients(client_id),
  FOREIGN KEY (room_id) REFERENCES rooms(room_id)
);

DELIMITER //
DROP TRIGGER IF EXISTS booking_conflict;
CREATE TRIGGER booking_conflict
BEFORE INSERT
  ON bookings FOR EACH ROW
BEGIN
  DECLARE vCnt INT ;
  SELECT COUNT(*) INTO vCnt FROM bookings
  WHERE (prac_id = NEW.prac_id OR room_id = NEW.room_id)
  AND name = NEW.name
  AND ((start <= NEW.start AND end > NEW.start)
  OR (start >= NEW.start AND start < NEW.end));
  IF vCnt > 0 THEN
    SET @s = 'Error: Booking clash';
    SIGNAL SQLSTATE '45001' SET MESSAGE_TEXT = @s;
  END IF;
END; //
DELIMITER ;

TRUNCATE bookings;
INSERT IGNORE INTO bookings (booking_id, prac_id, client_id, room_id, name, start, end, price)
VALUES(1, 1, 1, 1, '2019-12-17', '10:30', '11:00', 30.00),
(2, 1, 2, 2, '2019-12-16', '9:30', '10:30', 40.00);

CREATE TABLE if not exists avails (
  avail_id SERIAL PRIMARY KEY,
  prac_id BIGINT UNSIGNED NOT NULL,
  date DATE NOT NULL,
  start TIME NOT NULL,
  end TIME NOT NULL,
  FOREIGN KEY (prac_id) REFERENCES practitioners(prac_id)
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
  AND date = NEW.date
  AND ((start <= NEW.start AND end > NEW.start)
  OR (start >= NEW.start AND start < NEW.end));
  IF vCnt > 0 THEN
    SET @s = 'Avail time overlap';
    SIGNAL SQLSTATE '45001' SET MESSAGE_TEXT = @s;
  END IF;
END; //
DELIMITER ;

TRUNCATE avails;
DROP PROCEDURE IF EXISTS avail_populate;
DELIMITER //
CREATE PROCEDURE avail_populate()
BEGIN
  DECLARE cur_date DATE DEFAULT CURDATE();
  WHILE cur_date < DATE_ADD(CURDATE(), INTERVAL 30 DAY) DO
    IF DAYOFWEEK(cur_date) != 1 THEN
      INSERT INTO avails (prac_id, date, start, end)
      VALUES (1, cur_date, '9:00', '17:00'),
             (2, cur_date, '9:00', '17:00');
    END IF;
    SET cur_date = DATE_ADD(cur_date, INTERVAL 1 DAY);
  END WHILE;
END; //
DELIMITER ;
CALL avail_populate();

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
VALUES(1, 'wesleyconnellan@gmail.com', MD5('admin'), 2, NULL, 1),
(2, 'john.doe@gmail.com', MD5('user'), 0, 1, NULL);

CREATE TABLE if not exists notes (
  note_id SERIAL PRIMARY KEY,
  note TEXT,
  timestamp DATETIME NOT NULL,
  client_id BIGINT UNSIGNED NOT NULL,
  prac_id BIGINT UNSIGNED NOT NULL,
  booking_id BIGINT UNSIGNED,
  FOREIGN KEY (client_id) REFERENCES clients(client_id),
  FOREIGN KEY (prac_id) REFERENCES practitioners(prac_id),
  FOREIGN KEY (booking_id) REFERENCES bookings(booking_id)
);
INSERT IGNORE INTO notes (note_id, note, timestamp, client_id, prac_id, booking_id) VALUES (1, LOAD_FILE('/export/wynberg/lloyd/note.txt'), NOW(), 1, 1, 1);
