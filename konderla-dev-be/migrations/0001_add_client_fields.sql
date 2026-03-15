-- Migration: add client_name and client_project_name to budgets table
ALTER TABLE budgets ADD COLUMN IF NOT EXISTS client_name TEXT;
ALTER TABLE budgets ADD COLUMN IF NOT EXISTS client_project_name TEXT;
