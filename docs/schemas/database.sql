-- MarketMind relational data model (SQLite dialect; portable to PostgreSQL with minor type changes).
--
-- Part A, analytical store: the seven research datasets as a star schema with natural keys, so the CSV
--         values load as they are (brand names, SKU ids, categories, channels, regions).
-- Part B, operational store: saved runs and what the agents produced (results, findings, recommendations,
--         QA checks, trace events), for audit trails and cross-run reporting.
--
-- Load it with:  python scripts/export_sqlite.py      (applies this file, then inserts clean data and runs)
-- Foreign keys are enforced when the connection runs PRAGMA foreign_keys = ON.

PRAGMA foreign_keys = ON;

-- =====================================================================================================
-- Part A - analytical store
-- =====================================================================================================

CREATE TABLE IF NOT EXISTS dim_brand (
    brand            TEXT PRIMARY KEY,                      -- e.g. 'Kirana Beauty'; survey adds 'Other local brand'
    is_client        INTEGER NOT NULL DEFAULT 0 CHECK (is_client IN (0, 1))
);

CREATE TABLE IF NOT EXISTS dim_category (
    category         TEXT PRIMARY KEY CHECK (category IN ('Facial Wash', 'Toner', 'Serum', 'Moisturizer', 'Sunscreen'))
);

CREATE TABLE IF NOT EXISTS dim_channel (
    channel          TEXT PRIMARY KEY,                      -- Shopee, Tokopedia, TikTok Shop, Lazada, Offline Retail
    is_online        INTEGER NOT NULL CHECK (is_online IN (0, 1))
);

CREATE TABLE IF NOT EXISTS dim_region (
    region           TEXT PRIMARY KEY                       -- seven Indonesian regions
);

CREATE TABLE IF NOT EXISTS dim_product (
    sku_id               TEXT PRIMARY KEY,                  -- 'SKU-001'
    brand                TEXT NOT NULL REFERENCES dim_brand (brand),
    product_name         TEXT NOT NULL,
    category             TEXT NOT NULL REFERENCES dim_category (category),
    key_ingredient       TEXT,
    size_ml              REAL CHECK (size_ml > 0),
    price_idr            INTEGER CHECK (price_idr > 0),
    launch_month         TEXT,                              -- 'YYYY-MM'
    fragrance_free       INTEGER CHECK (fragrance_free IN (0, 1)),
    spf                  INTEGER,
    price_per_ml_idr     REAL,
    halal_certified      INTEGER CHECK (halal_certified IN (0, 1)),
    bpom_registered      INTEGER CHECK (bpom_registered IN (0, 1)),
    rating_avg           REAL CHECK (rating_avg IS NULL OR rating_avg BETWEEN 1 AND 5),
    review_count         INTEGER CHECK (review_count >= 0),
    units_sold_estimate  INTEGER CHECK (units_sold_estimate >= 0)
);

-- Grain: month x brand x category x channel x region (after the Data Quality agent's cleaning).
CREATE TABLE IF NOT EXISTS fact_sales_monthly (
    month                  TEXT    NOT NULL,                -- 'YYYY-MM-01'
    brand                  TEXT    NOT NULL REFERENCES dim_brand (brand),
    category               TEXT    NOT NULL REFERENCES dim_category (category),
    channel                TEXT    NOT NULL REFERENCES dim_channel (channel),
    region                 TEXT    NOT NULL REFERENCES dim_region (region),
    units                  INTEGER NOT NULL CHECK (units >= 0),
    revenue_idr            INTEGER NOT NULL CHECK (revenue_idr >= 0),
    list_price_idr         INTEGER CHECK (list_price_idr > 0),
    avg_selling_price_idr  INTEGER CHECK (avg_selling_price_idr > 0),
    discount_pct           REAL    CHECK (discount_pct BETWEEN 0 AND 1),
    promo_flag             INTEGER CHECK (promo_flag IN (0, 1)),
    stockout_days          INTEGER CHECK (stockout_days BETWEEN 0 AND 31),
    PRIMARY KEY (month, brand, category, channel, region)
);

CREATE TABLE IF NOT EXISTS fact_review (
    review_id           TEXT PRIMARY KEY,                   -- 'R000001'
    review_date         TEXT NOT NULL,                      -- 'YYYY-MM-DD'
    brand               TEXT NOT NULL REFERENCES dim_brand (brand),
    sku_id              TEXT NOT NULL REFERENCES dim_product (sku_id),
    product_name        TEXT,
    category            TEXT NOT NULL REFERENCES dim_category (category),
    channel             TEXT NOT NULL REFERENCES dim_channel (channel),
    region              TEXT REFERENCES dim_region (region),
    rating              INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review_text         TEXT,                               -- NULL = rating-only review
    helpful_votes       INTEGER CHECK (helpful_votes >= 0),
    verified_purchase   INTEGER CHECK (verified_purchase IN (0, 1)),
    reviewer_id         TEXT,
    reviewer_skin_type  TEXT CHECK (reviewer_skin_type IS NULL OR reviewer_skin_type IN ('oily', 'dry', 'combination', 'sensitive', 'normal'))
);
CREATE INDEX IF NOT EXISTS ix_review_brand_date ON fact_review (brand, review_date);

CREATE TABLE IF NOT EXISTS fact_social_post (
    post_id           TEXT PRIMARY KEY,                     -- 'P000001'
    post_date         TEXT NOT NULL,
    platform          TEXT NOT NULL CHECK (platform IN ('TikTok', 'Instagram', 'X', 'YouTube')),
    brand_mentioned   TEXT REFERENCES dim_brand (brand),    -- NULL for generic topic posts
    topics            TEXT NOT NULL,                        -- semicolon-separated
    post_text         TEXT NOT NULL,
    author_followers  INTEGER CHECK (author_followers >= 0),
    influencer_tier   TEXT CHECK (influencer_tier IN ('nano', 'micro', 'macro', 'mega')),
    views             INTEGER CHECK (views >= 0),
    likes             INTEGER CHECK (likes >= 0),
    comments          INTEGER CHECK (comments >= 0),
    shares            INTEGER CHECK (shares >= 0)
);
CREATE INDEX IF NOT EXISTS ix_social_brand_date ON fact_social_post (brand_mentioned, post_date);

CREATE TABLE IF NOT EXISTS social_label (
    post_id      TEXT PRIMARY KEY REFERENCES fact_social_post (post_id),
    human_label  TEXT NOT NULL CHECK (human_label IN ('negative', 'neutral', 'positive'))
);

CREATE TABLE IF NOT EXISTS fact_survey_response (
    respondent_id                 TEXT PRIMARY KEY,         -- 'S00001'
    survey_date                   TEXT NOT NULL,
    age                           INTEGER CHECK (age BETWEEN 15 AND 75),
    gender                        TEXT CHECK (gender IN ('Female', 'Male')),
    region                        TEXT REFERENCES dim_region (region),
    city_tier                     TEXT CHECK (city_tier IN ('Tier 1', 'Tier 2', 'Tier 3')),
    occupation                    TEXT,
    income_bracket                TEXT,                     -- NULL = prefer not to say
    monthly_income_idr            REAL,
    monthly_skincare_spend_idr    INTEGER CHECK (monthly_skincare_spend_idr >= 0),
    routine_steps                 INTEGER CHECK (routine_steps BETWEEN 1 AND 7),
    purchase_freq_per_month       REAL,
    skin_type                     TEXT,
    primary_concern               TEXT,
    preferred_channel             TEXT REFERENCES dim_channel (channel),
    main_brand                    TEXT REFERENCES dim_brand (brand),
    aware_kirana                  INTEGER CHECK (aware_kirana IN (0, 1)),
    aware_lumiere                 INTEGER CHECK (aware_lumiere IN (0, 1)),
    aware_dewiskin                INTEGER CHECK (aware_dewiskin IN (0, 1)),
    aware_glownesia               INTEGER CHECK (aware_glownesia IN (0, 1)),
    aware_aurelia                 INTEGER CHECK (aware_aurelia IN (0, 1)),
    aware_purabotanica            INTEGER CHECK (aware_purabotanica IN (0, 1)),
    nps_main_brand                INTEGER CHECK (nps_main_brand BETWEEN 0 AND 10),
    satisfaction_main_brand       INTEGER CHECK (satisfaction_main_brand BETWEEN 1 AND 5),
    social_media_hours_per_day    REAL,
    primary_platform              TEXT,
    follows_skincare_influencers  INTEGER CHECK (follows_skincare_influencers IN (0, 1)),
    influencer_trust              INTEGER CHECK (influencer_trust BETWEEN 1 AND 5),
    imp_price                     INTEGER CHECK (imp_price BETWEEN 1 AND 5),
    imp_halal                     INTEGER CHECK (imp_halal BETWEEN 1 AND 5),
    imp_ingredients               INTEGER CHECK (imp_ingredients BETWEEN 1 AND 5),
    imp_brand_reputation          INTEGER CHECK (imp_brand_reputation BETWEEN 1 AND 5),
    imp_packaging                 INTEGER CHECK (imp_packaging BETWEEN 1 AND 5),
    imp_reviews_influencers       INTEGER CHECK (imp_reviews_influencers BETWEEN 1 AND 5),
    imp_local_brand               INTEGER CHECK (imp_local_brand BETWEEN 1 AND 5),
    imp_sustainability            INTEGER CHECK (imp_sustainability BETWEEN 1 AND 5),
    imp_fragrance_free            INTEGER CHECK (imp_fragrance_free BETWEEN 1 AND 5),
    imp_fast_results              INTEGER CHECK (imp_fast_results BETWEEN 1 AND 5),
    attention_check               INTEGER,
    concept_purchase_intent       INTEGER CHECK (concept_purchase_intent BETWEEN 1 AND 5),
    vw_too_cheap_idr              INTEGER,
    vw_cheap_idr                  INTEGER,
    vw_expensive_idr              INTEGER,
    vw_too_expensive_idr          INTEGER,
    completion_time_sec           INTEGER
);

CREATE TABLE IF NOT EXISTS fact_market_size (
    year                   INTEGER NOT NULL,
    category               TEXT    NOT NULL REFERENCES dim_category (category),
    market_value_idr_bn    REAL    NOT NULL CHECK (market_value_idr_bn > 0),
    local_brand_share_pct  REAL CHECK (local_brand_share_pct BETWEEN 0 AND 100),
    online_share_pct       REAL CHECK (online_share_pct BETWEEN 0 AND 100),
    status                 TEXT CHECK (status IN ('actual', 'estimate')),
    source                 TEXT,
    yoy_growth_pct         REAL,
    PRIMARY KEY (year, category)
);

-- Monthly revenue and value share by brand (what the Competitive Intelligence agent computes in pandas).
CREATE VIEW IF NOT EXISTS v_brand_share_monthly AS
SELECT s.month,
       s.brand,
       SUM(s.revenue_idr) AS revenue_idr,
       1.0 * SUM(s.revenue_idr) / (SELECT SUM(t.revenue_idr) FROM fact_sales_monthly t WHERE t.month = s.month) AS value_share
FROM fact_sales_monthly s
GROUP BY s.month, s.brand;

-- =====================================================================================================
-- Part B - operational store (one row set per saved run)
-- =====================================================================================================

CREATE TABLE IF NOT EXISTS run (
    run_id        TEXT PRIMARY KEY,                         -- 'YYYYMMDD-HHMMSS'
    started       TEXT,
    status        TEXT NOT NULL CHECK (status IN ('completed', 'unverified', 'failed', 'rejected')),
    seconds       REAL,
    brief         TEXT,
    client        TEXT REFERENCES dim_brand (brand),
    llm_provider  TEXT,
    llm_model     TEXT,
    qa_score      REAL,
    qa_passed     INTEGER CHECK (qa_passed IN (0, 1)),
    qa_revisions  INTEGER
);

CREATE TABLE IF NOT EXISTS agent_result (
    run_id      TEXT NOT NULL REFERENCES run (run_id),
    task_id     TEXT NOT NULL,                              -- plan, collect, quality, market, ..., qa, report_rev1
    agent       TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('completed', 'failed', 'skipped')),
    summary     TEXT,
    seconds     REAL,
    findings    INTEGER,
    tool_calls  INTEGER,
    llm_calls   INTEGER,
    error       TEXT,
    PRIMARY KEY (run_id, task_id)
);

CREATE TABLE IF NOT EXISTS finding (
    run_id         TEXT NOT NULL REFERENCES run (run_id),
    finding_id     TEXT NOT NULL,                           -- 'CMP-02'
    agent          TEXT NOT NULL,
    area           TEXT NOT NULL CHECK (area IN ('data', 'market', 'competition', 'consumer', 'segmentation', 'pricing', 'forecast', 'strategy')),
    title          TEXT NOT NULL,
    statement      TEXT NOT NULL,
    metrics_json   TEXT,
    evidence_json  TEXT,
    impact         INTEGER CHECK (impact BETWEEN 1 AND 5),
    confidence     REAL CHECK (confidence BETWEEN 0 AND 1),
    swot           TEXT CHECK (swot IS NULL OR swot IN ('S', 'W', 'O', 'T')),
    tags_json      TEXT,
    priority       REAL,
    PRIMARY KEY (run_id, finding_id)
);

CREATE TABLE IF NOT EXISTS recommendation (
    run_id      TEXT NOT NULL REFERENCES run (run_id),
    rec_id      TEXT NOT NULL,                              -- 'R1'
    title       TEXT NOT NULL,
    action      TEXT,
    rationale   TEXT,
    kpi         TEXT,
    timeline    TEXT,
    horizon     TEXT CHECK (horizon IN ('Quick win', 'Core move', 'Strategic bet')),
    owner       TEXT,
    effort      TEXT CHECK (effort IN ('Low', 'Medium', 'High')),
    value_idr   REAL,
    impact      INTEGER,
    confidence  REAL,
    priority    REAL,
    PRIMARY KEY (run_id, rec_id)
);

CREATE TABLE IF NOT EXISTS recommendation_evidence (
    run_id      TEXT NOT NULL,
    rec_id      TEXT NOT NULL,
    finding_id  TEXT NOT NULL,
    PRIMARY KEY (run_id, rec_id, finding_id),
    FOREIGN KEY (run_id, rec_id) REFERENCES recommendation (run_id, rec_id),
    FOREIGN KEY (run_id, finding_id) REFERENCES finding (run_id, finding_id)
);

CREATE TABLE IF NOT EXISTS qa_check (
    run_id      TEXT NOT NULL REFERENCES run (run_id),
    revision    INTEGER NOT NULL,
    check_name  TEXT NOT NULL CHECK (check_name IN ('structure', 'coverage', 'grounding', 'citations', 'recommendations', 'disclosure')),
    score       REAL CHECK (score BETWEEN 0 AND 1),
    PRIMARY KEY (run_id, revision, check_name)
);

CREATE TABLE IF NOT EXISTS trace_event (
    run_id     TEXT NOT NULL REFERENCES run (run_id),
    seq        INTEGER NOT NULL,
    ts         REAL,
    agent      TEXT NOT NULL,
    kind       TEXT NOT NULL CHECK (kind IN ('status', 'thought', 'action', 'observation', 'finding', 'message', 'llm', 'warning', 'error', 'approval')),
    message    TEXT,
    data_json  TEXT,
    PRIMARY KEY (run_id, seq)
);
CREATE INDEX IF NOT EXISTS ix_trace_agent ON trace_event (run_id, agent);
