CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    discord_id VARCHAR(255) NOT NULL UNIQUE,
    username VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS media (
    id SERIAL PRIMARY KEY,
    tmdb_id INTEGER NOT NULL UNIQUE,

    title VARCHAR(255) NOT NULL,
    overview TEXT,

    media_type VARCHAR(10) NOT NULL
        CHECK (media_type IN ('movie', 'tv')),

    genres JSONB,

    poster_url VARCHAR(255),
    status VARCHAR(50),
    homepage VARCHAR(255),
    release_date DATE,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS series_details (
    media_id INTEGER PRIMARY KEY
        REFERENCES media(id) ON DELETE CASCADE,

    last_air_date DATE,
    next_episode_date DATE,
    next_episode_number INTEGER,
    next_season_number INTEGER,

    seasons JSONB,
    last_episode JSONB
);

CREATE TABLE IF NOT EXISTS movie_details (
    media_id INTEGER PRIMARY KEY
        REFERENCES media(id) ON DELETE CASCADE,

    collection JSONB
);


CREATE TABLE IF NOT EXISTS servers (
    id SERIAL PRIMARY KEY,
    server_id VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS user_media (
    user_id INTEGER NOT NULL
        REFERENCES users(id) ON DELETE CASCADE,

    media_id INTEGER NOT NULL
        REFERENCES media(id) ON DELETE CASCADE,

    media_type VARCHAR(10) NOT NULL
        CHECK (media_type IN ('movie', 'tv')),

    status VARCHAR(20) NOT NULL
        CHECK (status IN ('watching', 'watched', 'paused', 'dropped', 'planned')),

    progress JSONB,
    poster VARCHAR(255),
    last_updated TIMESTAMP DEFAULT NOW(),

    PRIMARY KEY (user_id, media_id)
);
