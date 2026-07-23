# Sentiment Project Context

## 1. Executive summary

- **Fakta**: aplikasi utama berada di `laravel-app`, git root `laravel-app`, commit saat audit `668959658198012b96d27edca7ac956ad89d196e`.
- **Fakta**: stack utama Laravel 13/PHP, Blade/Tailwind/Alpine/Chart.js, MySQL, plus service Python/FastAPI untuk sentiment inference.
- **Fakta**: production inference aktif tidak langsung memakai checkpoint Hugging Face `w11wo/indonesian-roberta-base-sentiment-classifier`; endpoint Python memuat artifact lokal `storage/app/sentiment_model/indobert_finetuned_v1` via `SENTIMENT_MODEL_DIR` default di `quant/sentiment_api.py::MODEL_DIR`.
- **Fakta**: checkpoint `w11wo/indonesian-roberta-base-sentiment-classifier` dipakai sebagai base training di `quant/finetune_sentiment_model.py::CHECKPOINT` dan `quant/finetune_sentiment_weighted_experiment.py::CHECKPOINT`, bukan sebagai artifact serving langsung.
- **Fakta**: final `sentiment_label` dipilih lewat ML/rule resolver; kalau ML dan rule beda, `App\Services\Sentiment\SentimentTiebreakResolver::resolve()` memilih ML dan method `ml_tiebreak`.
- **Fakta**: database read-only berhasil ke MySQL lokal setelah sandbox escalation; `news_articles` berisi 1,888 baris dan `sentiment_manual_labels` berisi 1,888 baris saat audit.
- **Kontradiksi penting**: dokumentasi lama menyebut 801 label/120 test untuk skor 58.16%, tetapi file dataset aktif `storage/app/sentiment_finetune/*.jsonl` sekarang berisi 692/148/148, dan locked R5b hard-case berisi 153. Skor 58.16% ada sebagai artifact lama, bukan hasil yang dihitung ulang pada task ini.
- **Tidak dilakukan**: tidak ada refactor, training, migration, final evaluation baru, perubahan dataset, atau perubahan DB.

## 2. Repository map

### Root dan runtime

- **Root workspace**: `/Applications/XAMPP/xamppfiles/htdocs/Implementasi AnalisisSentimenBerita`.
- **Git root aplikasi**: `/Applications/XAMPP/xamppfiles/htdocs/Implementasi AnalisisSentimenBerita/laravel-app`.
- **Bahasa**: PHP, Python, JavaScript, Blade.
- **Framework utama**: Laravel 13 (`laravel-app/composer.json`), FastAPI (`laravel-app/quant/sentiment_api.py`), Vite/Tailwind/Alpine (`laravel-app/package.json`).
- **Versi runtime lokal**: PHP 8.5.5 CLI, Python 3.9.6, Node v24.9.0, npm 11.6.0, Composer 2.9.5.
- **Package manager**: Composer, npm, Python virtualenv `laravel-app/quant/.venv-sentiment`.

### Struktur ringkas

```text
.
├── BASELINE_AUDIT_REQUESTED_FILES.md
├── PROJECT_CONDITION_REPORT.md
├── QUANT_AUDIT_CONTEXT.md
├── baseline-audit-upload/
├── database/
│   ├── database.sqlite
│   └── migrations/
└── laravel-app/
    ├── app/
    │   ├── Console/Commands/
    │   ├── Http/Controllers/
    │   ├── Models/
    │   └── Services/
    ├── bootstrap/
    ├── config/
    ├── database/migrations/
    ├── docs/
    ├── ops/macos/
    ├── output/
    ├── quant/
    ├── resources/
    ├── routes/
    ├── storage/app/sentiment_finetune/
    ├── storage/app/sentiment_model/
    └── tests/
```

Excluded from tree: `vendor`, `node_modules`, venv content, cache, generated output detail, model binary detail, large datasets.

### Entry point dan konfigurasi

- **Laravel CLI**: `laravel-app/artisan`.
- **Laravel bootstrap**: `laravel-app/bootstrap/app.php`.
- **Web routes**: `laravel-app/routes/web.php`.
- **Scheduler routes**: `laravel-app/routes/console.php`.
- **Sentiment API entry**: `laravel-app/quant/sentiment_api.py`.
- **Sentiment API launcher**: `laravel-app/start_sentiment_api.sh`.
- **Config utama**: `laravel-app/config/app.php`, `laravel-app/config/database.php`, `laravel-app/config/news.php`, `laravel-app/config/sentiment.php`, `laravel-app/config/services.php`.
- **Env template**: `laravel-app/.env.example`; `.env` ada tetapi tidak dibaca/cetak nilainya.
- **Docs**: `laravel-app/README.md`, `laravel-app/DEMO_GUIDE.md`, `laravel-app/CODEX_HANDOFF.md`, `laravel-app/docs/`.
- **Tests**: `laravel-app/tests/Feature`, `laravel-app/tests/Unit`, dan Python tests di `laravel-app/quant/test_*.py`.
- **ML pipeline**: `laravel-app/quant/finetune_sentiment_model.py`, `laravel-app/quant/finetune_sentiment_weighted_experiment.py`, `laravel-app/quant/evaluate_sentiment_models.py`, `laravel-app/quant/sentiment_api.py`.
- **Migrations/schema**: `laravel-app/database/migrations/`.
- **Deployment config**: `laravel-app/ops/macos/com.sentimena.sentiment-api.plist`, `laravel-app/ops/macos/com.sentimena.prediction-api.plist`, `laravel-app/ops/macos/com.luthfimirza.sentimena.scheduler.plist`. Tidak ditemukan Dockerfile atau docker-compose pada depth 3.

## 3. Current sentiment flow

### Diagram teks

```text
Scheduler / manual command
  -> php artisan news:fetch / news:fetch-ojk
  -> NewsAggregationService::refreshFromProvider()
  -> provider fetcher: rss_local, gnews, google_news_rss, idx_disclosure, business_site_search, ojk, newsapi, finnhub, gdelt, mock
  -> domain/exclusion/relevance/language/quality/dedup filters
  -> analyzer = SentimentEngineManager::getAnalyzer()
  -> PythonApiSentimentAnalyzer::analyze() POST PYTHON_SENTIMENT_ENDPOINT
  -> RuleBasedSentimentAnalyzer::analyze() baseline
  -> SentimentTiebreakResolver::resolve()
  -> NewsArticle::updateOrCreate()
  -> news_articles sentiment_* + ml_* + rule_* columns
```

### Tahap detail

| Tahap | File dan class/function | Input | Output | Dependency penting |
|---|---|---|---|---|
| Scheduler fetch | `routes/console.php`, `Schedule::command()` | waktu pasar/weekend | command `news:fetch`, `news:fetch-ojk` | Laravel scheduler |
| Manual fetch | `app/Console/Commands/FetchNewsCommand.php`, class `FetchNewsCommand`, signature `news:fetch {--limit=20} {--stock=} {--provider=} {--debug}` | stock aktif atau `--stock`, provider optional | stats raw/saved/updated/dropped | `NewsAggregationService`, `Stock` |
| Provider aggregation | `app/Services/News/NewsAggregationService.php`, `refreshFromProvider()` | `Stock`, limit, provider override | raw article collection | fetcher classes di `app/Services/News/*Fetcher.php` |
| Filter berita | `NewsAggregationService::persistRawArticles()` | raw title/url/source/text | accepted/dropped article stats | relevance scoring, keyword mapper, deduper, `config/news.php` |
| Text input untuk inference | `NewsAggregationService::persistRawArticles()` dan `PythonApiSentimentAnalyzer::analyze()` | `title`, `summary`, `content_snippet/full_text` | string input max 512 char sebelum API | `mb_substr`, `array_filter` |
| Python ML inference | `app/Services/Sentiment/PythonApiSentimentAnalyzer.php`, `analyze()` | text/context | label, score, confidence, prob_positive/neutral/negative | Laravel HTTP client, `PYTHON_SENTIMENT_ENDPOINT`, optional `HUGGINGFACE_API_TOKEN` |
| Rule baseline | `app/Services/Sentiment/RuleBasedSentimentAnalyzer.php`, `analyze()` | text/context | label, score, confidence, matched terms | lexicon internal, tokenization regex |
| Tie-break | `app/Services/Sentiment/SentimentTiebreakResolver.php`, `resolve()` | ML label, rule label, result arrays | final label/score/confidence/method/agreement | none |
| Persist | `NewsAggregationService::persistRawArticles()` | resolved sentiment + article | `news_articles` upsert | Eloquent `NewsArticle::updateOrCreate()` |
| Reanalysis | `app/Console/Commands/ReanalyzeSentimentCommand.php`, `processArticles()` | existing articles | updated sentiment fields | `SentimentEngineManager`, `RuleBasedSentimentAnalyzer` |
| Maintenance analyze | `app/Console/Commands/AnalyzeSentimentCommand.php` | articles missing sentiment fields | updated sentiment fields | same analyzer stack |

### Text fields dan cleaning

- **Article selection text**: `summary ?? content_snippet ?? title` in `SentimentAnalysisService::analyzeAndUpdate()` and `ExportSentimentFinetuneDatasetCommand::buildProductionInputText()`.
- **Python API input construction**: `title`, `summary`, and fallback text only when fallback text length `< 200`, joined with `. `, fallback to text if empty, then `mb_substr(..., 0, 512)` in `PythonApiSentimentAnalyzer::analyze()`.
- **Rule tokenization**: lowercases via `mb_strtolower`, splits with regex `/[^a-zA-Z]+/u` in `RuleBasedSentimentAnalyzer::tokenize()`; digits and non-letter separators discarded.
- **Python model cleaning**: no lowercasing or custom normalization found in `quant/sentiment_api.py::sentiment()`; tokenizer handles raw trimmed input.

### Batch vs real-time

- **Real-time during ingestion**: `NewsAggregationService::persistRawArticles()` calls analyzer per accepted article.
- **Batch/reanalysis**: `sentiment:reanalyze`, `news:analyze`, and `news:rescore-sentiment` update existing rows.
- **API serving**: FastAPI `/sentiment` is single-text per request in `quant/sentiment_api.py::sentiment()`. No batch endpoint found.

### Error dan timeout

- **Laravel side timeout**: `PYTHON_SENTIMENT_TIMEOUT`, default 15 in `config/sentiment.php` and `PythonApiSentimentAnalyzer::analyze()`.
- **HTTP non-success**: logged warning, returns `python_unavailable` result in `PythonApiSentimentAnalyzer::unavailableResult()`.
- **Invalid payload**: logged warning, returns unavailable result.
- **Exception**: caught as `Throwable`, logged warning, returns unavailable result.
- **FastAPI model missing**: `/health` returns `model_not_loaded`; `/sentiment` raises HTTP 503.
- **FastAPI empty input**: `/sentiment` raises HTTP 422.
- **Fallback fact**: in Python engine default, unavailable result is neutral-like ML unavailable; no automatic rule-based fallback in `PythonApiSentimentAnalyzer`. Rule baseline still computed separately by aggregation/reanalysis before resolver.

## 4. Active model

| Item | Fakta ditemukan |
|---|---|
| Active serving artifact | `storage/app/sentiment_model/indobert_finetuned_v1`, default `SENTIMENT_MODEL_DIR` in `quant/sentiment_api.py` |
| Base checkpoint for training | `w11wo/indonesian-roberta-base-sentiment-classifier` in `quant/finetune_sentiment_model.py::CHECKPOINT` and `quant/finetune_sentiment_weighted_experiment.py::CHECKPOINT` |
| Library model | `transformers.AutoModelForSequenceClassification`, `RobertaForSequenceClassification` in local `config.json` |
| Tokenizer | `transformers.AutoTokenizer.from_pretrained(str(MODEL_DIR))` in `quant/sentiment_api.py::load_model()` |
| Config local | `storage/app/sentiment_model/indobert_finetuned_v1/config.json` |
| Artifact files | `config.json`, `model.safetensors`, `tokenizer.json`, `vocab.json`, `merges.txt`, `special_tokens_map.json`, `tokenizer_config.json`, `training_args.bin` |
| Labels | 3 labels via `id2label`: `0=positive`, `1=neutral`, `2=negative`; `label2id`: `positive=0`, `neutral=1`, `negative=2` |
| Max token length | 256 in `quant/sentiment_api.py::sentiment()` and training scripts |
| Truncation | `truncation=True` |
| Padding | serving does not specify padding; training/evaluation use `DataCollatorWithPadding` |
| Device selection | serving does not move model/input to CUDA/MPS; effective CPU unless PyTorch default changed externally. Local `torch.cuda.is_available()` returned false. |
| Batch size inference | FastAPI single request; evaluation uses `per_device_eval_batch_size=16`; training uses eval batch 16 |
| Threshold khusus | no confidence threshold for final model decision; argmax softmax. Quality/relevance thresholds exist for article filtering in `config/news.php`. |
| Fallback if model fails | Laravel returns `python_unavailable`; FastAPI returns 503 if model absent |
| Artifact version | directory name `indobert_finetuned_v1`; FastAPI title version `1.0.0`; no semantic model metadata file beyond config/report found |

**Verification of `w11wo/indonesian-roberta-base-sentiment-classifier`**:

- **Used for training**: yes, in `quant/finetune_sentiment_model.py` and `quant/finetune_sentiment_weighted_experiment.py`.
- **Used for active inference directly**: no evidence. Active inference loads local `storage/app/sentiment_model/indobert_finetuned_v1` via `quant/sentiment_api.py`.

## 5. Dataset and label schema

### Database tables verified read-only

#### `news_articles`

- **Existence**: verified in MySQL through Laravel bootstrap.
- **Count**: 1,888 rows at audit time.
- **Primary key**: `id`.
- **Foreign keys by migration/model**: `stock_id` to `stocks`, `news_source_id` to `news_sources`; `NewsArticle::manualLabels()` has many `SentimentManualLabel`.
- **Sentiment distribution**: `negative=134`, `neutral=1460`, `positive=294`.
- **Missing values measured**: `title=0`, `summary=0`, `full_text=1786`.
- **Duplicates measured**: duplicate `source_url=0`, exact duplicate `(title, summary)=35` groups.

Schema fields verified in DB: `id`, `stock_id`, `news_source_id`, `title`, `slug`, `source_url`, `published_at`, `summary`, `content_snippet`, `full_text`, `sentiment_label`, `sentiment_score`, `sentiment_confidence`, `sentiment_method`, `ml_sentiment_label`, `ml_sentiment_score`, `ml_confidence`, `ml_prob_positive`, `ml_prob_neutral`, `ml_prob_negative`, `rule_sentiment_label`, `rule_sentiment_score`, `ml_rule_agree`, `sentiment_meta`, `language`, `detected_language`, `raw_payload`, `fetched_at`, `analyzed_at`, `created_at`, `updated_at`, `relevance_score`, `entity_match_score`, `market_context_score`, `language_score`, `final_quality_score`, `relevance_band`, `quality_band`, `source_provider`, `source_weight`, `matched_keywords`, `quality_flags`.

#### `sentiment_manual_labels`

- **Existence**: verified in MySQL.
- **Count**: 1,888 rows at audit time.
- **Primary key**: `id`.
- **Foreign keys by migration/model**: `news_article_id` to `news_articles`, `user_id` to `users`.
- **Label distribution**: `negative=145`, `neutral=1379`, `positive=364`.
- **Sample method distribution**: `legacy_hard_case=1023`, `representative_random=865`.
- **Missing label**: 0.
- **Duplicate `(news_article_id,user_id)`**: 0.
- **Model constants**: `SentimentManualLabel::LABELS = ['positive','neutral','negative']`; `SAMPLE_METHODS = ['legacy_hard_case','representative_random']`.

Schema fields verified in DB: `id`, `news_article_id`, `user_id`, `label`, `sample_method`, `created_at`, `updated_at`.

### Column availability and usage

| Column | Status | Evidence |
|---|---|---|
| `title` | ada dan digunakan | DB schema; model fillable; inference context; export text builder |
| `summary` | ada dan digunakan | DB schema; inference input; export text builder |
| `content_snippet` | ada dan digunakan | fallback text in `SentimentAnalysisService` and controllers |
| `full_text` | ada dan digunakan sebagian | context body for analyzer; often NULL (`1786/1888`) |
| `sentiment_label` | ada dan digunakan | final persisted label; scheduler/reanalysis filters |
| `ml_sentiment_label` | ada dan digunakan | ML label storage, manual validation, resolver input |
| `ml_prob_positive` | ada dan digunakan | Python response storage; active learning ordering; audit confidence |
| `ml_prob_neutral` | ada dan digunakan | Python response storage; active learning; audit confidence |
| `ml_prob_negative` | ada dan digunakan | Python response storage; active learning; audit confidence |
| `rule_sentiment_label` | ada dan digunakan | rule baseline storage; validation summary; resolver input |
| `relevance_score` | ada dan digunakan | filter/persist quality metadata |
| `quality_band` | ada dan digunakan | derived/persisted in `NewsAggregationService` |
| `entity_match_score` | ada dan digunakan | relevance metadata; stored DB |
| `matched_keywords` | ada dan digunakan | relevance metadata stored and cast array |
| `sentiment_method` | ada dan digunakan | persisted method: `python`, `python_unavailable`, `ml_tiebreak`, etc. |
| `analyzed_at` | ada dan digunakan | set during ingestion/reanalysis; indexed |
| `sample_method` | ada dan digunakan | `sentiment_manual_labels`; export filters; validation modes |
| `user_id` | ada dan digunakan | `sentiment_manual_labels`; relation to `User`; uniqueness query measured |

### Sources for training/evaluation data

- **DB source**: `sentiment_manual_labels` joined to `news_articles` through `SentimentManualLabel::with('article')` in `ExportSentimentFinetuneDatasetCommand::handle()`.
- **Export format**: JSONL rows with `news_article_id`, `text`, `label`, `sample_method`, `ml_sentiment_label`, `rule_sentiment_label`.
- **Text selection**: `buildProductionInputText()` uses title + summary + short fallback, max 512 characters.
- **Label origin**: manual labels collected through `SentimentValidationController::store()`; label choices constrained by `SentimentManualLabel::LABELS`.
- **Candidate selection**: legacy hard-case/active learning queries use ML-vs-rule disagreement and probabilities; representative random uses random articles not yet labeled for that method.

## 6. Train-validation-test split

### Current exported split files

| File | Size | Distribution | Duplicate IDs | Exact duplicate text | SHA256 |
|---|---:|---|---:|---:|---|
| `storage/app/sentiment_finetune/train.jsonl` | 692 | neutral 403, negative 74, positive 215 | 0 | 9 | `bbf9e1cdc410f5ff1bda3be74278d3f7c8dddf1508ed8a430ba4443e927ff890` |
| `storage/app/sentiment_finetune/val.jsonl` | 148 | neutral 86, negative 16, positive 46 | 0 | 1 | `6e32ab4d19648b9a0db1f1c1a2e39d7f3d7272c6242784fb53b286c73b88ccc7` |
| `storage/app/sentiment_finetune/test.jsonl` | 148 | neutral 87, positive 46, negative 15 | 0 | 0 | `6b5a7863dfdb58c4a307983a4b9b998e89de230eb16cd07a730d721b0492c5a5` |

### Locked R5b test files

| File | Size | Distribution | Duplicate IDs | Exact duplicate text | SHA256 |
|---|---:|---|---:|---:|---|
| `output/prediction_research/sentiment_r5b_locked_tests/legacy_hard_case_test.jsonl` | 153 | negative 18, neutral 88, positive 47 | 0 | 0 | `538db53806305de07b315c12bf878caf34b80c2a525a65fc670d611f8dd3b60c` |
| `output/prediction_research/sentiment_r5b_locked_tests/representative_random_test.jsonl` | 865 | neutral 789, negative 21, positive 55 | 0 | 14 | `281a7a699f7c12435b1d98dc397bf2cbe1a1dcff80efef9ce7d09479fb34f338` |

### Split method facts

- **Train set**: yes, generated by `ExportSentimentFinetuneDatasetCommand` and consumed by training scripts.
- **Validation set**: yes, `val.jsonl`, used by `Trainer` evaluation and best-model selection in training scripts.
- **Test set**: yes, `test.jsonl`; locked R5b test files also exist.
- **Random seed**: default 42 in export command and training scripts.
- **Stratification**: yes, split groups rows by `label` in `stratifiedSplit()`.
- **Grouping**: no group-aware split found; no grouping by source URL, stock, article family, or duplicate text found.
- **Time split**: no; split is random stratified.
- **Potential leakage**: duplicate text exists in train/val and representative test; no cross-split duplicate leakage analysis found in code beyond duplicate counts performed for this report.
- **Test used for tuning**: documentation warns not to tune on test, but evidence of procedural enforcement is partial. No code-enforced test lock verification found.
- **120-row locked test**: artifact `sentiment_finetune_report.json` references old 120-row test; current `storage/app/sentiment_finetune/test.jsonl` is 148 rows. So 120-row test is not currently represented by that path.
- **Checksum availability**: no stored checksum file found for tested split paths. Checksums above were computed read-only for report and not written as lock files.

## 7. Evidence for 58.16% macro-F1

### Evidence found

- `laravel-app/output/prediction_research/sentiment_finetune_report.json` contains `test_set_results.finetuned_macro_f1 = 0.5816`.
- Same file contains `checkpoint = w11wo/indonesian-roberta-base-sentiment-classifier`, `train_size=561`, `val_size=120`, `test_size=120`, `label2id={negative:2, neutral:1, positive:0}`, and `model_saved_to=storage/app/sentiment_model/indobert_finetuned_v1`.
- Same file contains classification report: accuracy `0.65`, macro avg F1 `0.5816278629254753`, weighted avg F1 `0.6366702217317423`.
- Per-class F1 in same file: positive `0.37735849056603776` support 31, neutral `0.7468354430379747` support 75, negative `0.6206896551724138` support 14.
- Baselines in same file: rule-based macro-F1 `0.5482`, raw ML baseline macro-F1 `0.3183`.
- `laravel-app/DEMO_GUIDE.md` states ML fine-tuned from 801 manual labels and achieved 58.16% macro-F1, rule-based 54.82%, raw model 35.6% accuracy.
- `laravel-app/CODEX_HANDOFF.md` references `0.5816` as old hard-case benchmark and warns newer representative test is easier/not comparable.

### Evidence missing or insufficient

- **Experiment date**: not present in `sentiment_finetune_report.json`.
- **Git commit for experiment**: not present in artifact.
- **Command used**: inferred likely `python quant/finetune_sentiment_model.py`, but exact command not stored in report.
- **Confusion matrix**: not found in `sentiment_finetune_report.json`; training script `finetune_sentiment_model.py` does not visibly store confusion matrix in the report segment inspected.
- **Hyperparameters**: training script defines them, but artifact report does not preserve all values.
- **Checksum for 120-row test**: not found.
- **Reproduction**: not rerun; task forbids long training/final evaluation.

## 8. Training pipeline

### Base training script

- **Entry point**: `quant/finetune_sentiment_model.py::main()`.
- **Command**: likely `quant/.venv-sentiment/bin/python quant/finetune_sentiment_model.py` from `laravel-app`; exact historical command not found in artifact.
- **Dataset loader**: `load_jsonl()` reads `storage/app/sentiment_finetune/train.jsonl`, `val.jsonl`, `test.jsonl`.
- **Preprocessing**: JSONL rows use prebuilt `text`; tokenizer applies truncation max 256.
- **Tokenizer**: `AutoTokenizer.from_pretrained(CHECKPOINT)`.
- **Model init**: `AutoModelForSequenceClassification.from_pretrained(CHECKPOINT, num_labels=3)`.
- **Label mapping**: copied from base checkpoint config; `id2label = {v:k for k,v in label2id.items()}`.
- **Loss**: default `Trainer` cross-entropy in base script.
- **Optimizer/scheduler**: default Hugging Face Trainer/TrainingArguments; no custom optimizer found.
- **Batch sizes**: train 8, eval 16.
- **Seed**: 42.
- **Metric**: macro-F1 via sklearn `f1_score` and `classification_report`.
- **Checkpoint selection**: `metric_for_best_model='macro_f1'` / best model at end in base script.
- **Saving**: model/tokenizer saved to `storage/app/sentiment_model/indobert_finetuned_v1`; report JSON/TXT to `output/prediction_research/sentiment_finetune_report.*`.

### Weighted experiment script

- **Entry point**: `quant/finetune_sentiment_weighted_experiment.py::main()`.
- **Features**: class weighting schemes, custom `WeightedTrainer`, resumed/candidate output directories, test evaluation.
- **Evidence**: `CHECKPOINT`, `MAX_LENGTH=256`, train batch 8, eval batch 16, class weight function, macro-F1 metrics.

### Evaluation script

- **Entry point**: `quant/evaluate_sentiment_models.py::main()`.
- **Purpose**: compare production and candidate models on locked hard-case and representative test JSONL files.
- **Defaults**: production `storage/app/sentiment_model/indobert_finetuned_v1`, candidate `storage/app/sentiment_model/indobert_finetuned_r5b_candidate`.
- **Output**: `output/prediction_research/sentiment_r5b_dual_eval_report.json/.txt`.

### Feature availability

| Feature | Status | Evidence |
|---|---|---|
| validation split | sudah tersedia | export command and training scripts |
| macro-F1 selection | sudah tersedia | training scripts use macro-F1 metric |
| per-class metrics | sudah tersedia | sklearn classification report |
| confusion matrix | belum tersedia | no stored confusion matrix found for sentiment report |
| weighted loss | sebagian tersedia | weighted experiment script, not active production artifact by default |
| weighted sampler | belum tersedia | no sampler implementation found |
| early stopping | sebagian tersedia | not confirmed in base script artifact; no strong evidence in report |
| multi-seed experiments | sebagian tersedia | docs mention 3-seed comparisons; no general registry enforcement found |
| config-driven training | belum tersedia | constants hardcoded in scripts |
| experiment registry | sebagian tersedia | JSON/TXT artifacts exist; no formal registry schema for sentiment |
| test checksum | belum tersedia | checksum computed for report; stored lock file not found |
| prediction export | sebagian tersedia | evaluation JSON reports predictions metrics, not full prediction row export confirmed |
| error analysis | sebagian tersedia | manual label audit command flags high-confidence mismatches |
| duplicate detection | sebagian tersedia | this report measured duplicates; no enforced training guard found |
| group-aware split | belum tersedia | random stratified by label only |

## 9. Database integration

- **Database engine**: `.env.example` sets `DB_CONNECTION=mysql`; runtime attempted MySQL `127.0.0.1:3306` and read succeeded after escalation. `config/database.php` default fallback is sqlite if env absent.
- **ORM/query layer**: Laravel Eloquent (`NewsArticle`, `SentimentManualLabel`) and Query Builder.
- **Schema/model files**: `app/Models/NewsArticle.php`, `app/Models/SentimentManualLabel.php`, migrations listed below.
- **Sentiment migrations**:
  - `database/migrations/2026_04_06_021517_create_news_articles_table.php` creates base article/sentiment fields.
  - `database/migrations/2026_04_07_000001_add_relevance_fields_to_news_articles.php` adds relevance/source metadata.
  - `database/migrations/2026_04_12_000000_add_ml_sentiment_to_news_articles.php` adds ML/rule fields.
  - `database/migrations/2026_04_12_000002_add_quality_fields_to_news_articles.php` adds quality fields.
  - `database/migrations/2026_04_13_000003_add_ml_sentiment_columns_to_news_articles.php` adds ML probabilities defensively.
  - `database/migrations/2026_07_07_000001_create_sentiment_manual_labels_table.php` creates manual labels.
  - `database/migrations/2026_07_22_000001_add_sample_method_to_sentiment_manual_labels.php` adds sample method.
- **Article/manual relationship**: `NewsArticle::manualLabels()` hasMany `SentimentManualLabel`; `SentimentManualLabel::article()` belongsTo `NewsArticle`.
- **Training data query**: `SentimentManualLabel::with('article')`, optional include/exclude by `sample_method`, then JSONL export.
- **Inference writes**: `NewsAggregationService` upserts article and writes `sentiment_label`, `sentiment_score`, `sentiment_confidence`, `sentiment_method`, `ml_*`, `rule_*`, `ml_rule_agree`, `sentiment_meta`, `analyzed_at`.
- **Transactions**: no explicit DB transaction found around sentiment upsert/reanalysis.
- **Schema changes needed now**: none required to improve model artifact if format stays compatible with existing columns.
- **Schema changes avoidable**: yes, if new model preserves labels/prob fields and writes same JSON response contract.
- **Compatibility constraints**: must preserve labels `positive|neutral|negative`, probabilities by label, method strings expected by UI/tests, and existing `news_articles` columns.

## 10. Runtime and commands

### Runtime/dependencies

- **PHP**: local CLI 8.5.5; project requires `php:^8.3`.
- **Laravel**: `laravel/framework:^13.0`.
- **Python**: system 3.9.6; sentiment venv at `quant/.venv-sentiment`.
- **Python ML dependencies in venv**: torch 2.2.2, transformers 4.57.6, fastapi 0.128.8, uvicorn 0.39.0, pydantic 2.13.4, datasets 4.5.0, scikit-learn 1.6.1, numpy 1.26.4.
- **GPU/CUDA**: local `torch.cuda.is_available()` returned false.
- **Node**: local v24.9.0; README says Node 18+.
- **Formatter/linter**: Laravel Pint available through `laravel/pint`; no JS lint script found in `package.json`.
- **Test frameworks**: PHPUnit/Pest-style Laravel tests via `php artisan test`; pytest-style Python tests in `quant/test_*.py`.

### Env variable names

Found names: `SENTIMENT_ENGINE`, `PYTHON_SENTIMENT_ENDPOINT`, `PYTHON_SENTIMENT_TIMEOUT`, `HUGGINGFACE_API_TOKEN`, `SENTIMENT_MODEL_DIR`, `NEWS_PROVIDER`, `NEWS_API_KEY`, `NEWS_API_BASE_URL`, `NEWS_API_LANGUAGE`, `NEWS_API_TIMEOUT`, `NEWS_API_USER_AGENT`, `NEWS_RSS_SOURCES`, `NEWS_RSS_TIMEOUT`, `NEWS_RSS_USER_AGENT`, `NEWS_RELEVANCE_THRESHOLD`, `NEWS_RELEVANCE_HIGH`, `NEWS_GOOGLE_RSS_*`, `GNEWS_API_KEY`, `GNEWS_BASE_URL`, `GNEWS_LANGUAGE`, `GNEWS_COUNTRY`, `GNEWS_TIMEOUT`, `DB_CONNECTION`, `DB_HOST`, `DB_PORT`, `DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD`.

No secret values printed.

### Commands

- **Install PHP**: `composer install`.
- **Install JS**: `npm install`.
- **Build assets**: `npm run build`.
- **Dev assets**: `npm run dev`.
- **Laravel app**: `php artisan serve`.
- **Queue**: `php artisan queue:work`.
- **Scheduler dev**: `php artisan schedule:work`.
- **Tests**: `php artisan test`; Composer script `composer test` clears config then runs artisan test.
- **Formatter**: likely `vendor/bin/pint` from dependency; no command run.
- **Fetch news**: `php artisan news:fetch --limit=20`, optional `--stock`, `--provider`, `--debug`.
- **Fetch OJK**: `php artisan news:fetch-ojk --limit=50`.
- **Analyze missing**: `php artisan news:analyze`.
- **Reanalyze**: `php artisan sentiment:reanalyze --include-global`, optional `--force`, `--limit`.
- **Full rescore**: `php artisan news:rescore-sentiment`.
- **Export finetune dataset**: `php artisan sentiment:export-finetune-dataset --output-dir=storage/app/sentiment_finetune --train-ratio=0.7 --val-ratio=0.15 --seed=42`.
- **Train base sentiment**: `quant/.venv-sentiment/bin/python quant/finetune_sentiment_model.py`.
- **Train weighted experiment**: `quant/.venv-sentiment/bin/python quant/finetune_sentiment_weighted_experiment.py`.
- **Evaluate sentiment models**: `quant/.venv-sentiment/bin/python quant/evaluate_sentiment_models.py`.
- **Serve sentiment API**: `./start_sentiment_api.sh` or `quant/.venv-sentiment/bin/python3 -m uvicorn quant.sentiment_api:app --host 127.0.0.1 --port 8002 --reload`.
- **Inference endpoint**: POST `/sentiment` to `PYTHON_SENTIMENT_ENDPOINT` with JSON `{"inputs":"..."}`.

## 11. Existing tests

Relevant tests found:

- `tests/Unit/PythonApiSentimentAnalyzerTest.php`
- `tests/Unit/SentimentAnalysisServiceTest.php`
- `tests/Unit/SentimentAnalyzerTest.php`
- `tests/Unit/SentimentSummaryServiceTest.php`
- `tests/Unit/NewsAggregationServiceTest.php`
- `tests/Unit/NewsArticlesSchemaTest.php`
- `tests/Feature/SentimentValidationTest.php`
- `tests/Feature/ReanalyzeSentimentCommandTest.php`
- `tests/Feature/AuditSentimentManualLabelsCommandTest.php`
- `tests/Feature/ExportSentimentActiveLearningCandidatesCommandTest.php`
- `quant/test_*.py` contains many quant/prediction tests; no dedicated `test_sentiment_api.py` found by filename list.

Tests were not run because task is audit/report only and no production code changed.

## 12. Missing capabilities

- Stored checksum verification before sentiment evaluation is not found.
- Group-aware duplicate-safe split is not found.
- Formal experiment registry with commit/date/command/env/artifact hash is not found for sentiment.
- Confusion matrix storage for 58.16% report is not found.
- Exact historical command and commit for 58.16% experiment are not found.
- Batch inference endpoint is not found.
- Explicit device selection for sentiment API is not found.
- Production-safe no-`--reload` sentiment service config is not found; current `start_sentiment_api.sh` uses `--reload`.
- Schema transaction around sentiment upsert/reanalysis is not found.

## 13. Risks

| Risk | Level | Reason | Mitigation |
|---|---|---|---|
| Label mapping mismatch | tinggi | production assumes `positive=0`, `neutral=1`, `negative=2` through config/prob lookup | assert `id2label/label2id` before serving; add startup check |
| Artifact format change | tinggi | FastAPI loads HF directory with tokenizer/model files | preserve HF `save_pretrained` layout; smoke-test `/health` and `/sentiment` |
| Tokenizer change | tinggi | changing tokenizer changes input distribution and logits | pin tokenizer artifact; record base checkpoint and tokenizer hash |
| Input text change | tinggi | training export replicates production input; changing fields breaks comparability | keep `buildProductionInputText()` and `PythonApiSentimentAnalyzer` aligned; add test |
| DB compatibility | tinggi | UI/pipeline expects existing `news_articles` columns | avoid schema change; preserve response keys and labels |
| Deployment compatibility | sedang | launchd plist calls `start_sentiment_api.sh`; port 8002/endpoint must match env | document deployment env; healthcheck before switching |
| Latency | sedang | per-article HTTP single inference can be slow | benchmark before rollout; optional batching later |
| Memory | sedang | RoBERTa model in local service uses RAM | measure process RSS; avoid loading multiple candidates in production |
| CPU/GPU requirements | sedang | local CUDA false; serving CPU-only | set expected latency target; optimize only if measured |
| Backward compatibility | tinggi | resolver policy and method strings feed downstream analytics | keep method strings or add compatibility mapping |
| Test leakage | tinggi | current split random stratified; test artifact changed over time | freeze official tests with checksum and no tuning rule |
| Duplicate leakage | sedang | duplicate text exists in train/val and representative test | add duplicate/group-aware split before next claim |
| Data privacy | sedang | article text exported to JSONL | avoid committing sensitive/full text beyond needed; restrict artifact access |
| Reproducibility | tinggi | old 58.16 report lacks date/commit/command/checksum | add experiment metadata and checksum validation before next run |

## 14. Unverified assumptions

- Whether `.env` currently points `PYTHON_SENTIMENT_ENDPOINT` to `http://127.0.0.1:8002/sentiment` was not printed; only active config names and code defaults verified.
- Whether launchd service is currently loaded/running was not checked.
- Whether production uses `indobert_finetuned_v1` at this moment depends on `SENTIMENT_MODEL_DIR`; code default says yes, env could override.
- Whether 58.16% was generated on commit `6689596...` is unverified; artifact lacks commit.
- Whether old 120-row test JSONL still exists under another path is unverified; not found in inspected active paths.
- Whether manual labels are all human-generated is inferred from controller/storage design, but annotator process identity is not encoded beyond `user_id`.
- Whether test set was ever used for tuning cannot be proven from repository alone.

## 15. Questions for the project owner

1. Mana test set resmi untuk gating berikutnya: old 120-row hard-case, current 148-row `storage/app/sentiment_finetune/test.jsonl`, atau R5b 153-row `legacy_hard_case_test.jsonl`?
2. Apakah skor 58.16% dianggap benchmark final produksi, atau hanya hasil awal dari split lama?
3. Siapa/role apa yang membuat manual labels, dan apakah semua label boleh dianggap human ground truth?
4. Apakah artikel ambigu/noisy boleh dikeluarkan dari training/evaluation, atau harus tetap dilabel `neutral`?
5. Artifact mana yang benar-benar berjalan di produksi saat ini jika `SENTIMENT_MODEL_DIR` override ada?
6. Apakah database produksi boleh disentuh untuk backfill setelah model baru lolos, atau hanya artifact service yang boleh diganti?
7. Target minimum model berikutnya apa: macro-F1 hard-case, macro-F1 representative, per-class positive/negative F1, atau business metric downstream?
8. Batas latency per artikel untuk ingestion dan UI berapa?
9. Batas compute eksperimen: CPU-only, MPS, GPU eksternal, atau cloud?
10. Apakah duplicate/group-aware split wajib sebelum klaim metrik berikutnya?

## 16. Recommended implementation order

1. **Freeze evaluation contract**: pilih test resmi, tulis checksum, dan verifikasi checksum sebelum evaluasi.
2. **Add metadata-only guards**: startup check label mapping, model dir, tokenizer/model config, no schema change.
3. **Add duplicate/group leakage audit**: read-only report untuk train/val/test sebelum training baru.
4. **Align input text tests**: test bahwa export training text sama dengan production Python input construction.
5. **Run small reproducibility smoke**: evaluate existing production artifact on official locked test only after owner confirms test set.
6. **Only then train candidate**: candidate directory baru, no overwrite production artifact, compare against frozen benchmark.
7. **Promote only after gate**: switch `SENTIMENT_MODEL_DIR` or artifact symlink after metrics and owner approval.
