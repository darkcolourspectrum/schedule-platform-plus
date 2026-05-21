-- ===================================================
-- Инициализация баз данных для микросервисов
-- Schedule Platform Plus
-- ===================================================

-- Auth Service Database
CREATE USER auth_user WITH PASSWORD 'auth_password';
CREATE DATABASE auth_service_db OWNER auth_user;
GRANT ALL PRIVILEGES ON DATABASE auth_service_db TO auth_user;

-- Profile Service Database  
CREATE USER profile_user WITH PASSWORD 'profile_password';
CREATE DATABASE profile_service_db OWNER profile_user;
GRANT ALL PRIVILEGES ON DATABASE profile_service_db TO profile_user;

-- Schedule Service Database
CREATE USER schedule_user WITH PASSWORD 'schedule_password';
CREATE DATABASE schedule_service_db OWNER schedule_user;
GRANT ALL PRIVILEGES ON DATABASE schedule_service_db TO schedule_user;

-- CRM Service Database
CREATE USER crm_user WITH PASSWORD 'crm_password';
CREATE DATABASE crm_service_db OWNER crm_user;
GRANT ALL PRIVILEGES ON DATABASE crm_service_db TO crm_user;

-- Подключаемся к каждой БД и даем права пользователям

-- Auth Service permissions
\connect auth_service_db;
GRANT ALL ON SCHEMA public TO auth_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO auth_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO auth_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO auth_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO auth_user;

-- Profile Service permissions
\connect profile_service_db;
GRANT ALL ON SCHEMA public TO profile_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO profile_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO profile_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO profile_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO profile_user;

-- Schedule Service permissions
\connect schedule_service_db;
GRANT ALL ON SCHEMA public TO schedule_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO schedule_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO schedule_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO schedule_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO schedule_user;

-- Создаём БД для Admin Service
CREATE DATABASE admin_service_db OWNER postgres;
GRANT ALL PRIVILEGES ON DATABASE admin_service_db TO postgres;

-- Подключаемся к admin_service_db и даём права
\connect admin_service_db;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO postgres;

-- Notification Service Database
CREATE USER notification_user WITH PASSWORD 'notification_password';
CREATE DATABASE notification_service_db OWNER notification_user;
GRANT ALL PRIVILEGES ON DATABASE notification_service_db TO notification_user;

\connect notification_service_db;
GRANT ALL ON SCHEMA public TO notification_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO notification_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO notification_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO notification_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO notification_user;

\connect crm_service_db;
GRANT ALL ON SCHEMA public TO crm_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO crm_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO crm_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO crm_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO crm_user;

-- Возвращаемся к postgres БД
\connect postgres;

-- Логирование
SELECT 'Database initialization completed successfully!' as status;