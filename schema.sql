CREATE TABLE IF NOT EXISTS feeds (
    url TEXT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    shortname VARCHAR(3) NOT NULL CHECK (shortname ~ '^[A-Z]{2,3}$'),
    ignorelinks TEXT,
    country VARCHAR(100) NOT NULL CHECK (country ~ '^[A-Z]')
);

CREATE TABLE IF NOT EXISTS secrets (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    feed_url TEXT NOT NULL,
    feed_name TEXT NOT NULL,
    feed_short_name TEXT NOT NULL,
    feed_country TEXT NOT NULL,
    feed_ignore_links TEXT NOT NULL DEFAULT '',
    article_title TEXT NOT NULL,
    formatted_title TEXT NOT NULL,
    article_link TEXT NOT NULL,
    article_published_at TIMESTAMPTZ,
    md5_hash TEXT NOT NULL,
    user_agent TEXT NOT NULL,
    referer TEXT NOT NULL,
    hn_outcome TEXT NOT NULL,
    hn_http_status INTEGER,
    hn_response_body TEXT,
    hn_response_headers JSONB,
    hn_submit_url TEXT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS posts_md5_hash_idx ON posts (md5_hash);
CREATE INDEX IF NOT EXISTS posts_created_at_idx ON posts (created_at);
CREATE INDEX IF NOT EXISTS posts_article_link_idx ON posts (article_link);

INSERT INTO secrets (key, value) VALUES
    ('UPSTASH_REDIS_REST_URL', 'https://your-db.upstash.io'),
    ('UPSTASH_REDIS_REST_TOKEN', 'your-upstash-rest-token'),
    ('HN_USERNAME', 'your-hn-username'),
    ('HN_PASSWORD', 'your-hn-password'),
    ('FEEDS_QUERY', 'SELECT url, name, shortname, ignorelinks, country FROM feeds'),
    ('SCAN_INTERVAL_SECONDS', '30'),
    ('FEED_REFRESH_SECONDS', '300'),
    ('MAX_ARTICLE_AGE_SECONDS', '86400'),
    ('SEEN_TTL_SECONDS', '172800'),
    ('REQUEST_TIMEOUT_SECONDS', '30')
ON CONFLICT (key) DO NOTHING;
