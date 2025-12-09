-- Admin Service Database Initialization
-- Добавьте эти строки в ваш основной init-databases.sql

-- Create admin_service database
CREATE DATABASE admin_service_db;

-- Create user for admin_service
CREATE USER admin_user WITH PASSWORD 'admin_password';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE admin_service_db TO admin_user;

-- Connect to admin_service_db and grant schema privileges
\c admin_service_db;
GRANT ALL ON SCHEMA public TO admin_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO admin_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO admin_user;
