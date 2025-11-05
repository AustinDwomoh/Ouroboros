-- ============================================================
-- PostgreSQL Normalized Schema v2 for Ouroboros
-- - Corrected foreign key dependencies and improved data integrity
-- - Added user_media registry for efficient media enumeration
-- - Timestamp triggers on commonly-updated tables
-- Created: 2025-11-05 (v2.1 - corrected)
-- ============================================================
\set ON_ERROR_STOP on
\echo '🔧 Running Ouroboros schema v2.1...'

-- Clean slate: drop everything
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;

-- Ensure we're using the public schema
SET search_path TO public;

-- Create extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

DO $$ BEGIN RAISE NOTICE '✅ Extension uuid-ossp ensured.'; END$$;
DO $$ BEGIN RAISE NOTICE '✅ Creating tables...'; END$$;

-- ============================================================
-- CORE TABLES (no dependencies)
-- ============================================================

-- Users table - foundational, no dependencies
CREATE TABLE users (
  user_id BIGINT PRIMARY KEY,
  created_at TIMESTAMPTZ DEFAULT now()
);

DO $$ BEGIN RAISE NOTICE '✅ Created users table'; END$$;

COMMENT ON TABLE users IS 'Core users table - user_id matches Discord snowflake IDs';
COMMENT ON COLUMN users.user_id IS 'Discord user ID (snowflake)';

-- ============================================================
-- DISCORD SERVER CONFIGURATION
-- ============================================================

CREATE TABLE serverstats (
  guild_id BIGINT PRIMARY KEY,
  welcome_channel_id BIGINT,
  goodbye_channel_id BIGINT,
  chat_channel_id BIGINT,
  signup_channel_id BIGINT,
  fixtures_channel_id BIGINT,
  guidelines_channel_id BIGINT,
  tourstate TEXT DEFAULT 'off' CHECK (tourstate IN ('on', 'off')),
  state TEXT DEFAULT 'off' CHECK (state IN ('on', 'off')),
  player_role TEXT DEFAULT 'Tour Player',
  tour_manager_role TEXT DEFAULT 'Tour manager',
  winner_role TEXT DEFAULT '🥇Champ',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

COMMENT ON TABLE serverstats IS 'Per-guild configuration for Discord server features';

-- ============================================================
-- NOTIFICATIONS SYSTEM
-- ============================================================

CREATE TABLE channels (
  channel_id BIGINT PRIMARY KEY,
  guild_id BIGINT NOT NULL,
  channel_name VARCHAR(255) NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE platform_accounts (
  channel_id BIGINT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
  platform_name TEXT NOT NULL,
  platform_id VARCHAR(255) NOT NULL,
  last_updated_content_id VARCHAR(255),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (channel_id, platform_name, platform_id)
);

COMMENT ON TABLE platform_accounts IS 'Tracks social media accounts for notification monitoring';

-- ============================================================
-- LEVELING SYSTEM
-- ============================================================

CREATE TABLE levels (
  id BIGSERIAL PRIMARY KEY,
  guild_id BIGINT NOT NULL,
  user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  xp INTEGER DEFAULT 0 CHECK (xp >= 0),
  level INTEGER DEFAULT 1 CHECK (level >= 1),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (guild_id, user_id)
);

CREATE INDEX idx_levels_user ON levels(user_id);
CREATE INDEX idx_levels_guild ON levels(guild_id);
CREATE INDEX idx_levels_guild_xp ON levels(guild_id, xp DESC);

COMMENT ON TABLE levels IS 'User XP and level progression per guild';

-- ============================================================
-- GAMES & LEADERBOARD SYSTEM
-- ============================================================

CREATE TABLE game_scores (
  id BIGSERIAL PRIMARY KEY,
  guild_id BIGINT NOT NULL,
  game_type TEXT NOT NULL,
  player_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  player_score INTEGER DEFAULT 0 CHECK (player_score >= 0),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (guild_id, game_type, player_id)
);

CREATE INDEX idx_game_scores_guild ON game_scores(guild_id, game_type);
CREATE INDEX idx_game_scores_player ON game_scores(player_id);

CREATE TABLE leaderboard (
  id BIGSERIAL PRIMARY KEY,
  guild_id BIGINT NOT NULL,
  player_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  total_score INTEGER DEFAULT 0 CHECK (total_score >= 0),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (guild_id, player_id)
);

CREATE INDEX idx_leaderboard_guild ON leaderboard(guild_id, total_score DESC);

COMMENT ON TABLE game_scores IS 'Individual game scores per user per guild';
COMMENT ON TABLE leaderboard IS 'Aggregated scores across all games per guild';

-- ============================================================
-- FINTECH / PAYMENT TRACKING
-- ============================================================

CREATE TABLE fintech_payments (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  category TEXT,
  amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
  total_paid NUMERIC(12,2) DEFAULT 0 CHECK (total_paid >= 0),
  status TEXT NOT NULL CHECK (status IN ('pending', 'paid', 'overdue', 'cancelled')),
  frequency TEXT NOT NULL CHECK (frequency IN ('once', 'daily', 'weekly', 'monthly', 'yearly')),
  due_date DATE,
  last_paid_date DATE,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (user_id, name)
);

CREATE INDEX idx_fintech_user ON fintech_payments(user_id);
CREATE INDEX idx_fintech_due_date ON fintech_payments(due_date) WHERE status != 'cancelled';

COMMENT ON TABLE fintech_payments IS 'User bill and payment tracking';
COMMENT ON COLUMN fintech_payments.amount IS 'Payment amount per occurrence';
COMMENT ON COLUMN fintech_payments.total_paid IS 'Cumulative amount paid to date';

-- ============================================================
-- MEDIA LIBRARY (Movies & Series)
-- ============================================================

CREATE TABLE movies (
  id SERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  media_id TEXT UNIQUE NOT NULL, -- External API ID (e.g., TMDB ID)
  overview TEXT,
  genres JSONB,
  release_date DATE,
  poster_url TEXT,
  status TEXT,
  homepage TEXT,
  in_collection JSONB,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_movies_media_id ON movies(media_id);
CREATE INDEX idx_movies_title ON movies(title);

COMMENT ON TABLE movies IS 'Master movies catalog from external API (e.g., TMDB)';
COMMENT ON COLUMN movies.media_id IS 'External API ID to avoid name collision';

CREATE TABLE series (
  id SERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  media_id TEXT UNIQUE NOT NULL, -- External API ID
  overview TEXT,
  genres JSONB,
  status TEXT,
  release_date DATE,
  last_air_date DATE,
  next_episode_date DATE,
  next_episode_number INTEGER,
  next_season_number INTEGER,
  last_episode JSONB,
  seasons JSONB,
  poster_url TEXT,
  homepage TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_series_media_id ON series(media_id);
CREATE INDEX idx_series_title ON series(title);
CREATE INDEX idx_series_next_episode ON series(next_episode_date) WHERE next_episode_date IS NOT NULL;

COMMENT ON TABLE series IS 'Master series catalog from external API';
COMMENT ON COLUMN series.media_id IS 'External API ID to avoid name collision';

-- ============================================================
-- USER MEDIA TRACKING
-- ============================================================

CREATE TABLE user_movies_watched (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  movie_id INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
  watched_date TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (user_id, movie_id)
);

CREATE INDEX idx_user_movies_user ON user_movies_watched(user_id);
CREATE INDEX idx_user_movies_watched_date ON user_movies_watched(user_id, watched_date DESC);

CREATE TABLE user_series_progress (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  series_id INTEGER NOT NULL REFERENCES series(id) ON DELETE CASCADE,
  season INTEGER DEFAULT 0 CHECK (season >= 0),
  episode INTEGER DEFAULT 0 CHECK (episode >= 0),
  status TEXT DEFAULT 'watching' CHECK (status IN ('watching', 'completed', 'dropped', 'on_hold')),
  last_updated TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (user_id, series_id)
);

CREATE INDEX idx_user_series_user ON user_series_progress(user_id);
CREATE INDEX idx_user_series_status ON user_series_progress(user_id, status);

CREATE TABLE user_watchlist (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  media_type TEXT NOT NULL CHECK (media_type IN ('movie', 'series')),
  media_id INTEGER NOT NULL, -- References movies.id or series.id depending on media_type
  status TEXT DEFAULT 'to_watch' CHECK (status IN ('to_watch', 'watching', 'completed')),
  added_date TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (user_id, media_type, media_id)
);

CREATE INDEX idx_watchlist_user ON user_watchlist(user_id);
CREATE INDEX idx_watchlist_status ON user_watchlist(user_id, status);

COMMENT ON TABLE user_watchlist IS 'User watchlist - references internal movies/series tables';
COMMENT ON COLUMN user_watchlist.media_id IS 'References movies.id or series.id depending on media_type';

-- ============================================================
-- USER MEDIA REGISTRY (Performance optimization)
-- ============================================================

CREATE TABLE user_media (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  media_type TEXT NOT NULL CHECK(media_type IN ('movie','series')),
  media_id INTEGER NOT NULL,
  added_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (user_id, media_type, media_id)
);

CREATE INDEX idx_user_media_user ON user_media(user_id, media_type);

COMMENT ON TABLE user_media IS 'Fast lookup registry for all media associated with a user (watched, watching, or on watchlist)';

-- ============================================================
-- TIMESTAMP TRIGGER FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION trigger_set_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION trigger_set_timestamp() IS 'Automatically updates updated_at timestamp on row modification';

-- Attach triggers to all tables with updated_at column
DO $$
DECLARE
  t TEXT;
  trg_name TEXT;
BEGIN
  FOR t IN 
    SELECT tablename 
    FROM pg_tables 
    WHERE schemaname = 'public'
  LOOP
    IF EXISTS (
      SELECT 1 
      FROM information_schema.columns 
      WHERE table_schema='public' 
        AND table_name=t 
        AND column_name='updated_at'
    ) THEN
      trg_name := 'set_timestamp_' || t;
      IF NOT EXISTS (
        SELECT 1 
        FROM pg_trigger 
        WHERE tgname = trg_name
      ) THEN
        EXECUTE format(
          'CREATE TRIGGER %I BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp()', 
          trg_name, 
          t
        );
        RAISE NOTICE 'Created trigger % on table %', trg_name, t;
      END IF;
    END IF;
  END LOOP;
END$$;

-- ============================================================
-- PERMISSIONS
-- ============================================================

GRANT USAGE ON SCHEMA public TO root;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO root;

DO $$
DECLARE 
  seq RECORD;
BEGIN
  FOR seq IN
    SELECT c.oid::regclass AS seqname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind = 'S' AND n.nspname = 'public'
  LOOP
    EXECUTE format('GRANT USAGE, SELECT, UPDATE ON SEQUENCE %s TO %I;', seq.seqname, 'root');
  END LOOP;
  RAISE NOTICE 'Granted sequence permissions to root';
END$$;

-- ============================================================
-- VALIDATION & SUMMARY
-- ============================================================

DO $$
DECLARE
  table_count INTEGER;
  index_count INTEGER;
BEGIN
  SELECT COUNT(*) INTO table_count FROM pg_tables WHERE schemaname = 'public';
  SELECT COUNT(*) INTO index_count FROM pg_indexes WHERE schemaname = 'public';
  
  RAISE NOTICE '=================================';
  RAISE NOTICE '✅ Schema v2.1 applied successfully';
  RAISE NOTICE 'Tables created: %', table_count;
  RAISE NOTICE 'Indexes created: %', index_count;
  RAISE NOTICE '=================================';
END$$;

\echo '🎉 Ouroboros schema v2.1 ready!'