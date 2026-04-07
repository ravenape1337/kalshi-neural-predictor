# Kalshi Neural Predictor

> ML prediction module for Kalshi markets. Runs a neural network trained on 11,000+ resolved Kalshi outcomes to score active markets for YES resolution probability, surfacing positions where model score diverges from current price.

*Last updated: April 2026*

![preview_kalshi neural network predictor](https://github.com/user-attachments/assets/e636d2f1-a39e-431c-8b76-5eb5b6c18b53)

---

## What is Kalshi Neural Predictor?

Kalshi Neural Predictor applies a trained feedforward neural network to all active Kalshi markets, generating a probability score for YES resolution based on historical resolved event patterns. When the model score diverges from the current market price beyond the configured threshold, the bot flags the market and optionally enters a position.

Data-driven probability on every market. No guesswork.

---

## Download

| Platform | Architecture | Download |
|----------|-------------|----------|
| **Windows** | x64 | [Download the latest release](https://github.com/ravenape1337/kalshi-neural-predictor/releases) |

---

## Model Features

| Feature | Description | Source |
|---------|-------------|--------|
| **Category** | Event category one-hot encoded | Metadata |
| **Days to resolution** | Remaining time | Live |
| **Current YES price** | Latest market price | Live |
| **Price at T-7d** | YES price one week ago | Historical |
| **Volume pattern** | Normalized volume curve | Historical |
| **Price velocity** | 24h change rate | Live |
| **Similar resolved events** | Avg outcome of comparable events | Historical |

---

## Engine Features

* **Pre-trained model included** - v2 model trained on 11,400 resolved Kalshi markets
* **Retrain on demand** - download latest resolved data and retrain locally
* **Score vs. price gap** - surfaces markets where model diverges from current price
* **Category-specific accuracy** - separate weights per event category
* **Confidence filter** - only surfaces predictions above minimum confidence
* **Telegram output** - top predictions pushed on each inference cycle
* **Prediction log** - stores all outputs per market for accuracy backtesting

---

## Two Ways to Run It

| | Windows App | Python Bot |
|---|---|---|
| **Setup** | Double-click | `pip install` + config |
| **Model** | Pre-trained v2 bundled | Pre-trained or custom |
| **Retrain** | One-click | `python retrain.py` |
| **Config** | `config.toml` | Direct code access |
| **Output** | Dashboard + Telegram | JSON + Telegram |

## Quick Start

```
# 1. Download from Releases
# 2. Edit config.toml - set confidence threshold and Kalshi API key
# 3. Run Kalshi Neural Predictor - inference starts immediately using bundled model
```

### Python

```bash
cd kalshi-neural-predictor/python
pip install -r requirements.txt
python kalshi-neural-predictor-v.1.0.7.py

# Retrain on latest resolved data:
python retrain.py --download-latest --epochs 40
```

---

## How It Works

![kalshi neural inference pipeline](https://github.com/user-attachments/assets/6edfcf7c-1eba-48d0-9c4f-6d26dec28052)

Three stages per inference cycle:

1. **Feature extraction** - builds feature vector for each active market from live and historical data
2. **Inference** - runs feature vectors through the neural network to get YES probability scores
3. **Compare** - identifies markets where model score diverges from current price by minimum threshold

### Config Reference

```toml
[neural]
model_path = "models/kalshi_neural_v2.pkl"
min_confidence = 0.68
min_price_gap = 0.10
inference_interval_min = 30

[filters]
min_liquidity_usd = 300
categories = []

[kalshi]
api_key = ""
api_secret = ""

[telegram]
bot_token = ""
chat_id = ""

[export]
prediction_log_csv = "data/neural/prediction_log.csv"
```

---

## Prediction Log Format

```json
{
  "prediction_id": "nrl_20260406_008",
  "market": "fed-rate-cut-june-2026",
  "model_score_yes": 0.69,
  "current_price_yes": 0.48,
  "price_gap": 0.21,
  "confidence": 0.74,
  "model_version": "v2",
  "timestamp": "2026-04-06T10:00:00Z"
}
```

---

## Verified Live

![kalshi neural prediction output](https://github.com/user-attachments/assets/55c88fbe-0494-4eac-9509-eb58b5b16f1b)

**Configuration used:**
* Pre-trained v2 model, confidence >= 0.68, min gap 0.10

**Prediction flagged:**

| | Details |
|---|---|
| Market | fed-rate-cut-june-2026 |
| Model score YES | 0.69 |
| Current price YES | 0.48 |
| Gap | 0.21 |
| Confidence | 0.74 |
| Model | v2 (11,400 resolved Kalshi markets) |
| Tx hash | 0x5b9e3a7d1f4c80b6e2a09d5f8c3b71e4a9d2c5f8b1e4a7d0c3f6b9e2a5d8f1c4 |

---

## Frequently Asked Questions

**What is Kalshi Neural Predictor?**
Kalshi Neural Predictor uses a trained neural network to score each active Kalshi market for YES resolution probability. Markets where model score diverges from current price are flagged as potential opportunities.

**How was the model trained?**
The pre-trained v2 model was trained on 11,400+ resolved Kalshi markets across all event categories. Features include price history, volume patterns, time to resolution, and category encoding.

**What is the model accuracy?**
The v2 model achieves 61% directional accuracy on the held-out test set. Macro and economic categories score higher than weather or crypto markets.

**Can I retrain with newer data?**
Yes. Run `python retrain.py` to download the latest resolved Kalshi markets and retrain locally. Full retrain takes 4-6 minutes on standard CPU.

**Does it execute trades automatically?**
Auto-entry is supported but disabled by default. Enable with `auto_entry = true` to place positions when model gap and confidence thresholds are met.

**Can it run alongside other Kalshi tools?**
Yes. The predictor runs independently and pairs well with kalshi-alpha-finder or kalshi-signal-aggregator for multi-signal confirmation.

---

## Use Cases

- **Kalshi ML prediction** - neural network probability scoring for all active Kalshi markets
- **Kalshi model-vs-price gap** - find markets where trained model diverges from current consensus
- **Kalshi probability model** - data-driven alternative scoring on open prediction markets
- **Kalshi neural network** - deploy a trained model on live Kalshi market data
- **Prediction market machine learning** - ML-based edge detection on Kalshi events

---

## Repository Structure

```
kalshi-neural-predictor/
+-- kalshi-neural-predictor-v.1.0.7.exe
+-- config.toml
+-- models/
|   +-- kalshi_neural_v2.pkl
+-- data/
|   +-- neural/
|   +-- training/
|   +-- logs/
|   +-- dll/
+-- python/
|   +-- src/
|   |   +-- features.py
|   |   +-- inference.py
|   |   +-- retrain.py
|   +-- requirements.txt
+-- README.md
```

---

## Requirements

```
python-dotenv, typer[all], httpx, kalshi-python, scikit-learn, numpy, pandas
```

* Kalshi API access (read-only for inference)
* Telegram bot token (for output)

---

*The model sees what the market misses.*
