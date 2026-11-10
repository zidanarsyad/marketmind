# Data dictionary

All files live in `data/raw/` and are produced by `scripts/generate_data.py` (seed 2026). Brands, products and
respondents are fictional. Money is in Indonesian rupiah (IDR). To run MarketMind on your own data, provide files
with these columns (extra columns are ignored).

Machine-readable contracts for the cleaned version of each file are in [`schemas/datasets/`](schemas/datasets/), and the
relational model (star schema and entity-relationship diagram) is in [SCHEMAS.md](SCHEMAS.md#5-relational-model). Real public
datasets that can stand in for, validate or calibrate each file are listed in [DATA_SOURCES.md](DATA_SOURCES.md).

## market_sales_panel.csv - monthly sell-out panel (~48k rows)

| Column | Type | Description |
|---|---|---|
| month | date (YYYY-MM-01) | Calendar month, Jan 2023 - Oct 2026 |
| brand | text | Kirana Beauty (client), Lumière Lab, DewiSkin, GlowNesia, Aurelia Derma, Purabotanica |
| category | text | Facial Wash, Toner, Serum, Moisturizer, Sunscreen |
| channel | text | Shopee, Tokopedia, TikTok Shop, Lazada, Offline Retail (some raw label variants are deliberate defects) |
| region | text | DKI Jakarta & Banten, Jawa Barat, Jawa Tengah & DIY, Jawa Timur, Sumatera, Kalimantan & Sulawesi, Bali & Indonesia Timur |
| units | int | Units sold (a few negative / x12 outlier rows are deliberate defects) |
| revenue_idr | int | Net revenue = units x avg_selling_price_idr |
| list_price_idr | int | Recommended retail price (yearly indexation; client +12% from Jul 2025) |
| avg_selling_price_idr | int | Effective price after discount |
| discount_pct | float | Average promotional discount (about 1% missing on purpose) |
| promo_flag | bool | Discount >= 15% |
| stockout_days | int | Days out of stock in the month |

## product_reviews.csv - marketplace reviews (~20k rows)

| Column | Type | Description |
|---|---|---|
| review_id | text | Unique review id (about 1% duplicated rows on purpose) |
| review_date | date | Date of the review |
| brand, sku_id, product_name, category | text | Reviewed product |
| channel | text | Online channel where it was bought |
| region | text | Buyer region |
| rating | int 1-5 | Star rating (J-shaped distribution, used as a weak sentiment label) |
| review_text | text | Indonesian review with slang, emojis, typos, code-mixing; empty for rating-only reviews |
| helpful_votes | int | "Helpful" votes |
| verified_purchase | bool | Verified buyer |
| reviewer_id | text | Reviewer id |
| reviewer_skin_type | text | oily / dry / combination / sensitive / normal (about 25% missing) |

## social_mentions.csv - social listening (~11k rows, no sentiment labels)

| Column | Type | Description |
|---|---|---|
| post_id | text | Unique post id (reposts duplicated on purpose) |
| post_date | date | Date posted |
| platform | text | TikTok, Instagram, X, YouTube |
| brand_mentioned | text | Brand mentioned, empty for generic topic posts |
| topics | text | Semicolon-separated topics (niacinamide, ceramide, skin barrier, peptide, sunscreen, refill, dupe, ...) |
| post_text | text | Post text with hashtags |
| author_followers | int | Author follower count |
| influencer_tier | text | nano / micro / macro / mega |
| views, likes, comments, shares | int | Engagement |

## social_validation_labels.csv - hand-labelled validation sample (400 rows)

| Column | Type | Description |
|---|---|---|
| post_id | text | Post id in social_mentions.csv |
| human_label | text | negative / neutral / positive (analyst annotation, used to validate model transfer) |

## consumer_survey.csv - usage & attitude survey (2,400 respondents)

| Column | Type | Description |
|---|---|---|
| respondent_id, survey_date | text, date | Respondent id, fieldwork Aug-Sep 2026 |
| age, gender, region, city_tier, occupation | mixed | Demographics (a few invalid ages on purpose) |
| income_bracket, monthly_income_idr | text, float | Income bracket and midpoint (about 4% "prefer not to say") |
| monthly_skincare_spend_idr | int | Monthly skincare spend |
| routine_steps, purchase_freq_per_month | int, float | Routine size and purchase frequency |
| skin_type, primary_concern | text | Skin type and main concern |
| preferred_channel, main_brand | text | Preferred channel and most-used brand |
| aware_<brand> | 0/1 | Aided brand awareness for each brand |
| nps_main_brand, satisfaction_main_brand | int | 0-10 recommendation score, 1-5 satisfaction |
| social_media_hours_per_day, primary_platform | float, text | Media habits |
| follows_skincare_influencers, influencer_trust | bool, int 1-5 | Influencer affinity |
| imp_price ... imp_fast_results | int 1-5 | Importance of 10 purchase drivers (price, halal, ingredients, brand reputation, packaging, reviews & influencers, local brand, sustainability, fragrance-free, fast results) |
| attention_check | int | Instructed-response item; the correct answer is 4 |
| concept_purchase_intent | int 1-5 | Intent to buy the fragrance-free barrier-repair moisturizer concept |
| vw_too_cheap_idr, vw_cheap_idr, vw_expensive_idr, vw_too_expensive_idr | int | Van Westendorp price questions |
| completion_time_sec | int | Interview length (speeders are a deliberate defect) |

## product_catalog.csv - SKU catalogue (49 rows)

sku_id, brand, product_name, category, key_ingredient, size_ml, price_idr, launch_month, fragrance_free, spf,
price_per_ml_idr, halal_certified, bpom_registered, rating_avg (empty for very new SKUs), review_count, units_sold_estimate.

## market_size.csv - market size (40 rows)

year (2019-2026), category, market_value_idr_bn, local_brand_share_pct, online_share_pct, status (actual / estimate),
source, yoy_growth_pct.

## Ground truth (for evaluation only - never read by the agents)

`data/ground_truth.json` records planted elasticities, events, segments, trends and injected data defects;
`data/ground_truth/` holds hidden labels: true review aspects, true social sentiment and true survey segments.
