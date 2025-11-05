-- ============================================================
-- PostgreSQL Normalized Schema v2 for Ouroboros
-- - builds on pg_schema.sql but adds a user_media registry and
--   installs timestamp triggers on commonly-updated tables.
-- Created: 2025-10-31 (v2)
-- ============================================================
\set ON_ERROR_STOP on
\echo '🔧 Running Ouroboros schema v2...'

DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

DO $$ BEGIN RAISE NOTICE '✅ Extension uuid-ossp ensured.'; END$$;

-- Re-create base objects (copied & extended from v1)

-- SERVERSTATS
CREATE TABLE IF NOT EXISTS serverstats (
  guild_id BIGINT PRIMARY KEY,
  welcome_channel_id BIGINT,
  goodbye_channel_id BIGINT,
  chat_channel_id BIGINT,
  signup_channel_id BIGINT,
  fixtures_channel_id BIGINT,
  guidelines_channel_id BIGINT,
  tourstate TEXT DEFAULT 'off',
  state TEXT DEFAULT 'off',
  player_role TEXT DEFAULT 'Tour Player',
  tour_manager_role TEXT DEFAULT 'Tour manager',
  winner_role TEXT DEFAULT '🥇Champ',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- NOTIFICATIONS
CREATE TABLE IF NOT EXISTS channels (
  channel_id BIGINT PRIMARY KEY,
  guild_id BIGINT NOT NULL,
  channel_name VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS platform_accounts (
  channel_id BIGINT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
  platform_name TEXT NOT NULL,
  platform_id VARCHAR(255) NOT NULL,
  last_updated_content_id VARCHAR(255),
  PRIMARY KEY (channel_id, platform_name, platform_id)
);

-- LEVELING
CREATE TABLE IF NOT EXISTS levels (
  id BIGSERIAL PRIMARY KEY,
  guild_id BIGINT NOT NULL,
  user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  xp INTEGER DEFAULT 0,
  level INTEGER DEFAULT 1,
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (guild_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_levels_user  ON levels(user_id);
CREATE INDEX IF NOT EXISTS idx_levels_guild ON levels(guild_id);

-- GAMES & LEADERBOARD
CREATE TABLE IF NOT EXISTS game_scores (
  id BIGSERIAL PRIMARY KEY,
  guild_id BIGINT NOT NULL,
  game_type TEXT NOT NULL,
  player_id BIGINT NOT NULL,
  player_score INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (guild_id, game_type, player_id)
);

CREATE TABLE IF NOT EXISTS leaderboard (
  id BIGSERIAL PRIMARY KEY,
  guild_id BIGINT NOT NULL,
  player_id BIGINT NOT NULL,
  total_score INTEGER DEFAULT 0,
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (guild_id, player_id)
);


CREATE TABLE IF NOT EXISTS users (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS fintech_payments (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  category TEXT,
  amount NUMERIC(12,2) NOT NULL,
  total_paid NUMERIC(12,2) DEFAULT 0,
  status TEXT NOT NULL,
  frequency TEXT NOT NULL,
  due_date DATE,
  last_paid_date DATE,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (user_id, name)
);

-- MEDIA (movies, series, watchlists, registry)
CREATE TABLE IF NOT EXISTS movies (
  id SERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  release_date DATE,
  original_title TEXT,
  overview TEXT,
  genres JSONB,
  poster_url TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS series (
  id SERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  first_air_date DATE,
  last_air_date DATE,
  status TEXT,
  poster_url TEXT,
  seasons JSONB,
  last_episode JSONB,
  next_episode_date DATE,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_movies_watched (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  movie_id INTEGER REFERENCES movies(id) ON DELETE CASCADE,
  watched_date TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (user_id, movie_id)
);

CREATE TABLE IF NOT EXISTS user_series_progress (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  series_id INTEGER REFERENCES series(id) ON DELETE CASCADE,
  season INTEGER DEFAULT 0,
  episode INTEGER DEFAULT 0,
  status TEXT DEFAULT 'watching',
  last_updated TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (user_id, series_id)
);

CREATE TABLE IF NOT EXISTS user_watchlist (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  media_type TEXT CHECK (media_type IN ('movie', 'series')),
  media_id INTEGER,
  title TEXT,
  extra TEXT,
  status TEXT DEFAULT 'to_watch',
  release_date DATE,
  added_date TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  next_release_date DATE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_watchlist_unique
ON user_watchlist (user_id, media_type, COALESCE(media_id::text, title));

-- Registry table used by app code to quickly enumerate media per user
CREATE TABLE IF NOT EXISTS user_media (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  media_type TEXT NOT NULL CHECK(media_type IN ('movie','series')),
  media_id INTEGER NOT NULL,
  added_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (user_id, media_type, media_id)
);

-- TIMESTAMP TRIGGER FUNCTION
CREATE OR REPLACE FUNCTION trigger_set_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Attach triggers safely to tables that have updated_at column
DO $$
DECLARE
  t TEXT;
  trg_name TEXT;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name=t AND column_name='updated_at') THEN
      trg_name := 'set_timestamp_' || t;
      IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = trg_name) THEN
        EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp()', trg_name, t);
      END IF;
    END IF;
  END LOOP;
END$$;

-- PERMISSIONS (grant to PG user from env expected to be set by operator)
GRANT USAGE ON SCHEMA public TO root;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO root;

DO $$
DECLARE seq RECORD;
BEGIN
  FOR seq IN
    SELECT c.oid::regclass AS seqname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind = 'S' AND n.nspname = 'public'
  LOOP
    EXECUTE format('GRANT USAGE, SELECT, UPDATE ON SEQUENCE %s TO %I;', seq.seqname, 'root');
  END LOOP;
END$$;

\echo '🎉 Schema v2 applied.'
