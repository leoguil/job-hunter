# POC — Évaluation de nouvelles sources de scraping

Ce module teste la faisabilité d'intégrer de nouveaux sites d'emploi.
Rien ici n'est intégré dans l'app principale.

## Architecture du POC

```
poc/
  evaluator.py        # Harnais de test commun (mesure qualité/stabilité)
  apec.py             # APEC (cadres, API non officielle)
  francetravail.py    # France Travail (ex Pôle Emploi) — API publique OAuth2
  cadremploi.py       # Cadremploi — scraping HTML
  remoteok.py         # RemoteOK — flux RSS public
  README.md           # Ce fichier
```

## Comment lancer un test

```bash
cd backend/scrapers/poc
python apec.py              # teste APEC
python francetravail.py     # teste France Travail
python remoteok.py          # teste RemoteOK (RSS)
python evaluator.py         # résumé tous les sites
```

---

## Grille d'évaluation

| Critère               | Poids | Description                                              |
|-----------------------|-------|----------------------------------------------------------|
| Scrapable sans auth   | 30 %  | Fonctionne sans token / inscription                      |
| Qualité des données   | 25 %  | Titre, entreprise, localisation, date, salaire présents  |
| Stabilité             | 20 %  | API/structure stable dans le temps (pas de JS dynamique) |
| Richesse              | 15 %  | Description, secteur, type de contrat disponibles        |
| Difficulté technique  | 10 %  | Facilité d'intégration (API > RSS > HTML)                |

Score total sur 100. Seuil d'intégration recommandé : **≥ 65 points**.

---

## Sites évalués — Classement priorisé

| Priorité | Site            | Méthode        | Score estimé | Statut POC   |
|----------|-----------------|----------------|--------------|--------------|
| 1        | RemoteOK        | RSS public     | ~85          | ✅ À tester   |
| 2        | France Travail  | API OAuth2     | ~80          | ✅ À tester   |
| 3        | APEC            | API privée     | ~70          | ✅ À tester   |
| 4        | Cadremploi      | HTML scraping  | ~55          | ⚠️ Risqué     |
| 5        | Indeed          | HTML scraping  | ~25          | ❌ Anti-bot   |
| 6        | LinkedIn        | HTML scraping  | ~10          | ❌ Bloqué     |

### Détail par site

#### 1. RemoteOK (priorité haute)
- **Méthode** : RSS public `https://remoteok.com/remote-jobs.rss`
- **Auth** : Aucune
- **Qualité** : Titre, entreprise, date, tags (tech, design, etc.)
- **Limite** : Jobs remote uniquement, orienté tech
- **Difficulté** : Très faible — parsing RSS standard

#### 2. France Travail / ex Pôle Emploi (priorité haute)
- **Méthode** : API REST officielle `https://api.francetravail.io`
- **Auth** : OAuth2 (client_id + client_secret — inscription gratuite)
- **Qualité** : Excellente — données normalisées, salaires, secteur ROME
- **Limite** : Nécessite inscription sur `francetravail.io/partenaire`
- **Difficulté** : Moyenne — OAuth2 + format ROME à mapper

#### 3. APEC (priorité moyenne)
- **Méthode** : API Algolia non officielle (identique à WTTJ)
- **Auth** : Clé Algolia publique extraite du HTML
- **Qualité** : Bonne — cadres et managers, données structurées
- **Limite** : API privée susceptible de changer
- **Difficulté** : Faible — même pattern que WTTJ

#### 4. Cadremploi (priorité basse)
- **Méthode** : Scraping HTML `https://www.cadremploi.fr`
- **Auth** : Aucune mais User-Agent requis
- **Qualité** : Moyenne — titre, entreprise, localisation, peu de salaires
- **Limite** : Structure HTML instable, risque de blocage
- **Difficulté** : Moyenne

#### 5. Indeed — NE PAS INTÉGRER
- Anti-bot agressif (Cloudflare + JS challenge)
- CGU interdit le scraping

#### 6. LinkedIn — NE PAS INTÉGRER
- Auth obligatoire + rate limiting très strict
- Scraping interdit par CGU
