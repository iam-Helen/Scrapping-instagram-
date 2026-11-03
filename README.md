# Veille Instagram → Telegram

Chaque semaine, ce projet récupère les publications publiques des comptes et des hashtags de ta niche, repère celles qui marchent le mieux et t'envoie un rapport sur Telegram.

- **Aucun compte Instagram n'est utilisé** : c'est [Apify](https://apify.com) qui récupère les données publiques avec ses propres serveurs. Ton compte ne risque rien.
- **Ça tourne tout seul**, gratuitement, grâce à GitHub Actions (le lundi matin par défaut). Ton ordinateur n'a pas besoin d'être allumé.

## Ce que contient le rapport

- 🔥 **Contenus qui percent** : les publications qui font au moins 1,5 fois plus d'interactions que d'habitude pour leur compte. C'est le meilleur signal d'un sujet ou d'une accroche qui fonctionne.
- 🏆 **Plus d'interactions** : les publications les plus likées et commentées.
- 🎬 **Formats** : Reels, carrousels ou photos, avec la moyenne d'interactions de chacun.
- 🏷️ **Hashtags** utilisés par les meilleurs contenus.

Chaque exécution garde aussi un export **CSV** (lisible dans Excel) et JSON pendant 30 jours, dans l'onglet *Actions* de GitHub.

## Installation (environ 10 minutes, une seule fois)

### 1. Créer un compte Apify (gratuit)

1. Inscris-toi sur <https://console.apify.com/sign-up>. Aucune carte bancaire n'est demandée.
2. Copie ta clé d'API depuis <https://console.apify.com/settings/integrations>.

Le plan gratuit donne **5 $ de crédit par mois**. Quand ce crédit est épuisé, Apify s'arrête jusqu'au mois suivant : il n'y a jamais de facture surprise.

### 2. Créer le bot Telegram

1. Sur Telegram, écris à **@BotFather**, envoie `/newbot` et suis les instructions. Il te donne un **jeton**.
2. Envoie un message quelconque à ton nouveau bot, par exemple « salut ».
3. Récupère ton identifiant de conversation :
   ```bash
   pip install requests
   TELEGRAM_BOT_TOKEN=ton_jeton python telegram_chat_id.py
   ```

### 3. Ranger les clés dans GitHub, de façon privée

Dans le dépôt GitHub, va dans **Settings → Secrets and variables → Actions → New repository secret**, puis ajoute :

| Nom                  | Valeur                          |
|----------------------|---------------------------------|
| `APIFY_TOKEN`        | la clé d'API Apify              |
| `TELEGRAM_BOT_TOKEN` | le jeton donné par @BotFather   |
| `TELEGRAM_CHAT_ID`   | le numéro trouvé à l'étape 2    |

⚠️ Ne mets jamais ces clés dans un fichier du dépôt ni dans un message.

### 4. Choisir quoi surveiller

Modifie [`config.yaml`](config.yaml) : ajoute les comptes (le nom ou le lien du profil) et les hashtags de ta niche.

### 5. Tester

Dans l'onglet **Actions** de GitHub, ouvre **Veille Instagram**, clique sur **Run workflow**, et le rapport arrive sur Telegram quelques minutes plus tard.

## Coût

Avec l'Actor `apify/instagram-scraper`, Apify facture environ **0,0027 $ par publication récupérée** sur le plan gratuit (tarif de novembre 2026).

| Exemple                                         | Par exécution | Par mois (hebdo) |
|-------------------------------------------------|---------------|------------------|
| 15 comptes + 3 hashtags × 12 publications max   | ≈ 0,58 $ max  | ≈ 2,30 $         |

Le filtre « X derniers jours » réduit souvent le nombre réel de publications. Le plafond `budget_max_usd` du fichier `config.yaml` (1 $ par défaut) arrête Apify s'il est atteint. Une veille hebdomadaire de taille raisonnable tient dans le crédit gratuit.

## Utilisation en local (facultatif)

```bash
pip install -r requirements.txt
export APIFY_TOKEN=...                     # ne pas commiter
python veille.py --dry-run                 # affiche le rapport sans l'envoyer
python veille.py --fichier sorties/brut_….json --dry-run   # réanalyse sans payer
python -m pytest                           # tests
```

## Bon usage

- Le projet ne collecte que des **données publiques**. Utilise-les pour analyser les sujets, les formats et les accroches qui marchent, pas pour republier le contenu d'autres créateurs (droit d'auteur).
- **RGPD** : les commentaires ne sont pas exploités dans le rapport, et les exports sont supprimés automatiquement au bout de 30 jours.
