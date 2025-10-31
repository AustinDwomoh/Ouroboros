#!/usr/bin/env python3
"""Migration v2: improved SQLite -> Postgres migrator

Features:
- Dry-run mode (--dry-run) that prints planned operations without executing them
- Per-module safe transactions with clear logging
- Robust media discovery (movies, series, watchlists) and user_media registry population
- Verbose output for troubleshooting

Usage:
  & .\lapworld\Scripts\python.exe .\migrations\migrate_sqlite_to_postgres_v2.py [--dry-run] [--modules serverstats,media]
"""
import os
import sqlite3
import psycopg2
import argparse
from dotenv import load_dotenv

load_dotenv()

PGHOST = os.getenv("PGHOST")
PGPORT = int(os.getenv("PGPORT", "5432"))
PGUSER = os.getenv("PGUSER")
PGPASSWORD = os.getenv("PGPASSWORD")
PGDATABASE = os.getenv("PGDATABASE")
SQLITE_DATA_DIR = os.getenv("SQLITE_DATA_DIR", "data")

if not (PGHOST and PGUSER and PGPASSWORD and PGDATABASE):
    raise SystemExit("Missing Postgres credentials. Set PGHOST, PGUSER, PGPASSWORD, PGDATABASE in .env")


def get_pg_conn():
    return psycopg2.connect(host=PGHOST, port=PGPORT, user=PGUSER, password=PGPASSWORD, dbname=PGDATABASE)


def _sanitize_value(v):
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        if s == "" or s.lower() in ("null", "none", "n/a"):
            return None
        if s.isdigit():
            try:
                return int(s)
            except Exception:
                pass
        return s
    return v


class Migrator:
    def __init__(self, dry_run=False, verbose=True):
        self.dry_run = dry_run
        self.verbose = verbose

    def log(self, *args, **kwargs):
        if self.verbose:
            print(*args, **kwargs)

    def _pg_execute(self, cur, sql, params=None):
        if self.dry_run:
            self.log("DRY RUN SQL:", sql.strip().splitlines()[0], "... params=", params)
            return None
        cur.execute(sql, params)
        return cur

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

        pg = get_pg_conn()
        migrated = 0
        try:
            with pg.cursor() as cur:
                for r in rows:
                    params = tuple(_sanitize_value(x) for x in r)
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
                      winner_role = EXCLUDED.winner_role
                    '''
                    self._pg_execute(cur, sql, params)
                    migrated += 1
            if not self.dry_run:
                pg.commit()
        finally:
            pg.close(); sconn.close()
        self.log(f'  migrated serverstats rows: {migrated}')
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

        pg = get_pg_conn()
        migrated = 0
        try:
            with pg.cursor() as cur:
                for table in tables:
                    guild_id = table.split('_', 1)[1]
                    scur.execute(f"SELECT user_id, xp, level FROM '{table}'")
                    for user_id, xp, level in scur.fetchall():
                        params = (guild_id, user_id, xp or 0, level or 1)
                        sql = '''
                        INSERT INTO levels (guild_id, user_id, xp, level)
                        VALUES (%s,%s,%s,%s)
                        ON CONFLICT (guild_id, user_id) DO UPDATE SET xp = EXCLUDED.xp, level = EXCLUDED.level
                        '''
                        self._pg_execute(cur, sql, params)
                        migrated += 1
            if not self.dry_run:
                pg.commit()
        finally:
            pg.close(); sconn.close()
        self.log(f'  migrated leveling rows: {migrated}')
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
        pg = get_pg_conn()
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
                            sql = '''
                            INSERT INTO game_scores (guild_id, game_type, player_id, player_score)
                            VALUES (%s,%s,%s,%s)
                            ON CONFLICT (guild_id, game_type, player_id) DO UPDATE SET player_score = EXCLUDED.player_score
                            '''
                            self._pg_execute(cur, sql, (guild_id, game_type, player_id, player_score or 0))
                            migrated += 1
                    elif t.startswith('leaderboard_'):
                        guild_id = t.split('leaderboard_')[1]
                        scur.execute(f"SELECT player_id, total_score FROM '{t}'")
                        for player_id, total_score in scur.fetchall():
                            sql = '''
                            INSERT INTO leaderboard (guild_id, player_id, total_score)
                            VALUES (%s,%s,%s)
                            ON CONFLICT (guild_id, player_id) DO UPDATE SET total_score = EXCLUDED.total_score
                            '''
                            self._pg_execute(cur, sql, (guild_id, player_id, total_score or 0))
                            migrated += 1
            if not self.dry_run:
                pg.commit()
        finally:
            pg.close(); sconn.close()
        self.log(f'  migrated game rows: {migrated}')
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
        pg = get_pg_conn()
        try:
            # user_payments
            try:
                scur.execute("SELECT user_id FROM user_payments")
                with pg.cursor() as cur:
                    for (user_id,) in scur.fetchall():
                        self._pg_execute(cur, "INSERT INTO user_payments (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING", (user_id,))
            except sqlite3.OperationalError:
                self.log('  no user_payments table in sqlite')

            # dynamic fintech tables
            scur.execute("SELECT name FROM sqlite_master WHERE name LIKE '%_fintech'")
            tables = [r[0] for r in scur.fetchall()]
            with pg.cursor() as cur:
                for t in tables:
                    try:
                        scur.execute(f"SELECT name, category, amount, total_paid, status, frequency, due_date, last_paid_date FROM '{t}'")
                    except Exception:
                        continue
                    user_id = t.split('_fintech')[0]
                    try:
                        user_id_int = int(user_id)
                    except Exception:
                        user_id_int = None
                    if user_id_int is None:
                        self.log(f'  skipping fintech table {t}: cannot derive user_id')
                        continue
                    for row in scur.fetchall():
                        params = (user_id_int, *row)
                        sql = '''
                        INSERT INTO fintech_payments (user_id, name, category, amount, total_paid, status, frequency, due_date, last_paid_date)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (user_id, name) DO UPDATE SET
                          amount = EXCLUDED.amount, total_paid = EXCLUDED.total_paid, status = EXCLUDED.status,
                          frequency = EXCLUDED.frequency, due_date = EXCLUDED.due_date, last_paid_date = EXCLUDED.last_paid_date
                        '''
                        self._pg_execute(cur, sql, params)
                        migrated += 1
            if not self.dry_run:
                pg.commit()
        finally:
            pg.close(); sconn.close()
        self.log(f'  migrated fintech rows: {migrated}')
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

        pg = get_pg_conn()
        migrated = 0

        def upsert_movie(cur, title):
            title = _sanitize_value(title)
            if title is None:
                return None
            if self.dry_run:
                self.log('  DRY upsert movie', title)
                return None
            cur.execute("SELECT id FROM movies WHERE title=%s", (title,))
            r = cur.fetchone()
            if r:
                return r[0]
            cur.execute("INSERT INTO movies (title) VALUES (%s) RETURNING id", (title,))
            return cur.fetchone()[0]

        def upsert_series(cur, title):
            title = _sanitize_value(title)
            if title is None:
                return None
            if self.dry_run:
                self.log('  DRY upsert series', title)
                return None
            cur.execute("SELECT id FROM series WHERE title=%s", (title,))
            r = cur.fetchone()
            if r:
                return r[0]
            cur.execute("INSERT INTO series (title) VALUES (%s) RETURNING id", (title,))
            return cur.fetchone()[0]

        try:
            with pg.cursor() as cur:
                # Movies
                for t in movie_tables:
                    user_raw = t.rsplit('_Movies', 1)[0]
                    try:
                        user_id = int(user_raw)
                    except Exception:
                        user_id = user_raw
                    scur.execute(f"PRAGMA table_info('{t}')")
                    cols = [r[1] for r in scur.fetchall()]
                    title_idx = cols.index('title') if 'title' in cols else 0
                    date_idx = None
                    for cand in ('date','watched_date','added_date','timestamp'):
                        if cand in cols:
                            date_idx = cols.index(cand); break
                    rows = scur.execute(f"SELECT * FROM '{t}'").fetchall()
                    for row in rows:
                        title = row[title_idx] if len(row) > title_idx else None
                        date = row[date_idx] if (date_idx is not None and len(row) > date_idx) else None
                        title_s = _sanitize_value(title)
                        if not title_s:
                            continue
                        mid = upsert_movie(cur, title_s)
                        if not self.dry_run:
                            cur.execute("INSERT INTO user_movies_watched (user_id, movie_id, watched_date) VALUES (%s,%s,%s) ON CONFLICT (user_id, movie_id) DO NOTHING", (user_id, mid, _sanitize_value(date)))
                            cur.execute("INSERT INTO user_media (user_id, media_type, media_id) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (user_id, 'movie', mid))
                        migrated += 1

                # Series
                for t in series_tables:
                    user_raw = t.rsplit('_Series', 1)[0]
                    try:
                        user_id = int(user_raw)
                    except Exception:
                        user_id = user_raw
                    scur.execute(f"PRAGMA table_info('{t}')")
                    cols = [r[1] for r in scur.fetchall()]
                    title_idx = cols.index('title') if 'title' in cols else 0
                    season_idx = cols.index('season') if 'season' in cols else None
                    episode_idx = cols.index('episode') if 'episode' in cols else None
                    progress_idx = cols.index('progress') if 'progress' in cols else None
                    date_idx = None
                    for cand in ('date','watched_date','last_watched','timestamp'):
                        if cand in cols:
                            date_idx = cols.index(cand); break
                    rows = scur.execute(f"SELECT * FROM '{t}'").fetchall()
                    for row in rows:
                        title = row[title_idx] if len(row) > title_idx else None
                        season = row[season_idx] if (season_idx is not None and len(row) > season_idx) else None
                        episode = row[episode_idx] if (episode_idx is not None and len(row) > episode_idx) else None
                        progress = row[progress_idx] if (progress_idx is not None and len(row) > progress_idx) else None
                        date = row[date_idx] if (date_idx is not None and len(row) > date_idx) else None
                        title_s = _sanitize_value(title)
                        if not title_s:
                            continue
                        sid = upsert_series(cur, title_s)
                        # schema v2 stores 'status' rather than a raw 'progress' numeric column
                        status_val = None
                        if progress is not None:
                            # coerce numeric progress to a short status string if needed
                            try:
                                status_val = str(progress)
                            except Exception:
                                status_val = progress
                        if not self.dry_run:
                            cur.execute(
                                """
                                INSERT INTO user_series_progress (user_id, series_id, season, episode, status, updated_at)
                                VALUES (%s,%s,%s,%s,%s,%s)
                                ON CONFLICT (user_id, series_id) DO UPDATE SET
                                  season = EXCLUDED.season,
                                  episode = EXCLUDED.episode,
                                  status = EXCLUDED.status,
                                  updated_at = EXCLUDED.updated_at
                                """,
                                (user_id, sid, season, episode, status_val, _sanitize_value(date)),
                            )
                            cur.execute("INSERT INTO user_media (user_id, media_type, media_id) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (user_id, 'series', sid))
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
                        user_id = user_raw
                    scur.execute(f"PRAGMA table_info('{t}')")
                    cols = [r[1] for r in scur.fetchall()]
                    title_idx = cols.index('title') if 'title' in cols else 0
                    date_idx = None
                    for cand in ('date','added_date','timestamp'):
                        if cand in cols:
                            date_idx = cols.index(cand); break
                    rows = scur.execute(f"SELECT * FROM '{t}'").fetchall()
                    for row in rows:
                        title = row[title_idx] if len(row) > title_idx else None
                        date = row[date_idx] if (date_idx is not None and len(row) > date_idx) else None
                        title_s = _sanitize_value(title)
                        if not title_s:
                            continue
                        if media_kind == 'movie':
                            mid = upsert_movie(cur, title_s)
                            if not self.dry_run:
                                cur.execute(
                                    "INSERT INTO user_watchlist (user_id, media_type, media_id, added_date) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                                    (user_id, 'movie', mid, _sanitize_value(date)),
                                )
                                cur.execute("INSERT INTO user_media (user_id, media_type, media_id) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (user_id, 'movie', mid))
                        else:
                            sid = upsert_series(cur, title_s)
                            if not self.dry_run:
                                cur.execute(
                                    "INSERT INTO user_watchlist (user_id, media_type, media_id, added_date) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                                    (user_id, 'series', sid, _sanitize_value(date)),
                                )
                                cur.execute("INSERT INTO user_media (user_id, media_type, media_id) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (user_id, 'series', sid))
                        migrated += 1

            if not self.dry_run:
                pg.commit()
        finally:
            pg.close(); sconn.close()
        self.log(f'  migrated media rows: {migrated}')
        return migrated


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--dry-run', action='store_true', help='Show planned operations without writing to Postgres')
    p.add_argument('--modules', type=str, default='', help='Comma-separated list of modules to run (serverstats,leveling,games,fintech,media,notifications)')
    return p.parse_args()


def main():
    args = parse_args()
    modules = [m.strip() for m in args.modules.split(',') if m.strip()] if args.modules else []
    migrator = Migrator(dry_run=args.dry_run, verbose=True)

    sequence = [
        #('serverstats', migrator.migrate_serverstats),
        #('leveling', migrator.migrate_leveling),
        #('games', migrator.migrate_games),
        #('fintech', migrator.migrate_fintech),
        ('media', migrator.migrate_media),
    ]

    print('🚀 Starting migration v2', '(DRY RUN)' if args.dry_run else '')
    for name, fn in sequence:
        if modules and name not in modules:
            continue
        print(f'-- {name.upper()} --')
        try:
            n = fn()
            print(f'  -> {n} rows handled for {name}')
        except Exception as e:
            print(f'  ERROR in {name}:', e)
            if not args.dry_run:
                raise

    print('\n✅ Migration v2 finished.')


if __name__ == '__main__':
    main()
