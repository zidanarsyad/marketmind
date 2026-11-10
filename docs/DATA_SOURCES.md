# Real data sources for MarketMind

MarketMind runs on simulated data so that every result can be scored against a planted truth ([EVALUATION.md](EVALUATION.md)). This guide lists **real, public datasets and statistics** that support the system in three ways:

1. **Replace or augment** a simulated file with real records.
2. **Validate** a model on real data: the sentiment model on real Indonesian reviews, the aspect lexicon on human-labelled aspects, and the segmentation code on real survey answers.
3. **Calibrate** the simulator against real-world numbers: market size, channel shares, consumer habits.

Every source below was found on 4 November 2026 by opening its page and reading what it states about size, fields and licence; where a page leaves something out, the entry says "not stated", "unknown" or "unclear". Entries and figures marked ✓ were checked a second time against the source page. Two of them, the Shopee/Tokopedia beauty reviews and IndoNLU SmSA, have been downloaded into `data/external/` for the validation described in section 9; the others have not. Licences differ widely, so read section 8 before using any of them.

---

## 1. At a glance

| MarketMind data (agent) | Best real sources | What they add | Gap that remains |
|---|---|---|---|
| `product_reviews.csv` (Consumer Insight, deep learning) | Shopee/Tokopedia beauty reviews (76k, Apache-2.0); Female Daily skincare reviews (8.6k, with skin type); Tokopedia 2025 (about 1M reviews, CC BY-NC) | Real marketplace text with star ratings, to train and validate the sentiment models; the Tokopedia set also shows the natural star mix | No source has every column (brand, channel, region, date) at once |
| Human labels for the models | IndoNLU SmSA (12.8k, 3 classes); PRDECT-ID (5.4k, human sentiment and emotion); IndoNLU CASA and HoASA (aspects) | Honest benchmarks with human labels, and a check of star-derived labels against human ones | No beauty-specific aspect benchmark |
| `social_mentions.csv`, `social_validation_labels.csv` | Natasha Skincare tweets (19k, emotion labels); UGM Indonesian tweets (10.8k, 3 classes); Azarine sunscreen comments (400, TikTok and X) | Real social text for the review-to-social transfer check | No public, human-labelled TikTok or Instagram beauty sentiment set |
| `product_catalog.csv` | Sociolla catalogue (7.5k products, IDR prices); Female Daily product list (7.4k, ratings); Sephora (ingredients, CC BY 4.0); BPOM registrations | Real brands, categories, prices, ratings and ingredient claims | Halal, BPOM number and units sold are rarely together |
| `market_sales_panel.csv` | Tokopedia 2025 sold counts and review dates; Compas published aggregates | Proxies for units, discounts, channel mix and Ramadan uplift | No open sell-out panel by brand, channel and region exists |
| `market_size.csv` | Statista, MarketLine, GlobalData and Euromonitor headlines; Compas e-commerce totals; UN Comtrade HS 3304 | Citable market totals, growth and company shares | Definitions differ between sources; full reports are paid |
| `consumer_survey.csv` | Small Indonesian survey deposits (n = 189-440, mostly CC BY 4.0); ZAP, Populix and Jakpat reports | Real answers to test segmentation code; population figures for calibration | No public skincare microdata with spend, channel, brand and Van Westendorp questions |
| Calendar and macro | Python `holidays` (MIT); BPS WebAPI; Google Trends | Official Eid dates, regional statistics, search interest | Google Trends has no stable official API yet |

## 2. Review and social text

### Reviews with star ratings

| Dataset | Size and coverage | Labels | Licence | Access | Use in MarketMind |
|---|---|---|---|---|---|
| **Indonesian beauty product reviews** ✓ <br>[huggingface.co/datasets/sekarmulyani/ulasan-beauty-products](https://huggingface.co/datasets/sekarmulyani/ulasan-beauty-products) | 76,256 reviews of women's beauty products from 38 official stores on Shopee and Tokopedia; train 57,192, validation 15,251, test 3,813; 5.2 MB of parquet. Collection period not stated. | 1-5 stars (one column per star) | Apache-2.0 | `load_dataset("sekarmulyani/ulasan-beauty-products")` | **The best open corpus for the sentiment agent:** real marketplace beauty text whose stars MarketMind's rule (1-2 negative, 3 neutral, 4-5 positive) turns straight into labels. Text and stars only (no brand, date or product). The stars are balanced (about 20% each), so the set does not show the natural star mix, and emojis are written as names such as `:thumbs_up:`. |
| **Female Daily SkinCare Review** ✓ <br>[kaggle.com/datasets/hafidahmusthaanah/skincare-review](https://www.kaggle.com/datasets/hafidahmusthaanah/skincare-review) | 8,646 reviews of 802 skincare products by 5,281 reviewers, scraped from femaledaily.com on 18 Sep 2020; a product file covers 861 products and 215 brands | 1-5 stars, a recommend flag, skin condition and age band ("Oily, 19 - 24") | Unknown | Kaggle download (account needed) | A validation set that includes **skin type**, for the aspect lexicon and the skin-type fit analysis. The product file adds brand, category and price. |
| **Tokopedia Product and Review Dataset** ✓ <br>[kaggle.com/datasets/musabiam/tokopedia-product-and-review-dataset](https://www.kaggle.com/datasets/musabiam/tokopedia-product-and-review-dataset) | 5,553 products with about 1M reviews in 24 categories, including Kecantikan (beauty) and Perawatan Tubuh (body care); scraped in 2025; 1.06 GB | 1-5 stars; review likes; bad-rating reasons | CC BY-NC 4.0; "for research and educational purposes only" | Kaggle download; reviews are stored as lists per product and must be exploded | The only large, recent source from a real sales channel. It maps to review_id, review_date, product_name, category, channel, rating, review_text and helpful_votes, and `bad_rating_reason` helps the complaint-topic model. Beauty is one of 24 categories. |
| **PRDECT-ID** ✓ <br>[data.mendeley.com/datasets/574v66hf2v/1](https://data.mendeley.com/datasets/574v66hf2v/1) (mirror: `ZakyF/PRDECT-ID`) | 5,400 Tokopedia reviews, 200 from each of 29 categories (including Beauty, Body Care and Health) | Human-annotated sentiment (positive or negative) and 5 emotions, plus stars | CC BY 4.0 | Direct download, or `load_dataset("ZakyF/PRDECT-ID")` | Measures how well **star-derived labels agree with human labels**, the main assumption behind MarketMind's weak supervision. Two classes only; the star mix is not natural. |
| Lazada Indonesian Reviews <br>[kaggle.com/datasets/grikomsn/lazada-indonesian-reviews](https://www.kaggle.com/datasets/grikomsn/lazada-indonesian-reviews) | 203,787 reviews, October 2019, electronics only | 1-5 stars | CC0: Public Domain | Kaggle download | Extra Indonesian text for pre-training only; no beauty products. |

### Human-labelled sentiment and aspect benchmarks

| Dataset | Size | Labels | Licence | Use in MarketMind |
|---|---|---|---|---|
| **IndoNLU SmSA** ✓ <br>[huggingface.co/datasets/indonlp/indonlu](https://huggingface.co/datasets/indonlp/indonlu) (config `smsa`) | 11,000 / 1,260 / 500 comments and reviews from several platforms | positive, neutral, negative, labelled by linguists | "MIT" on the Hugging Face card; the GitHub repository's LICENSE file is Apache-2.0 | The standard 3-class benchmark to report the sentiment models against. The Hugging Face version needs a loading script; the [GitHub TSV files](https://github.com/IndoNLP/indonlu/tree/master/dataset/smsa_doc-sentiment-prosa) (2.5 MB) download directly. |
| **IndoNLU CASA and HoASA** ✓ (same repository) | CASA 810/90/180 car reviews, 6 aspects; HoASA 2,283/285/286 hotel reviews, 10 aspects | Polarity per aspect | As SmSA | The only human-labelled Indonesian aspect benchmarks. They test the aspect lexicon where aspects overlap: price, smell or scent, and service (a stand-in for delivery). |
| NusaX-senti (Indonesian part) | 1,000 rows | 3 classes | CC BY-SA 4.0 | A stratified sample of SmSA, so it is not an independent test. |

### Social media text

| Dataset | Size and coverage | Labels | Licence | Use in MarketMind |
|---|---|---|---|---|
| **Natasha Skincare tweets** ✓ <br>[huggingface.co/datasets/SEACrowd/sentiment_nathasa_review](https://huggingface.co/datasets/SEACrowd/sentiment_nathasa_review) | 19,253 tweets mentioning an Indonesian skincare clinic brand, about 2018 | 7 emotions: no-emotion 17,736, joy 804, sad 287, disgust 167, anger 154, fear 61, surprise 43 | Unknown | The only labelled social text about a local skincare brand. Map joy to positive; sad, anger, disgust and fear to negative; no-emotion to neutral; and use it for the transfer check. Loading needs `trust_remote_code=True`. Very imbalanced, and the labelling method is not described. |
| UGM Indonesian Sentiment Twitter Dataset <br>[github.com/ridife/dataset-idsa](https://github.com/ridife/dataset-idsa) | 10,806 labelled tweets (plus 454,559 unlabelled), up to 2019 | positive, neutral, negative | Unclear: CC BY-NC on the author's UGM page, none on GitHub | A larger 3-class social set for the transfer check; not about beauty. |
| Azarine sunscreen comments <br>[data.mendeley.com/datasets/fk73wgbmn7/1](https://data.mendeley.com/datasets/fk73wgbmn7/1) | 400 Indonesian comments (200 TikTok, 200 X) about a local sunscreen brand, January 2024 to June 2025 | Thematic codes (product attributes such as packaging and SPF, performance, social proof); no sentiment labels | CC BY 4.0 | A small sample from MarketMind's own period and category, to test the aspect lexicon on social text. Adding sentiment labels would make a real `social_validation_labels.csv`. |

**Avoid:** `wiwikastriani09/ulasan-kosmeti-emina` on Kaggle looks synthetic (exactly uniform star counts, templated texts, ratings that contradict the text). Merged collections with no card or licence, such as `carant-ai/indonesian_sentiment_dataset`, cannot be traced to their sources.

## 3. Product catalogues and sales proxies

| Source | Size and coverage | Key fields | Licence or terms | Use in MarketMind |
|---|---|---|---|---|
| **Sociolla: All Brands Products Catalog** ✓ <br>[kaggle.com/datasets/ibrahimhafizhan/sociolla-all-brands-products-catalog](https://www.kaggle.com/datasets/ibrahimhafizhan/sociolla-all-brands-products-catalog) | 7,500+ products from 300+ brands, from sociolla.com (active dates run to December 2023); includes makeup | brand, product, categories, IDR price range and price per variant, rating, review count, wishlist count, repurchase counts | "Other (specified in description)": research and analysis only | Seeds a realistic `product_catalog.csv`: brands, categories, IDR prices, ratings and review counts. Size, SPF and ingredient must be parsed from product names. |
| **Indonesia Skincare From Female Daily Reviews** ✓ <br>[kaggle.com/datasets/prastyasusanto/indonesia-skincare-from-female-daily-reviews](https://www.kaggle.com/datasets/prastyasusanto/indonesia-skincare-from-female-daily-reviews) | About 7,400 skincare products, collected about 2023 | type (moisturizer, facial wash, sunscreen, toner, serum ...), name, brand, rating, total reviewers, link | Unknown | Category and brand popularity among Indonesian reviewers, with strong local brands (Wardah, Emina, Azarine, Somethinc). No prices. |
| Tokopedia 2025 (see section 2) | 5,553 products | `count_sold`, `price`, `discounted_price`, `stock`, `is_official`, `rating_average`, `shop_location` | CC BY-NC 4.0 | The only open source with **units sold and discounts**, as proxies for units, discount_pct and price positioning. Sold counts are cumulative; monthly review counts can stand in for monthly sales. |
| Sephora Products and Skincare Reviews <br>[kaggle.com/datasets/nadyinky/sephora-products-and-skincare-reviews](https://www.kaggle.com/datasets/nadyinky/sephora-products-and-skincare-reviews) | 8,000+ products and about 1M reviews (US, March 2023) | price, size, ingredients, highlights (such as fragrance-free), rating; reviewer skin type | CC BY 4.0 | An ingredient and claim taxonomy (niacinamide, ceramide, peptide, fragrance-free) and skin-type patterns. US prices and demand do not transfer. |
| Cosmetics datasets <br>[kaggle.com/datasets/kingabzpro/cosmetics-datasets](https://www.kaggle.com/datasets/kingabzpro/cosmetics-datasets) | 1,472 Sephora products (2020) | price, ingredients, five skin-type flags | GPL 2 | A small reference for ingredient-to-skin-type suitability. |
| Open Beauty Facts <br>[world.openbeautyfacts.org/data](https://world.openbeautyfacts.org/data) | Global barcode database; about 421 products tagged Indonesia | brands, categories, ingredients, labels | Database ODbL; contents DbCL; images CC BY-SA | Ingredient and label lookups; thin Indonesian coverage and no prices. |
| **BPOM Satu Data: cosmetics by product category** ✓ <br>[satudata.pom.go.id](https://satudata.pom.go.id/datasets/8-jumlah-produk-kosmetik-berdasarkan-kategori-produk) | Registered cosmetics in 153 categories (dataset created October 2021) | Facial cleanser 19,161; toner 10,881; moisturizer 9,660; sunscreen 8,081 | Marked open ("Terbuka") on data.go.id | A prior for the category mix of supply. A companion dataset gives registrations as 55.57% local, 34.11% imported and 10.32% contract-made (2020). Registrations are not sales. |

There is **no open sell-out panel** with brand, category, channel and region by month (Nielsen and Kantar sell theirs), and no Shopee, TikTok Shop or Lazada skincare dataset with sold counts was found. The best substitutes are the Tokopedia 2025 sold counts and the aggregates that Compas publishes (section 4).

## 4. Market size and industry figures

| Figure | Year | Source |
|---|---|---|
| Skin care US$2.55bn (+7.0%); CAGR 3.55% for 2026-31 ✓ | 2026, estimate | [Statista Market Insights](https://www.statista.com/outlook/cmo/beauty-personal-care/skin-care/indonesia) |
| Beauty and personal care US$10.35bn, 19.9% sold online | 2026, estimate | [Statista](https://www.statista.com/outlook/cmo/beauty-personal-care/indonesia) |
| Skin care US$2.52bn; 812.7 million units | 2024 | [MarketLine, via Research and Markets](https://www.researchandmarkets.com/reports/5992468/skincare-in-indonesia) |
| Skin care Rp24.1 trillion (facial Rp19.8 trillion) | 2019 | [GlobalData (2020)](https://www.globaldata.com/media/consumer/indonesian-skincare-sector-is-expected-to-reach-us2-5bn-by-2024-says-globaldata/) |
| Company value shares: L'Oréal 15%, Paragon 9%, Unilever 7% | 2025 | [Euromonitor report summary](https://www.euromonitor.com/skin-care-in-indonesia/report) |
| Beauty and care sales by marketplace: Shopee 63.5%, TikTok Shop 18.2%, Lazada 13.8%, Tokopedia 4.26%, Blibli 0.13% ✓ | February 2024 | [Compas](https://compas.co.id/article/top-market-share-kategori-beauty-care-2024/) |
| Beauty sales on Shopee and Tokopedia during Ramadan: Rp2.44T, Rp2.42T, Rp2.9T, Rp4.5T ✓ | 2022, 2023, 2024, 2025 | [Compas, via Databoks](https://databoks.katadata.co.id/en/consumer-durables-apparel/statistics/69b0c57200b9b/sales-value-of-beauty-products-in-indonesian-e-commerce-during-the-ramadan-period-2022-2025) |
| Beauty on Shopee and Tokopedia Rp8.9 trillion (+42%), of which sunscreen Rp424 billion | Q1 2024 | [Compas, via Bisnis](https://teknologi.bisnis.com/read/20240530/266/1769747/shopee-tokopedia-berebut-kue-bisnis-kecantikan-nilai-penjualan-rp89-triliun) |
| Beauty e-commerce Rp31.9 trillion (51.6% of online FMCG); sunscreen +60% | 2024 | [Compas, via CNBC Indonesia](https://www.cnbcindonesia.com/research/20250108111952-128-601595/penjualan-produk-kecantikan-tembus-rp-30-t-ini-trik-gaet-pembeli) |
| Top skincare brands on Shopee: Skintific 4.10%, Wardah 2.97%, Glad2Glow 2.51% | Q1 2025 | [Compas, via GoodStats](https://data.goodstats.id/statistic/10-brand-skincare-terlaris-di-shopee-indonesia-2025-mana-favoritmu-9jroA) |
| Imports of HS 3304 (beauty and skincare preparations) US$442.8M and US$487.4M (China US$244.0M, Korea US$97.3M) | 2023, 2024 | [UN Comtrade](https://comtradeplus.un.org/) |
| Cosmetics exports US$417M and US$473.8M | 2024, 2025 | [Kemenperin and BPOM, via Kompas](https://money.kompas.com/read/2026/05/19/153856126/ekspor-kosmetik-indonesia-naik-kemenperin-soroti-penguatan-ekosistem) |

Market definitions differ (skin care only, or all beauty; all channels, or only marketplace sales of products rated 4 stars or more), so compare a source only with itself over time. Full Statista, Euromonitor and Compas data are paid; these are their free headline figures.

## 5. Consumer survey data

### Respondent-level data

No public dataset can replace the simulated survey: none combines spend, channel, brand, NPS and Van Westendorp questions for Indonesian skincare buyers. Small, real Indonesian deposits do exist. They are mostly thesis surveys with Likert scales, enough to run MarketMind's K-Means and concept-test code on real answers.

| Dataset | Sample | Variables | Licence |
|---|---|---|---|
| **Ethical Issues of Digital Marketing on Skincare Products** ✓ <br>[doi.org/10.5281/zenodo.15752080](https://doi.org/10.5281/zenodo.15752080) | 440 valid of 651; Greater Jakarta, Java, Sumatra; April 2025 | Brand awareness, trust, misleading advertising, perceived deception, exaggerated claims, purchase intention, perceived risk; raw XLSX, processed CSV and questionnaire | Not stated (ask the authors) |
| **Determinants of purchase decisions among Gen Z toward Skintific** ✓ <br>[doi.org/10.5281/zenodo.22950270](https://doi.org/10.5281/zenodo.22950270) | 256; Indonesia; 2026 | Age, education, domicile, occupation, Shopee promotion exposure; Likert scales for perceived value, message quality, trust, satisfaction, purchase intention | CC BY 4.0 |
| Dataset_Halal Cosmetic <br>[data.mendeley.com/datasets/kncwmsj6pc/1](https://data.mendeley.com/datasets/kncwmsj6pc/1) | 390 Gen Z Muslims; mall intercepts in South Jakarta, Surabaya, Malang and Yogyakarta | Religiosity, group conformity, perceived value, continued purchase intention | CC BY 4.0 |
| Gen Z online word of mouth and local skincare <br>[data.mendeley.com/datasets/y6j7xdy243/1](https://data.mendeley.com/datasets/y6j7xdy243/1) | 315; Jabodetabek; ages 14-29 | Online word of mouth and local skincare buying (item list on the record) | CC BY 4.0 |
| Greenwashing and brand trust <br>[data.mendeley.com/datasets/s58mtb8vtt/1](https://data.mendeley.com/datasets/s58mtb8vtt/1) | 189 Gen Z | Greenwashing perception, brand trust; CSV with codebook | CC BY 4.0 |
| Customer Personality Analysis (off-domain) <br>[kaggle.com/datasets/imakash3011/customer-personality-analysis](https://www.kaggle.com/datasets/imakash3011/customer-personality-analysis) | About 2,240 customers | Income, education, spend by category, purchases by channel, campaign response | CC0: Public Domain |

No public respondent-level Van Westendorp data exists for cosmetics. Two UGM undergraduate theses applied the method to Indonesian cosmetics ([lipstick, n = 150, 2019](https://etd.repository.ugm.ac.id/penelitian/detail/175269); [beauty products, n = 500, 2020](https://etd.repository.ugm.ac.id/penelitian/detail/192411)); their price points are only in the full texts. **Official microdata:** BPS SUSENAS (household spending on personal care by province) can be requested through [silastik.bps.go.id](https://silastik.bps.go.id). It is free (Rp0) for Indonesian educational institutions with a request letter signed at dean level and a signed data-use agreement, for non-commercial use only.

### Numbers for calibrating the simulator

| Statistic | Value | Sample | Year | Source |
|---|---|---|---|---|
| Skincare bought through e-commerce / minimarket / supermarket / hypermarket ✓ | 57% / 18% / 14% / 4% | 10,616 | Sep 2021-Jun 2022 | [Populix, via Medcom](https://www.medcom.id/teknologi/news-teknologi/MkMPPVjb-orang-indonesia-paling-suka-beli-produk-selfcare-via-ecommerce) |
| Buy skincare at least monthly; can spend up to Rp250k a month ✓ | 77%; 8 in 10 | 10,616 | Sep 2021-Jun 2022 | Populix, as above |
| Purchase frequency ✓ | monthly 33%, every 2-3 months 26%, when run out 15%, only in big promotions 6%, every 4-6 months 5%, yearly 2%, non-users 13% | 1,100 Gen Z and Millennials | Sep 2024 | [Populix, via Databoks](https://databoks.katadata.co.id/en/consumer-durables-apparel/statistics/68243a6789280/how-often-do-gen-z-and-millennials-buy-skincare-this-is-the-survey) |
| Products bought ✓ | cleanser 63%, sunscreen 54%, moisturizer 51%, serum or essence 33%, toner 23% | 1,100 | Sep 2024 | Populix, as above |
| Use sunscreen, women / men; say a halal claim matters ✓ | 75% / 42%; 75% | 1,700 | 2024 | [Jakpat](https://insight.jakpat.net/makeup-skincare-and-bodycare-indonesian-favorites-2024/) |
| Top products used ✓ | face wash 72%, sunscreen 64%, moisturizer 52% | 1,700 | 2024 | Jakpat, as above |
| Top skin concerns, women ✓ | dull skin 53.8%, enlarged pores 49.3% | 9,000 women aged 15-65 | 2024 | [ZAP Beauty Index, via Fortune IDN](https://www.fortuneidn.com/luxury/riset-zap-beauty-index-2024-kulit-kusam-jadi-masalah-utama-perempuan-00-4vfn9-3n4zk6) |
| Monthly skincare spend above Rp300k / above Rp500k, women ✓ | 71.4% / 28.6% | 9,000 | 2024 | ZAP, as above |
| Consider ingredients / brand reputation; would pay more for an eco brand ✓ | 66.4% / 42.8%; 89.4% | 9,000 | 2024 | ZAP, as above |
| Use domestic skincare brands | 87% (Korean 31%, Japanese 16%) | 961 users | Sep 2024 | [Populix, via Databoks](https://databoks.katadata.co.id/en/consumer-durables-apparel/statistics/6824465f2ae1d/survey-most-indonesian-young-people-use-domestic-skincare-products) |
| E-commerce is the main skincare channel; prefer local skincare; influencers affect purchases | 62%; 76%; 59% | 1,088 | Jul 2024 | [Populix, via Industry.co.id](https://www.industry.co.id/read/136178/lebih-dari-60-persen-konsumen-pilih-beli-skincare-dan-fashion-lewat-e-commerce) |
| Most-used e-commerce platform, all internet users | Shopee 53.2%, TikTok Shop 27.4%, Tokopedia 9.6%, Lazada 9.1% | 8,700 | Apr-Jul 2025 | [APJII, via GoodStats](https://goodstats.id/article/e-commerce-paling-sering-diakses-2025-shopee-masih-juara-wyZqk) |

ZAP's sample is urban and beauty-engaged, so treat its spending figures as an upper bound; Populix's broad tracking puts most spending below Rp250k a month.

## 6. Other real signals

| Source | What it offers | Licence or terms | Use in MarketMind |
|---|---|---|---|
| Python [`holidays`](https://pypi.org/project/holidays/) | Indonesian public holidays, including Idul Fitri (2 days) and Idul Adha, with dates taken from government decrees; joint-leave days (cuti bersama) | MIT | Check the hand-coded Ramadan table in `ml/calendar_id.py` against official Eid dates. The package has no Ramadan start date, so the start would still be derived from Eid. |
| [BPS WebAPI](https://webapi.bps.go.id/developer/) | Official statistics as JSON: population by province, household consumption (SUSENAS tables), e-commerce statistics | Free with registration and a token; outputs must credit "This service uses the Badan Pusat Statistik (BPS) API." | Weights for the seven regions; a second macro source beside the World Bank. |
| Google Trends | Relative search interest for Indonesia and its provinces (for example ceramide, niacinamide, sunscreen) | The unofficial `pytrends` library was archived in April 2025; the official Trends API (alpha, July 2025) admits a limited number of testers | Real topic trends to compare with the Market & Trend Analyst's social trends. |
| [UN Comtrade](https://comtradeplus.un.org/) | Trade in HS 3304 by partner, yearly and monthly | Data "provided for internal use only" and "may not be re-disseminated in any form without UNSD's permission" | A supply-side check on how much of the market is imported. |
| World Bank Open Data | Eight macro indicators for Indonesia | Open (CC BY 4.0) | Already used by the Data Collection Agent. |

## 7. How the simulated data compares

Comparing MarketMind's simulated data with the real figures above shows where the simulator is realistic and where it should be recalibrated. The simulated values come from the bundled data (`scripts/generate_data.py`, seed 2026) after cleaning.

| Statistic | MarketMind simulation | Real benchmark | Verdict |
|---|---|---|---|
| Skin-care market size, 2019 | Rp23.4 trillion | Rp24.1 trillion (GlobalData) | Close |
| Market size, 2024 and 2026 | Rp35.1 trillion; Rp41.6 trillion (estimate) | US$2.52bn (MarketLine, 2024) and US$2.55bn (Statista, 2026), about Rp40-41 trillion at Rp16,000 per US$ | In range; 2024 about 13% low |
| Market growth | 8.6% a year, 2019-2025 | +7.0% in 2026, then 3.55% a year (Statista) | Plausible, slightly high |
| Marketplace shares, Feb 2024 (online channels only) | Shopee 44.7%, Tokopedia 22.5%, TikTok Shop 22.3%, Lazada 10.5% | Shopee 63.5%, TikTok Shop 18.2%, Lazada 13.8%, Tokopedia 4.26% (Compas) | **Recalibrate:** Tokopedia too high, Shopee too low |
| Star mix of reviews with text, 1-2 / 3 / 4-5 stars | 14.6% / 8.6% / 76.9% | 10.8% / 17.6% / 71.7% (Female Daily, a review community) | Check against the Tokopedia 2025 reviews before changing (the Shopee/Tokopedia beauty set is balanced by rating, so it cannot show the natural mix) |
| Monthly skincare spend of Rp250k or less | 71% | 8 in 10 (Populix 2021-22); ZAP shows a richer, urban sample | Consistent with the broad sample |
| Buy skincare at least once a month | 81% | 77% (Populix 2021-22); 33% of all respondents (38% of users) in Populix 2024 | The sources disagree; the simulator matches the larger 2021-22 tracking |
| Halal claim important (rated 4-5 of 5) | 49% | 75% (Jakpat 2024) | **Recalibrate:** too low |
| Prefer buying online | 76% (24% prefer offline retail) | e-commerce 57% (Populix 2021-22), 62% (Populix 2024) | Somewhat high |
| Lazada as the preferred channel | 0% of respondents | 9.1% name it their most-used platform (APJII 2025) | **Recalibrate:** add Lazada |

## 8. Licences, terms and personal data

| Status | Sources | What it allows |
|---|---|---|
| Open, redistribution allowed with credit | Shopee/Tokopedia beauty reviews (Apache-2.0), PRDECT-ID, Sephora, Azarine comments and the CC BY survey deposits (CC BY 4.0), Lazada reviews and Customer Personality (CC0), IndoNLU (MIT or Apache-2.0), `holidays` (MIT), Open Beauty Facts (ODbL), World Bank | Use in MarketMind and in published work; cite the source |
| Non-commercial or research only | Tokopedia 2025 (CC BY-NC 4.0), Sociolla catalogue, UGM tweets (CC BY-NC per the author), BPS API (credit required), UN Comtrade (internal use; no re-dissemination) | Fine for a university project; do not redistribute the data or use it commercially |
| Licence unknown | Both Female Daily datasets, Natasha tweets, the Zenodo "Ethical Issues" survey | Use only for private research and validation, do not redistribute, and ask the owner for permission before publishing results based on them |

Also note:

- **Scraped content.** Several datasets were scraped from Shopee, Tokopedia, Female Daily or Twitter, whose terms of service may restrict reuse. The dataset licence covers only what the uploader could grant.
- **Personal data.** Some datasets contain user names or account handles (for example Female Daily's `UserName`). Indonesia's Personal Data Protection Law (UU No. 27 Tahun 2022) applies to them, so pseudonymise reviewer identities before analysis and never publish raw rows that identify people.
- **Keep downloads out of git.** Put downloaded files in `data/external/`, which `.gitignore` already excludes, and record the source and licence of each file next to it.

## 9. Suggested next steps

1. **Validate the sentiment agent on real text.** Done on 4 November 2026 with `scripts/validate_on_real_data.py`, on the Shopee/Tokopedia beauty reviews and IndoNLU SmSA ([EVALUATION.md §4.6](EVALUATION.md#46-sentiment-on-real-text-external-validation)). The models trained on simulated reviews reach only macro-F1 0.43-0.47 on the real reviews. Adding the real reviews to the training data (`--sentiment-data study+real`) raises this to 0.662 while keeping 0.820 on the study's reviews and passing all 25 ground-truth checks.
2. **Test the weak-supervision assumption.** On PRDECT-ID, measure how often star-derived labels agree with the human sentiment labels.
3. **Test the transfer check on real social text.** Map the Natasha Skincare emotions to three classes and score them with the transfer model.
4. **Recalibrate the simulator** with the benchmarks marked "Recalibrate" in section 7 (channel shares, halal importance, Lazada), then re-run `python scripts/evaluate_agents.py` to confirm that the 25 checks still pass.
5. **Add a real-data mode.** Done for the sentiment models: `python run.py --sentiment-data study+real` trains them on the study's reviews plus the real beauty reviews, and `real` on the real reviews only ([EVALUATION.md §4.6](EVALUATION.md#46-sentiment-on-real-text-external-validation)). Still open: an adapter that loads the Tokopedia 2025 beauty subset as real reviews and catalogue rows, filling in or marking the columns it lacks, so that a whole study can run on real marketplace data (for non-commercial use).
