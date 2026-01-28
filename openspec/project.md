# Project Context

## Purpose
MeshForge Runtime est le substrat fondamental pour forger des espaces de travail agentiques isolés et pilotés par événements. Il fournit les SDK, les rails de gouvernance et les primitives d'observabilité nécessaires pour exécuter des agents en toute sécurité. Il ne contient AUCUNE logique métier.

## Tech Stack
- **Langage :** Python 3.11+
- **Bibliothèques Clés :** Pydantic v2 (modèles), CloudEvents (concepts d'enveloppe), Structlog (observabilité)
- **Infrastructure :** NATS (Bus d'événements), PostgreSQL (Persistance/Artefacts)
- **Outils :** Poetry/UV, OpenSpec, Docker

## Project Conventions

### Code Style
- **Python-First :** Typage strict (`mypy` strict), `ruff` pour le linting/formatage.
- **Spec-Driven :** Tout changement doit commencer par une proposition OpenSpec. Pas de code sans spécification.
- **Isolation :** 1 Workspace = 1 Stack. Pas d'état partagé entre les tenants.

### Architecture Patterns
- **Event-Driven :** Toutes les interactions entre agents se font via des événements immuables.
- **Agentic :** Workers (sans état), Managers (supervision avec état), Gateways (entrée/sortie), Governors (garde-fous).
- **Gouvernance :** Journaux d'audit en ajout seul (append-only), validation bloquante des contrats.

### Testing Strategy
- **Unitaire :** Pytest pour la logique SDK.
- **Simulation :** Exécuteur de scénarios déterministe pour la vérification de la conformité.
- **Contrats :** Validation JSON Schema pour tous les événements et artefacts.

### Git Workflow
- **Séparation style Monorepo :** Runtime, Factory et Envs sont des dépôts séparés mais gérés de manière cohérente.
- **Branches :** `main` est prêt pour la production. Fonctionnalités via PRs liées aux IDs de changement OpenSpec.

## Domain Context
- **MeshForge :** L'usine/le framework.
- **Workspace :** Un déploiement isolé pour un tenant/cas d'usage spécifique (ex: Mealhome).
- **Artefact :** Logique/config versionnée (code, règles, prompts) gérée via un cycle de vie.
- **Enveloppe :** Wrapper d'événement standardisé avec suivi de corrélation/causalité.

## Important Constraints
- **Pas de Logique Métier dans le Runtime :** Le runtime sait seulement comment exécuter des agents, pas ce qu'ils font.
- **Déterminisme :** Les sorties de la Factory et les exécutions du Simulateur doivent être reproductibles.
- **Sécurité :** Les Garde-fous (Governors) peuvent bloquer toute action.

## External Dependencies
- **Fournisseurs LLM :** Accessibles via des passerelles standardisées (pas codées en dur dans le runtime).
- **Déploiement :** Docker Compose pour local/dev, K8s pour la production (futur).
