-- InsForge / PostgreSQL Database Schema for AI Skin Specialist
-- Run this migration in your InsForge dashboard (SQL Editor) or via the InsForge CLI

CREATE TABLE IF NOT EXISTS consultations (
    id BIGSERIAL PRIMARY KEY,
    patient_name VARCHAR(255) NOT NULL,
    patient_age INT,
    patient_gender VARCHAR(50),
    patient_transcript TEXT,
    doctor_guidance TEXT,
    image_path TEXT,
    audio_path TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Row-Level Security (RLS)
ALTER TABLE consultations ENABLE ROW LEVEL SECURITY;

-- Allow inserts and queries via InsForge Anon Key
CREATE POLICY "Allow public insert" ON consultations FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow public select" ON consultations FOR SELECT USING (true);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_consultations_patient_name ON consultations(patient_name);
CREATE INDEX IF NOT EXISTS idx_consultations_created_at ON consultations(created_at DESC);
