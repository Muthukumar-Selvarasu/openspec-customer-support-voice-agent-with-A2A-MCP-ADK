-- Schema and demo seed for Postgres (local Podman `toolbox_db` and Neon).
-- Non-destructive and idempotent: safe to re-run without dropping tables,
-- duplicating demo rows, or failing when role `toolbox_user` does not exist.
-- Shopper passwords are demo values used by authentication tests.

CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(100),
    is_premium_customer BOOLEAN DEFAULT FALSE,
    total_items_purchased INTEGER DEFAULT 0,
    password VARCHAR(255) NOT NULL
);

INSERT INTO users (email, full_name, is_premium_customer, total_items_purchased, password) VALUES
    ('hannah.m@school.edu',       'Hannah M',     TRUE,  94, 'hannah'),
    ('charlie.d@webmail.com',     'Charlie D',    TRUE,  88, 'charlie'),
    ('julia.child@kitchen.com',   'Julia Child',  TRUE,  75, 'julia'),
    ('evan.g@bizcorp.com',        'Evan G',       TRUE,  56, 'evan'),
    ('alice.jones@example.com',   'Alice Jones',  FALSE, 42, 'alice'),
    ('ian.malcolm@chaos.com',     'Ian Malcolm',  FALSE, 31, 'ian'),
    ('diana.prince@hero.net',     'Diana Prince', FALSE, 23, 'diana'),
    ('george.j@jungle.com',       'George J',     FALSE, 19, 'george'),
    ('bob.smith@techmail.com',    'Bob Smith',    FALSE, 15, 'bob'),
    ('fiona.shrek@swamp.com',     'Fiona Shrek',  FALSE, 12, 'fiona')
ON CONFLICT (email) DO NOTHING;

CREATE TABLE IF NOT EXISTS customer_orders (
    order_id SERIAL PRIMARY KEY,
    customer_email VARCHAR(255) NOT NULL REFERENCES users (email),
    delivery_address VARCHAR(255),
    status VARCHAR(20) NOT NULL CHECK (status IN ('PROCESSING', 'SHIPPED', 'DELIVERED', 'CANCELLED', 'RETURNED')),
    items JSONB NOT NULL,
    order_date TIMESTAMPTZ DEFAULT NOW(),
    total_amount DECIMAL(10, 2) NOT NULL
);

CREATE INDEX IF NOT EXISTS customer_orders_customer_email_idx ON customer_orders (customer_email);

INSERT INTO customer_orders (order_id, customer_email, delivery_address, status, items, order_date, total_amount) VALUES
    (1,  'alice.jones@example.com',  '123 Market St, Springfield', 'DELIVERED',  '[{"product":"Ergonomic Office Chair","qty":1,"price":250.00}]', NOW() - INTERVAL '6 months',   250.00),
    (2,  'alice.jones@example.com',  '123 Market St, Springfield', 'DELIVERED',  '[{"product":"Wireless Mouse","qty":1,"price":25.00}]',         NOW() - INTERVAL '3 months',    25.00),
    (3,  'alice.jones@example.com',  '123 Market St, Springfield', 'SHIPPED',    '[{"product":"Mechanical Keyboard","qty":1,"price":120.00}]',    NOW() - INTERVAL '2 days',     120.00),
    (4,  'alice.jones@example.com',  '123 Market St, Springfield', 'PROCESSING', '[{"product":"USB-C Hub","qty":1,"price":45.00}]',               NOW() - INTERVAL '1 hour',      45.00),
    (5,  'bob.smith@techmail.com',   '88 Tech Ave, Seattle',       'DELIVERED',  '[{"product":"Gaming Laptop 15-inch","qty":1,"price":1500.00}]', NOW() - INTERVAL '1 year',    1500.00),
    (6,  'bob.smith@techmail.com',   '88 Tech Ave, Seattle',       'CANCELLED',  '[{"product":"VR Headset","qty":1,"price":400.00}]',             NOW() - INTERVAL '10 days',    400.00),
    (7,  'bob.smith@techmail.com',   '88 Tech Ave, Seattle',       'PROCESSING', '[{"product":"Curved Monitor 34-inch","qty":1,"price":450.00}]', NOW() - INTERVAL '4 hours',   450.00),
    (8,  'charlie.d@webmail.com',    '12 Oak Rd, Denver',          'DELIVERED',  '[{"product":"AA Batteries (Pack of 12)","qty":2,"price":15.00}]', NOW() - INTERVAL '45 days',  30.00),
    (9,  'diana.prince@hero.net',    '5 Hero Ln, Metropolis',      'DELIVERED',  '[{"product":"Smart Watch Gen 5","qty":1,"price":299.00}]',       NOW() - INTERVAL '60 days',   299.00),
    (10, 'diana.prince@hero.net',    '5 Hero Ln, Metropolis',      'RETURNED',   '[{"product":"Running Shoes","qty":1,"price":120.00}]',           NOW() - INTERVAL '15 days',   120.00),
    (11, 'evan.g@bizcorp.com',       '200 Business Pkwy, Austin',  'SHIPPED',    '[{"product":"Office Desk","qty":2,"price":300.00}]',             NOW() - INTERVAL '1 day',     600.00),
    (12, 'fiona.shrek@swamp.com',    '7 Swamp Rd, Bayou',          'CANCELLED',  '[{"product":"Skincare Gift Set","qty":1,"price":85.00}]',        NOW() - INTERVAL '5 days',     85.00),
    (13, 'george.j@jungle.com',      '9 Jungle Path, Amazonia',    'PROCESSING', '[{"product":"Bluetooth Speaker","qty":1,"price":60.00}]',        NOW() - INTERVAL '30 minutes',  60.00),
    (14, 'hannah.m@school.edu',      '4 Campus Dr, Boston',        'DELIVERED',  '[{"product":"Notebook Pack","qty":5,"price":12.00}]',            NOW() - INTERVAL '4 months',    60.00),
    (15, 'ian.malcolm@chaos.com',    '22 Chaos Blvd, San Diego',   'DELIVERED',  '[{"product":"Professional Camera Lens","qty":1,"price":2200.00}]', NOW() - INTERVAL '8 months', 2200.00),
    (16, 'julia.child@kitchen.com',  '10 Kitchen St, Portland',    'DELIVERED',  '[{"product":"Coffee Beans 1kg","qty":1,"price":25.00}]',         NOW() - INTERVAL '3 months',    25.00),
    (17, 'julia.child@kitchen.com',  '10 Kitchen St, Portland',    'PROCESSING', '[{"product":"Descaling Kit","qty":1,"price":15.00}]',            NOW() - INTERVAL '3 hours',     15.00)
ON CONFLICT (order_id) DO NOTHING;

SELECT setval(
    pg_get_serial_sequence('customer_orders', 'order_id'),
    COALESCE((SELECT MAX(order_id) FROM customer_orders), 1)
);

CREATE TABLE IF NOT EXISTS actions_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    user_email VARCHAR(255) NOT NULL REFERENCES users (email),
    action_type VARCHAR(50) NOT NULL,
    parameters JSONB NOT NULL
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'toolbox_user') THEN
        GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO toolbox_user;
        GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO toolbox_user;
        GRANT USAGE ON SCHEMA public TO toolbox_user;
    END IF;
END
$$;
