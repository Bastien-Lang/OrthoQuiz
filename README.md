# OrthoQuiz

Petit jeu d'entraînement à l'orthographe pour Windows (niveau primaire / collège).
Python + Tkinter, aucune dépendance : l'exe fait une dizaine de Mo et se lance d'un double-clic.

- **11 thèmes**, 24 questions chacun (264 au total) : a/à, et/est, ou/où, on/ont·son/sont,
  ce/se·ces/ses·c'est/s'est, leur/leurs, é/er/ez, participe passé, conjugaison, orthographe des mots,
  pluriels et accords.
- **QCM** pour choisir entre des homophones ; **saisie au clavier** quand il faut vraiment écrire le mot
  (conjugaison, orthographe, accords). Un bouton « Indice » donne la première lettre (XP divisée par 2).
- **Progression** : chaque thème a 3 niveaux. Il faut **80 % de bonnes réponses** pour débloquer le suivant
  (étoiles ★ sur la carte du thème). XP, niveaux de joueur (Apprenti → Légende), séries, jours consécutifs
  et 12 succès. Les questions ratées reviennent plus souvent ; le bouton « Revoir mes erreurs » les rejoue.
- La progression est enregistrée dans `%APPDATA%\OrthoQuiz\progress.json`.

## Mise en place (une seule fois)

1. Crée un dépôt GitHub **public** (nécessaire pour les mises à jour automatiques des questions)
   et envoie-y tout ce dossier :
   ```
   git init
   git add .
   git commit -m "OrthoQuiz"
   git branch -M main
   git remote add origin https://github.com/TON-COMPTE/orthoquiz.git
   git push -u origin main
   ```
2. Onglet **Actions** du dépôt : le workflow « Compiler OrthoQuiz.exe » se lance tout seul
   (environ 2 minutes). À la fin, télécharge l'artefact **OrthoQuiz-windows** : il contient `OrthoQuiz.exe`
   et un zip prêt à envoyer.
3. Pour avoir un lien de téléchargement permanent, crée un tag : `git tag v1.0 && git push --tags`.
   L'exe apparaît alors dans l'onglet **Releases**.

## Pour ton ami

Il lance `OrthoQuiz.exe` par double-clic. Rien à installer.

- Au tout premier lancement, Windows peut afficher « Windows a protégé votre PC » (l'exe n'est pas signé) :
  cliquer sur **Informations complémentaires**, puis **Exécuter quand même**.
- Le démarrage prend 1 à 2 secondes (l'exe se décompresse en mémoire).
- Gmail refuse souvent les `.exe`, même dans un zip. Le plus simple : lui envoyer le lien de la Release GitHub,
  ou passer par un lien Drive / WeTransfer.

## Ajouter ou corriger des questions (sans renvoyer l'exe)

1. Modifie ou ajoute un fichier dans `questions/` (format ci-dessous) et **augmente le `version`** du thème.
2. Vérifie : `python tools/check_questions.py`
3. `git add . && git commit -m "Nouvelles questions" && git push`

Au prochain lancement (avec internet), le jeu compare ses fichiers avec ceux du dépôt, télécharge seulement
ceux qui ont changé et les range dans `%APPDATA%\OrthoQuiz\questions_updates`. Hors ligne, il utilise les
questions déjà présentes, sans message d'erreur. Un nouveau **thème** = un nouveau fichier `.json`.

Seules les modifications du **code** (`ortho/*.py`) demandent un nouvel exe : pousse un nouveau tag `v1.1`.

### Format d'un fichier de questions

(Les commentaires `//` ci-dessous sont là pour expliquer : ils sont interdits dans le vrai fichier JSON.)

```json
{
 "id": "a_a",                       // identifiant unique : minuscules, chiffres et _
 "title": "a / à",                  // titre du cahier
 "subtitle": "Verbe avoir ou préposition ?",
 "version": 1,                      // à augmenter à chaque modification
 "order": 10,                       // position dans le menu
 "rule": "Rappel affiché quand on se trompe.",
 "questions": [
  {"lvl":1, "q":"Léa ___ un chat.", "choices":["a","à"], "answer":"a", "why":"Explication (facultatif)"},
  {"lvl":2, "q":"Demain, je ___ (faire) un gâteau.", "answer":"ferai"},
  {"lvl":3, "q":"Écris le mot : ___ (savant qui étudie les étoiles)", "answer":["astronome"]}
 ]
}
```

- `lvl` : 1, 2 ou 3 (difficulté). Prévoir au moins 8 questions par niveau (un script le signale).
- Avec `choices` → QCM (2 à 6 choix, mélangés à chaque fois). Sans `choices` → saisie au clavier :
  la casse est ignorée mais **les accents comptent** (« Presque ! » s'affiche s'ils manquent).
- `___` marque le trou ; `answer` peut être une liste pour accepter plusieurs graphies.
- `why` est facultatif : sinon c'est la `rule` du thème qui s'affiche après une erreur.

## Lancer sans compiler (développement)

```
python main.py                                  # nécessite Python 3.10+ (Tkinter est inclus sous Windows)
python -m unittest discover -s tests -v         # tests
```

Compiler à la main (équivalent du workflow) :

```
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name OrthoQuiz --icon assets/icon.ico ^
  --add-data "questions;questions" --add-data "assets;assets" --add-data "config.json;." main.py
```

## Structure

```
main.py                  point d'entrée (journal d'erreurs dans %APPDATA%\OrthoQuiz\crash.log)
ortho/content.py         lecture et validation des JSON, correction des réponses
ortho/session.py         choix des questions, XP, séries
ortho/progress.py        niveaux, paliers par thème, sauvegarde
ortho/badges.py          succès
ortho/updater.py         mise à jour des questions via l'API GitHub
ortho/ui.py              interface (cahier Seyès, couvertures colorées, surligneur)
questions/*.json         les thèmes
tools/check_questions.py vérification avant commit
.github/workflows/       compilation automatique de l'exe
```
