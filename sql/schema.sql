PRAGMA foreign_keys = ON;

CREATE TABLE source_runs (
    source_run_id INTEGER PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    snapshot TEXT NOT NULL,
    downloaded_at_utc TEXT NOT NULL,
    source_metadata_json TEXT NOT NULL
);

CREATE TABLE games (
    app_id INTEGER PRIMARY KEY CHECK (typeof(app_id) = 'integer' AND app_id > 0),
    name TEXT NOT NULL,
    metadata_available INTEGER NOT NULL CHECK (metadata_available IN (0, 1)),
    review_group TEXT NOT NULL,
    eligible INTEGER NOT NULL CHECK (eligible IN (0, 1)),
    eligibility_reason TEXT NOT NULL,
    metadata_source_id INTEGER REFERENCES source_runs(source_run_id),
    CHECK (eligible = 0 OR (metadata_available = 1 AND review_group = 'Game-related labels only'))
);

CREATE TABLE game_genres (
    app_id INTEGER NOT NULL REFERENCES games(app_id),
    genre TEXT NOT NULL CHECK (length(trim(genre)) > 0),
    PRIMARY KEY (app_id, genre)
);

CREATE TABLE monthly_players (
    app_id INTEGER NOT NULL REFERENCES games(app_id),
    month TEXT NOT NULL CHECK (
        length(month) = 10 AND
        month GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-01' AND
        substr(month, 6, 2) BETWEEN '01' AND '12'
    ),
    avg_players REAL NOT NULL CHECK (avg_players >= 0 AND avg_players < 1e308),
    source_run_id INTEGER NOT NULL DEFAULT 2 REFERENCES source_runs(source_run_id),
    PRIMARY KEY (app_id, month)
);

CREATE INDEX monthly_players_month ON monthly_players(month);

CREATE TABLE analysis_categories (
    genre TEXT PRIMARY KEY
);

CREATE VIEW app_coverage AS
SELECT p.app_id, MIN(p.month) AS first_month, MAX(p.month) AS last_month,
       COUNT(*) AS observed_months
FROM monthly_players AS p
GROUP BY p.app_id;
