-- Add client_name and client_project_name to projects (run if you have existing DB before this change)
ALTER TABLE projects ADD COLUMN IF NOT EXISTS client_name VARCHAR;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS client_project_name VARCHAR;
