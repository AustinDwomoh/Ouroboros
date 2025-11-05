#!/usr/bin/env python3
"""Migration v2.1: improved SQLite -> Postgres migrator

Features:
- Dry-run mode (--dry-run) that prints planned operations without executing them
- Per-module safe transactions with clear logging
- Robust media discovery (movies, series, watchlists) and user_media registry population
- Ensures users table is populated before inserting foreign keys
- Verbose output for troubleshooting

Usage:
  python migrate_sqlite_to_postgres_v2.py [--dry-run] [--modules serverstats,media]
"""
import os,psycopg2
import sqlite3
import argparse
from dotenv import load_dotenv


# ---------------------------
# Environment Loading
# ---------------------------
load_dotenv()
# ---------------------------
# Database Config
# ---------------------------
PGHOST = os.getenv("PGHOST")
PGPORT = int(os.getenv("PGPORT", "5432"))
PGUSER = os.getenv("PGUSER")
PGPASSWORD = os.getenv("PGPASSWORD")
PGDATABASE = os.getenv("PGDATABASE")
SQLITE_DATA_DIR = os.getenv("SQLITE_DATA_DIR", "data")

def create_pg_conn():
    """
    Blocking (synchronous) Postgres connection for scripts, migrations, etc.
    """
    if not all([PGHOST, PGUSER, PGPASSWORD, PGDATABASE]):
        raise RuntimeError("Postgres credentials missing in .env")
    return psycopg2.connect(
    host=PGHOST,
    port=PGPORT,
    sslmode="require",
    dbname=PGDATABASE,
    user=PGUSER,
    password=PGPASSWORD
)


class Migrator:
    def __init__(self, dry_run=False, verbose=True):
        self.dry_run = dry_run
        self.verbose = verbose

    def log(self, *args, **kwargs):
        if self.verbose:
            print(*args, **kwargs)

    def _pg_execute(self, cur, sql, params=None):
        if self.dry_run:
            self.log(f"  [DRY-RUN] SQL: {sql[:100]}... PARAMS: {params}")
            return cur
        cur.execute(sql, params)
        return cur

    def _sanitize_value(self, val):
        """Sanitize value for insertion into Postgres."""
        if val is None:
            return None
        if isinstance(val, str):
            v = val.strip()
            # treat case-insensitive 'null' or empty as None
            if v.lower() in ('', 'null', 'none', 'nil', 'nan'):
                return None
            return v
        return val


    def _ensure_user(self, cur, user_id):
        """Ensure user exists in users table before inserting related records."""
        if self.dry_run:
            return
        try:
            user_id_int = int(user_id)
            cur.execute(
                "INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING",
                (user_id_int,)
            )
        except (ValueError, TypeError):
            self.log(f"  ⚠️  Invalid user_id: {user_id}")

    # ---------------- serverstats ----------------
    def migrate_serverstats(self):
        sqlite_path = os.path.join(SQLITE_DATA_DIR, "serverstats.db")
        self.log('\n🧩 serverstats')
        if not os.path.exists(sqlite_path):
            self.log('  no serverstats.db found, skipping')
            return 0
        
        sconn = sqlite3.connect(sqlite_path)
        scur = sconn.cursor()
        try:
            scur.execute('SELECT * FROM serverstats')
        except sqlite3.OperationalError:
            self.log('  no serverstats table in sqlite; skipping')
            sconn.close()
            return 0

        rows = scur.fetchall()
        if not rows:
            self.log('  no rows to migrate')
            sconn.close()
            return 0

        pg = create_pg_conn()
        migrated = 0
        try:
            with pg.cursor() as cur:
                for r in rows:
                    params = tuple(self._sanitize_value(x) for x in r)
                    sql = '''
                    INSERT INTO serverstats (
                      guild_id, welcome_channel_id, goodbye_channel_id, chat_channel_id,
                      signup_channel_id, fixtures_channel_id, guidelines_channel_id,
                      tourstate, state, player_role, tour_manager_role, winner_role
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (guild_id) DO UPDATE SET
                      welcome_channel_id = EXCLUDED.welcome_channel_id,
                      goodbye_channel_id = EXCLUDED.goodbye_channel_id,
                      chat_channel_id = EXCLUDED.chat_channel_id,
                      signup_channel_id = EXCLUDED.signup_channel_id,
                      fixtures_channel_id = EXCLUDED.fixtures_channel_id,
                      guidelines_channel_id = EXCLUDED.guidelines_channel_id,
                      tourstate = EXCLUDED.tourstate,
                      state = EXCLUDED.state,
                      player_role = EXCLUDED.player_role,
                      tour_manager_role = EXCLUDED.tour_manager_role,
                      winner_role = EXCLUDED.winner_role,
                      updated_at = now()
                    '''
                    self._pg_execute(cur, sql, params)
                    migrated += 1
            if not self.dry_run:
                pg.commit()
        finally:
            pg.close()
            sconn.close()
        self.log(f'  ✅ migrated serverstats rows: {migrated}')
        return migrated

    # ---------------- leveling ----------------
    def migrate_leveling(self):
        sqlite_path = os.path.join(SQLITE_DATA_DIR, 'leveling.db')
        self.log('\n🎮 leveling')
        if not os.path.exists(sqlite_path):
            self.log('  no leveling.db found, skipping')
            return 0
        
        sconn = sqlite3.connect(sqlite_path)
        scur = sconn.cursor()
        scur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'levels_%'")
        tables = [r[0] for r in scur.fetchall()]
        if not tables:
            self.log('  no levels_* tables found')
            sconn.close()
            return 0

        pg = create_pg_conn()
        migrated = 0
        try:
            with pg.cursor() as cur:
                for table in tables:
                    guild_id = table.split('_', 1)[1]
                    scur.execute(f"SELECT user_id, xp, level FROM '{table}'")
                    for user_id, xp, level in scur.fetchall():
                        # Ensure user exists first
                        self._ensure_user(cur, user_id)
                        
                        params = (guild_id, user_id, xp or 0, level or 1)
                        sql = '''
                        INSERT INTO levels (guild_id, user_id, xp, level)
                        VALUES (%s,%s,%s,%s)
                        ON CONFLICT (guild_id, user_id) DO UPDATE SET 
                          xp = EXCLUDED.xp, 
                          level = EXCLUDED.level,
                          updated_at = now()
                        '''
                        self._pg_execute(cur, sql, params)
                        print()
                        migrated += 1
                        print(migrated)
            if not self.dry_run:
                pg.commit()
        finally:
            pg.close()
            sconn.close()
        self.log(f'  ✅ migrated leveling rows: {migrated}')
        return migrated

    # ---------------- games ----------------
    def migrate_games(self):
        sqlite_path = os.path.join(SQLITE_DATA_DIR, 'game_records.db')
        self.log('\n🏆 games')
        if not os.path.exists(sqlite_path):
            self.log('  no game_records.db found, skipping')
            return 0
        
        sconn = sqlite3.connect(sqlite_path)
        scur = sconn.cursor()
        scur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        all_tables = [r[0] for r in scur.fetchall()]

        pg = create_pg_conn()
        migrated = 0
        try:
            with pg.cursor() as cur:
                for t in all_tables:
                    if '_scores_' in t:
                        parts = t.split('_scores_')
                        if len(parts) != 2:
                            continue
                        game_type, guild_id = parts
                        scur.execute(f"SELECT player_id, player_score FROM '{t}'")
                        for player_id, player_score in scur.fetchall():
                            # Ensure user exists first
                            self._ensure_user(cur, player_id)
                            
                            sql = '''
                            INSERT INTO game_scores (guild_id, game_type, player_id, player_score)
                            VALUES (%s,%s,%s,%s)
                            ON CONFLICT (guild_id, game_type, player_id) DO UPDATE SET 
                              player_score = EXCLUDED.player_score,
                              updated_at = now()
                            '''
                            self._pg_execute(cur, sql, (guild_id, game_type, player_id, player_score or 0))
                            migrated += 1
                    elif t.startswith('leaderboard_'):
                        guild_id = t.split('leaderboard_')[1]
                        scur.execute(f"SELECT player_id, total_score FROM '{t}'")
                        for player_id, total_score in scur.fetchall():
                            # Ensure user exists first
                            self._ensure_user(cur, player_id)
                            
                            sql = '''
                            INSERT INTO leaderboard (guild_id, player_id, total_score)
                            VALUES (%s,%s,%s)
                            ON CONFLICT (guild_id, player_id) DO UPDATE SET 
                              total_score = EXCLUDED.total_score,
                              updated_at = now()
                            '''
                            self._pg_execute(cur, sql, (guild_id, player_id, total_score or 0))
                            migrated += 1
            if not self.dry_run:
                pg.commit()
        finally:
            pg.close()
            sconn.close()
        self.log(f'  ✅ migrated game rows: {migrated}')
        return migrated

    # ---------------- fintech ----------------
    def migrate_fintech(self):
        sqlite_path = os.path.join(SQLITE_DATA_DIR, 'finance.db')
        self.log('\n💰 fintech')
        if not os.path.exists(sqlite_path):
            self.log('  no finance.db found, skipping')
            return 0
        
        sconn = sqlite3.connect(sqlite_path)
        scur = sconn.cursor()
        migrated = 0
        pg = create_pg_conn()
        
        try:
            with pg.cursor() as cur:
                # Dynamic fintech tables (user-specific payment tables)
                scur.execute("SELECT name FROM sqlite_master WHERE name LIKE '%_fintech'")
                tables = [r[0] for r in scur.fetchall()]
                
                for t in tables:
                    try:
                        scur.execute(f"SELECT name, category, amount, total_paid, status, frequency, due_date, last_paid_date FROM '{t}'")
                    except Exception as e:
                        self.log(f'  ⚠️  Error reading table {t}: {e}')
                        continue
                    
                    user_id = t.split('_fintech')[0]
                    try:
                        user_id_int = int(user_id)
                    except Exception:
                        self.log(f'  ⚠️  Skipping fintech table {t}: cannot derive user_id')
                        continue
                    
                    # Ensure user exists first
                    self._ensure_user(cur, user_id_int)
                    
                    for row in scur.fetchall():
                        row = list(row)
                        # row = [name, category, amount, total_paid, status, frequency, due_date, last_paid_date]
                        
                        # -------------------------
                        # Normalize schema enums
                        # -------------------------
                        status = str(row[4]).strip().lower() if row[4] else None
                        freq   = str(row[5]).strip().lower() if row[5] else None

                        # Status normalization
                        if status in ('reminded', 'remind', 'notify', 'active'):
                            status = 'pending'
                        elif status in ('done', 'complete', 'finished', 'success', 'paid_off'):
                            status = 'paid'
                        elif status in ('late', 'missed', 'unpaid'):
                            status = 'overdue'
                        elif status not in ('pending', 'paid', 'overdue', 'cancelled'):
                            status = 'pending'

                        # Frequency normalization
                        if freq:
                            freq = freq.lower()
                        if freq not in ('once', 'daily', 'weekly', 'monthly', 'yearly'):
                            # Catch uppercase or misspelled variants
                            if freq in ('one-time', 'one time', 'single'):
                                freq = 'once'
                            elif freq in ('month', 'months', 'every month'):
                                freq = 'monthly'
                            elif freq in ('week', 'weeks'):
                                freq = 'weekly'
                            elif freq in ('day', 'days'):
                                freq = 'daily'
                            elif freq in ('year', 'years', 'annually'):
                                freq = 'yearly'
                            else:
                                freq = 'monthly'  # sensible default

                        # Apply normalized values back to row
                        row[4] = status
                        row[5] = freq

                        # -------------------------
                        # Build parameter tuple
                        # -------------------------
                        params = (user_id_int, *row)

                        sql = '''
                        INSERT INTO fintech_payments (user_id, name, category, amount, total_paid, status, frequency, due_date, last_paid_date)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (user_id, name) DO UPDATE SET
                        category = EXCLUDED.category,
                        amount = EXCLUDED.amount,
                        total_paid = EXCLUDED.total_paid,
                        status = EXCLUDED.status,
                        frequency = EXCLUDED.frequency,
                        due_date = EXCLUDED.due_date,
                        last_paid_date = EXCLUDED.last_paid_date,
                        updated_at = now()
                        '''
                        self._pg_execute(cur, sql, params)
                        migrated += 1

            if not self.dry_run:
                pg.commit()
        finally:
            pg.close()
            sconn.close()
        self.log(f'  ✅ migrated fintech rows: {migrated}')
        return migrated

    # ---------------- media (robust) ----------------
    def migrate_media(self):
        sqlite_path = os.path.join(SQLITE_DATA_DIR, 'mediarecords.db')
        self.log('\n🎬 media')
        if not os.path.exists(sqlite_path):
            self.log('  no mediarecords.db found, skipping')
            return 0
        
        sconn = sqlite3.connect(sqlite_path)
        scur = sconn.cursor()
        scur.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")
        all_tables = [r[0] for r in scur.fetchall()]
        
        movie_tables = [t for t in all_tables if t.lower().endswith('_movies') and 'watch' not in t.lower()]
        series_tables = [t for t in all_tables if t.lower().endswith('_series') and 'watch' not in t.lower()]
        watchlist_tables = [t for t in all_tables if 'watch_list' in t.lower() or 'watchlist' in t.lower()]

        pg = create_pg_conn()
        migrated = 0

        def upsert_movie(cur, title, media_id=None):
            """Insert or update movie, return internal movie.id"""
            title = self._sanitize_value(title)
            if title is None:
                return None
            if self.dry_run:
                self.log(f'  [DRY-RUN] upsert movie: {title}')
                return None
            
            # Try to find by media_id first (external API ID)
            if media_id:
                cur.execute("SELECT id FROM movies WHERE media_id=%s", (media_id,))
                r = cur.fetchone()
                if r:
                    return r[0]
            
            # Fall back to title lookup
            cur.execute("SELECT id FROM movies WHERE title=%s", (title,))
            r = cur.fetchone()
            if r:
                return r[0]
            
            # Insert new movie (media_id required by schema, generate placeholder if missing)
            if not media_id:
                media_id = f"unknown_{title.lower().replace(' ', '_')}"
            
            cur.execute(
                "INSERT INTO movies (title, media_id) VALUES (%s,%s) RETURNING id",
                (title, media_id)
            )
            return cur.fetchone()[0]

        def upsert_series(cur, title, media_id=None):
            """Insert or update series, return internal series.id"""
            title = self._sanitize_value(title)
            if title is None:
                return None
            if self.dry_run:
                self.log(f'  [DRY-RUN] upsert series: {title}')
                return None
            
            # Try to find by media_id first
            if media_id:
                cur.execute("SELECT id FROM series WHERE media_id=%s", (media_id,))
                r = cur.fetchone()
                if r:
                    return r[0]
            
            # Fall back to title lookup
            cur.execute("SELECT id FROM series WHERE title=%s", (title,))
            r = cur.fetchone()
            if r:
                return r[0]
            
            # Insert new series (media_id required by schema)
            if not media_id:
                media_id = f"unknown_{title.lower().replace(' ', '_')}"
            
            cur.execute(
                "INSERT INTO series (title, media_id) VALUES (%s,%s) RETURNING id",
                (title, media_id)
            )
            return cur.fetchone()[0]

        try:
            with pg.cursor() as cur:
                # Movies
                for t in movie_tables:
                    user_raw = t.rsplit('_Movies', 1)[0] if '_Movies' in t else t.rsplit('_movies', 1)[0]
                    try:
                        user_id = int(user_raw)
                    except Exception:
                        self.log(f'  ⚠️  Cannot parse user_id from table {t}')
                        continue
                    
                    # Ensure user exists
                    self._ensure_user(cur, user_id)
                    
                    scur.execute(f"PRAGMA table_info('{t}')")
                    cols = [r[1] for r in scur.fetchall()]
                    title_idx = cols.index('title') if 'title' in cols else 0
                    date_idx = None
                    for cand in ('date', 'watched_date', 'added_date', 'timestamp'):
                        if cand in cols:
                            date_idx = cols.index(cand)
                            break
                    
                    rows = scur.execute(f"SELECT * FROM '{t}'").fetchall()
                    for row in rows:
                        title = row[title_idx] if len(row) > title_idx else None
                        date = row[date_idx] if (date_idx is not None and len(row) > date_idx) else None
                        title_s = self._sanitize_value(title)
                        if not title_s:
                            continue
                        
                        mid = upsert_movie(cur, title_s)
                        if not self.dry_run and mid:
                            cur.execute(
                                "INSERT INTO user_movies_watched (user_id, movie_id, watched_date) VALUES (%s,%s,%s) ON CONFLICT (user_id, movie_id) DO NOTHING",
                                (user_id, mid, self._sanitize_value(date))
                            )
                            cur.execute(
                                "INSERT INTO user_media (user_id, media_type, media_id) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                                (user_id, 'movie', mid)
                            )
                        migrated += 1

                # Series
                for t in series_tables:
                    user_raw = t.rsplit('_Series', 1)[0] if '_Series' in t else t.rsplit('_series', 1)[0]
                    try:
                        user_id = int(user_raw)
                    except Exception:
                        self.log(f'  ⚠️  Cannot parse user_id from table {t}')
                        continue
                    
                    # Ensure user exists
                    self._ensure_user(cur, user_id)
                    
                    scur.execute(f"PRAGMA table_info('{t}')")
                    cols = [r[1] for r in scur.fetchall()]
                    title_idx = cols.index('title') if 'title' in cols else 0
                    season_idx = cols.index('season') if 'season' in cols else None
                    episode_idx = cols.index('episode') if 'episode' in cols else None
                    status_idx = cols.index('status') if 'status' in cols else None
                    date_idx = None
                    for cand in ('date', 'watched_date', 'last_watched', 'timestamp'):
                        if cand in cols:
                            date_idx = cols.index(cand)
                            break
                    
                    rows = scur.execute(f"SELECT * FROM '{t}'").fetchall()
                    for row in rows:
                        title = row[title_idx] if len(row) > title_idx else None
                        season = row[season_idx] if (season_idx is not None and len(row) > season_idx) else 0
                        episode = row[episode_idx] if (episode_idx is not None and len(row) > episode_idx) else 0
                        status = row[status_idx] if (status_idx is not None and len(row) > status_idx) else 'watching'
                        date = row[date_idx] if (date_idx is not None and len(row) > date_idx) else None
                        
                        title_s = self._sanitize_value(title)
                        if not title_s:
                            continue
                        
                        # Map old status values to new schema constraints
                        if status not in ('watching', 'completed', 'dropped', 'on_hold'):
                            status = 'watching'
                        
                        sid = upsert_series(cur, title_s)
                        if not self.dry_run and sid:
                            cur.execute(
                                """
                                INSERT INTO user_series_progress (user_id, series_id, season, episode, status, last_updated)
                                VALUES (%s,%s,%s,%s,%s,%s)
                                ON CONFLICT (user_id, series_id) DO UPDATE SET
                                  season = EXCLUDED.season,
                                  episode = EXCLUDED.episode,
                                  status = EXCLUDED.status,
                                  last_updated = EXCLUDED.last_updated,
                                  updated_at = now()
                                """,
                                (user_id, sid, season, episode, status, self._sanitize_value(date))
                            )
                            cur.execute(
                                "INSERT INTO user_media (user_id, media_type, media_id) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                                (user_id, 'series', sid)
                            )
                        migrated += 1

                # Watchlists
                for t in watchlist_tables:
                    low = t.lower()
                    if '_watch_list_' in low:
                        parts = t.split('_watch_list_')
                        user_raw = parts[0]
                        media_kind = 'movie' if parts[1].lower().endswith('movies') else 'series'
                    elif 'watchlist' in low:
                        if low.endswith('_movies') or low.endswith('_series'):
                            user_raw = t.rsplit('_', 2)[0]
                            media_kind = 'movie' if low.endswith('_movies') else 'series'
                        else:
                            user_raw = t.split('_', 1)[0]
                            media_kind = 'movie'
                    else:
                        user_raw = t.split('_', 1)[0]
                        media_kind = 'movie'
                    
                    try:
                        user_id = int(user_raw)
                    except Exception:
                        self.log(f'  ⚠️  Cannot parse user_id from watchlist table {t}')
                        continue
                    
                    # Ensure user exists
                    self._ensure_user(cur, user_id)
                    
                    scur.execute(f"PRAGMA table_info('{t}')")
                    cols = [r[1] for r in scur.fetchall()]
                    title_idx = cols.index('title') if 'title' in cols else 0
                    date_idx = None
                    for cand in ('date', 'added_date', 'timestamp'):
                        if cand in cols:
                            date_idx = cols.index(cand)
                            break
                    
                    rows = scur.execute(f"SELECT * FROM '{t}'").fetchall()
                    for row in rows:
                        title = row[title_idx] if len(row) > title_idx else None
                        date = row[date_idx] if (date_idx is not None and len(row) > date_idx) else None
                        title_s = self._sanitize_value(title)
                        if not title_s:
                            continue
                        
                        if media_kind == 'movie':
                            mid = upsert_movie(cur, title_s)
                            if not self.dry_run and mid:
                                cur.execute(
                                    "INSERT INTO user_watchlist (user_id, media_type, media_id, added_date) VALUES (%s,%s,%s,%s) ON CONFLICT (user_id, media_type, media_id) DO NOTHING",
                                    (user_id, 'movie', mid, self._sanitize_value(date))
                                )
                                cur.execute(
                                    "INSERT INTO user_media (user_id, media_type, media_id) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                                    (user_id, 'movie', mid)
                                )
                        else:
                            sid = upsert_series(cur, title_s)
                            if not self.dry_run and sid:
                                cur.execute(
                                    "INSERT INTO user_watchlist (user_id, media_type, media_id, added_date) VALUES (%s,%s,%s,%s) ON CONFLICT (user_id, media_type, media_id) DO NOTHING",
                                    (user_id, 'series', sid, self._sanitize_value(date))
                                )
                                cur.execute(
                                    "INSERT INTO user_media (user_id, media_type, media_id) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                                    (user_id, 'series', sid)
                                )
                        migrated += 1

            if not self.dry_run:
                pg.commit()
        finally:
            pg.close()
            sconn.close()
        self.log(f'  ✅ migrated media rows: {migrated}')
        return migrated

    def run_all(self, modules=None):
        """Run all migrations or specified modules."""
        all_modules = {
            #'serverstats': self.migrate_serverstats,
            #'leveling': self.migrate_leveling,
            #'games': self.migrate_games,
            'fintech': self.migrate_fintech,
            #'media': self.migrate_media,
        }
        
        if modules:
            modules_to_run = {k: v for k, v in all_modules.items() if k in modules}
        else:
            modules_to_run = all_modules
        
        self.log('\n' + '='*50)
        self.log('🚀 Starting migration...')
        if self.dry_run:
            self.log('⚠️  DRY-RUN MODE - No changes will be committed')
        self.log('='*50)
        
        total = 0
        for name, func in modules_to_run.items():
            try:
                count = func()
                total += count
            except Exception as e:
                self.log(f'\n❌ Error in {name}: {e}')
                import traceback
                traceback.print_exc()
        
        self.log('\n' + '='*50)
        self.log(f'✅ Migration complete! Total rows migrated: {total}')
        self.log('='*50)
        return total


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Migrate SQLite data to Postgres')
    parser.add_argument('--dry-run', action='store_true', help='Print operations without executing')
    parser.add_argument('--modules', type=str, help='Comma-separated list of modules to migrate')
    parser.add_argument('--quiet', action='store_true', help='Reduce output verbosity')
    
    args = parser.parse_args()
    
    modules_list = None
    if args.modules:
        modules_list = [m.strip() for m in args.modules.split(',')]
    
    migrator = Migrator(dry_run=args.dry_run, verbose=not args.quiet)
    migrator.run_all(modules=modules_list)