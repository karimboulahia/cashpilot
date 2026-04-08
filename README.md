# 🚀 CashPilot — Copilote Financier Conversationnel

CashPilot est un moteur de décision financière personnalisé sur Telegram. Il aide les utilisateurs à suivre leur patrimoine, enregistrer leurs dépenses, et prendre des décisions d'achat éclairées.

**Ce n'est PAS un simple budget tracker.** C'est un copilote qui répond à la question : *"Est-ce que je peux acheter ça ?"*

## ✨ Fonctionnalités V1

- 🧑‍💼 **Onboarding conversationnel** — profil financier en 2 minutes
- 💰 **Suivi multi-comptes** — banque, épargne, crypto, cash, PayPal...
- 📊 **Tracking des dépenses** — "25 resto" suffit
- 🧠 **Moteur de décision d'achat** — YES / NO / WAIT / CONDITIONAL
- 📋 **Résumé financier** — patrimoine, matelas de sécurité, santé globale
- 🤖 **Bot Telegram** — interface conversationnelle naturelle
- 🔗 **API REST** — intégration possible avec d'autres outils

## 🏗️ Architecture

```
app/
├── main.py                    # FastAPI entry point
├── core/                      # Config, logging, security
├── db/
│   ├── base.py               # SQLAlchemy Base + TimestampMixin
│   ├── session.py            # Async session factory
│   └── models/               # 6 ORM models
├── schemas/                   # Pydantic request/response models
├── services/
│   ├── decision_engine.py    # ⭐ Core business rules (deterministic)
│   ├── parser_service.py     # Expense message parser
│   ├── llm_service.py        # OpenAI integration (NLU only)
│   ├── onboarding_service.py # Step-by-step onboarding
│   ├── telegram_service.py   # Message orchestrator
│   ├── account_service.py    # Account CRUD
│   ├── transaction_service.py # Transaction CRUD + analytics
│   ├── profile_service.py    # User/profile CRUD
│   └── reporting_service.py  # Financial summary + health
├── api/routes/               # REST endpoints
├── bot/                      # Telegram bot (polling mode)
└── prompts/                  # LLM prompt templates
```

## 🧠 Moteur de Décision

Le moteur est **100% déterministe** — le LLM ne prend jamais la décision.

### Règles métier
| # | Règle | Résultat |
|---|-------|----------|
| 1 | Prix > liquidité disponible | **NO** |
| 2 | Casse le matelas de sécurité + revenu instable | **NO** |
| 3 | Casse le matelas + revenu stable + non essentiel | **WAIT** |
| 4 | Revenu instable + confort + >40% épargne | **NO** |
| 5 | Coûts récurrents > 50% du reste à vivre | **NO** |
| 6 | Essentiel mais > 30% épargne | **CONDITIONAL** |
| 7 | Compromet un objectif actif | **WAIT** |
| 8 | Tout OK | **YES** |

### Score composite (0-100)
- Stabilité du revenu (0-25)
- Sécurité post-achat (0-25)
- Consommation de l'épargne (0-25)
- Charge récurrente (0-15)
- Discipline de dépense (0-10)

## 📦 Installation

### Prérequis
- Python 3.12+
- PostgreSQL 14+ (ou Docker)
- Compte Telegram Bot ([@BotFather](https://t.me/BotFather))
- Clé API OpenAI

### Setup local

```bash
# Cloner le repo
git clone <repo-url> cashpilot
cd cashpilot

# Environnement virtuel
python -m venv venv
source venv/bin/activate  # macOS/Linux

# Installer les dépendances
pip install -r requirements.txt

# Copier et configurer les variables d'environnement
cp .env.example .env
# Éditer .env avec tes clés
```

### Variables d'environnement

| Variable | Description | Exemple |
|----------|-------------|---------|
| `DATABASE_URL` | URL PostgreSQL async | `postgresql+asyncpg://cashpilot:cashpilot@localhost:5432/cashpilot` |
| `TELEGRAM_BOT_TOKEN` | Token du bot Telegram | `123456:ABC-DEF...` |
| `TELEGRAM_WEBHOOK_URL` | URL du webhook (prod) | `https://app.render.com/api/v1/telegram/webhook` |
| `TELEGRAM_WEBHOOK_SECRET` | Secret pour vérifier les webhooks | `random-secret` |
| `OPENAI_API_KEY` | Clé API OpenAI | `sk-...` |
| `OPENAI_MODEL` | Modèle à utiliser | `gpt-4o-mini` |
| `API_KEY` | Clé API pour les endpoints REST | `your-secret-key` |

## 🐳 Docker

### Démarrage rapide

```bash
docker-compose up -d
```

Cela lance PostgreSQL + l'app sur `http://localhost:8000`.

### Commandes utiles

```bash
# Voir les logs
docker-compose logs -f app

# Reconstruire l'image
docker-compose build

# Arrêter
docker-compose down

# Reset complet (supprime les données)
docker-compose down -v
```

## 🗃️ Base de données

### Lancer les migrations

```bash
# Appliquer toutes les migrations
alembic upgrade head

# Voir le statut
alembic current

# Créer une nouvelle migration
alembic revision --autogenerate -m "description"
```

### Tables
- `users` — Identité Telegram
- `financial_profiles` — Profil financier complet
- `accounts` — Comptes (banque, épargne, crypto...)
- `transactions` — Dépenses et revenus
- `goals` — Objectifs financiers
- `purchase_decisions` — Historique des décisions

## 🚀 Lancement

### API (mode développement)

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

L'API sera disponible sur `http://localhost:8000`.
Swagger UI : `http://localhost:8000/docs`

### Bot Telegram

#### Mode Polling (développement)

```bash
python -m app.bot.handlers
```

#### Mode Webhook (production)

L'app configure automatiquement le webhook au démarrage si `TELEGRAM_WEBHOOK_URL` est défini dans `.env`.

## 🧪 Tests

```bash
# Tous les tests
python -m pytest tests/ -v

# Tests du moteur de décision uniquement
python -m pytest tests/test_decision_engine.py -v

# Avec couverture
python -m pytest tests/ --cov=app --cov-report=html
```

## 🔌 API REST

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/api/v1/health` | Health check |
| `POST` | `/api/v1/users` | Créer un utilisateur |
| `GET` | `/api/v1/users/{id}` | Détails utilisateur |
| `POST` | `/api/v1/accounts?user_id={id}` | Ajouter un compte |
| `GET` | `/api/v1/accounts/user/{id}` | Comptes d'un utilisateur |
| `POST` | `/api/v1/transactions?user_id={id}` | Ajouter une transaction |
| `GET` | `/api/v1/transactions/user/{id}` | Transactions d'un utilisateur |
| `POST` | `/api/v1/goals?user_id={id}` | Ajouter un objectif |
| `GET` | `/api/v1/goals/user/{id}` | Objectifs d'un utilisateur |
| `POST` | `/api/v1/decisions/evaluate?user_id={id}` | Évaluer un achat |
| `POST` | `/api/v1/telegram/webhook` | Webhook Telegram |

## 🤖 Commandes Telegram

| Commande | Description |
|----------|-------------|
| `/start` | Démarrer l'onboarding |
| `/help` | Aide et commandes |
| `/summary` | Résumé financier |
| `/accounts` | Voir tes comptes |
| `/add_account` | Ajouter un compte |
| `/goals` | Voir tes objectifs |
| `/canibuy` | Demander un avis d'achat |
| `/profile` | Ton profil financier |
| `/health` | Santé financière |

### Exemples d'usage

```
25 resto              → Enregistre 25€ en restaurant
18 uber               → Enregistre 18€ en transport
45 courses            → Enregistre 45€ en alimentation
+2500 salaire         → Enregistre un revenu de 2500€

Est-ce que je peux acheter un iPhone à 1200€ ?
→ Le moteur analyse et répond YES/NO/WAIT/CONDITIONAL
```

## 🌐 Déploiement

### Render + Supabase

#### 1. Base de données — Supabase

1. Créer un projet sur [supabase.com](https://supabase.com)
2. Aller dans Settings → Database → Connection string
3. Copier l'URL de connexion et la convertir :
   - Remplacer `postgresql://` par `postgresql+asyncpg://`
   - Utiliser le format : `postgresql+asyncpg://user:password@host:port/dbname`
4. L'utiliser comme `DATABASE_URL`

#### 2. App — Render

1. Créer un Web Service sur [render.com](https://render.com)
2. Connecter le repo GitHub
3. Configuration :
   - **Runtime** : Python 3
   - **Build Command** : `pip install -r requirements.txt`
   - **Start Command** : `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Ajouter les variables d'environnement dans le dashboard Render
5. Le webhook Telegram sera automatiquement configuré au démarrage

#### 3. Migrations en production

```bash
# Depuis votre machine locale avec DATABASE_URL pointant vers Supabase
DATABASE_URL="postgresql+asyncpg://..." alembic upgrade head
```

## 📄 Licence

MIT
