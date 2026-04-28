# Supply Chain Design - Streamlit

Application Streamlit simple pour resoudre un probleme de Supply Chain Design avec OR-Tools.

L'application permet de :

- charger un fichier Excel de couts par site et region ;
- charger un fichier Excel de capacites par site ;
- saisir une demande de reference par region ;
- definir un deuxieme scenario par pourcentage d'evolution ;
- choisir si la fermeture des sites est autorisee ;
- lancer l'optimisation ;
- comparer les resultats des deux scenarios.

Le point d'entree de l'application est :

```bash
app_v3.py
```

Le solveur est dans :

```bash
optimizer_v3.py
```

## Format des fichiers Excel

### 1. Fichier des couts

Le fichier Excel des couts doit contenir :

- une colonne `Site` ;
- une colonne `Cout fixe` ;
- une colonne par region.

Exemple :

```text
Site, Cout fixe, PACA, BRETAGNE, CENTRE, Nouvelle Aquitaine, AURA, OCCITANIE
RENNES, 7650, 1675, 400, 685, 1630, 1160, 2800
BORDEAUX, 3500, 1460, 1940, 970, 100, 495, 1200
```

### 2. Fichier des capacites

Le fichier Excel des capacites doit contenir :

```text
Site, Capacite
```

Exemple :

```text
Site, Capacite
RENNES, 18
BORDEAUX, 24
```

La colonne `Capacite` peut aussi etre ecrite `capacite`.

## Lancer en local

Depuis le dossier du projet :

```bash
streamlit run app_v3.py
```

Ou avec l'environnement virtuel local du projet :

```bash
.venv/bin/python -m streamlit run app_v3.py
```

## Deploiement sur Streamlit Community Cloud

1. Creer un depot GitHub contenant au minimum :

```text
app_v3.py
optimizer_v3.py
requirements.txt
README.md
```

2. Aller sur Streamlit Community Cloud :

```text
https://share.streamlit.io
```

3. Cliquer sur `New app`.

4. Selectionner le depot GitHub.

5. Indiquer comme fichier principal :

```text
app_v3.py
```

6. Lancer le deploiement.

Streamlit installera automatiquement les dependances listees dans `requirements.txt`.

## Remarques

- Le modele mathematique est implemente dans `optimizer_v3.py`.
- L'interface utilisateur est implemente dans `app_v3.py`.
- Aucune base de donnees n'est utilisee.
- Les fichiers Excel sont charges par l'utilisateur dans l'application.
