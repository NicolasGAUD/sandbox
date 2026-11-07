# Comment la photo est copiée sur le serveur

**Application :** CLIP urbex (branche `feature/photo-upload-app`)
**Date :** 25 octobre 2026

La photo passe par trois étapes. À aucun moment elle n'est recompressée : c'est le fichier d'origine, octet pour octet, avec ses données EXIF.

## 1. Le téléphone envoie la photo

Fichier `app/src/app/analysis.service.ts`, méthode `analyse` :

```
const form = new FormData();
form.append('photo', file, file.name);
const analysis = await firstValueFrom(this.http.post<Analysis>('/api/analyses', form));
```

Le fichier choisi, ou pris avec l'appareil photo, part tel quel dans une requête `multipart/form-data`, avec son nom d'origine.

## 2. Le serveur l'analyse, puis la met en attente

Fichier `server.py`, fonction `analyse` :

```
content = photo.file.read()                                   # octets bruts du fichier reçu
image = ImageOps.exif_transpose(Image.open(io.BytesIO(content))).convert("RGB")
results, details, _ = analyzer.analyse(image, all_details=True)   # analyse en mémoire

analysis_id = uuid.uuid4().hex
path = UPLOADS / f"{analysis_id}{suffix}"                     # uploads/<identifiant>.jpg
path.write_bytes(content)                                     # copie exacte du fichier reçu
exif = read_exif(content)
pending[analysis_id] = {"path": path, "name": file_name(exif["taken"], suffix)}
```

- L'analyse se fait sur une image décodée en mémoire, qui ne sert qu'à CLIP.
- Le fichier d'origine est écrit **après** l'analyse, dans `uploads/`, sous un nom unique (un UUID) pour éviter toute collision.
- Le serveur garde en mémoire le lien entre cet identifiant, le fichier et le nom sous lequel il sera rangé (voir plus bas). Le téléphone reçoit l'identifiant avec les réponses de CLIP.

## 3. À la validation, la photo est rangée

Fichier `server.py`, fonction `validate` :

```
upload = pending.pop(analysis_id)
target, n = photos / upload["name"], 1
while target.exists():                                        # jamais d'écrasement
    n += 1
    target = photos / f"{Path(upload['name']).stem} ({n}){Path(upload['name']).suffix}"
shutil.move(upload["path"], target)                           # uploads/ → dossier des photos

expected[target.name] = {name: validation.answers.get(name) for name in names}
expected_path.write_text(json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8")
```

Le fichier est **déplacé** de `uploads/` vers le dossier `--photos`. Les réponses validées sont ajoutées à `expected.json`.

## Nom de la photo rangée

Les appareils photo des téléphones appellent souvent toutes leurs photos `image.jpg`. C'est le cas sur iPhone, par exemple. Le nom d'origine n'est donc jamais gardé : la photo est nommée par un **timestamp en millisecondes** (fonctions `read_exif` et `file_name` de `server.py`) :

- **Avec une date EXIF** (`DateTimeOriginal`, sinon `DateTime`), c'est le timestamp de la prise de vue. Exemple : `DSC03383.jpg`, prise le 11 septembre 2024 à 14 h 26 min 39 s, devient `1726057599000.jpg`.
- L'EXIF n'indique pas toujours le fuseau horaire. S'il est présent (`OffsetTimeOriginal`), il est utilisé. Sinon, la date est lue comme une heure locale du PC.
- **Sans date EXIF**, c'est le timestamp de l'envoi de la photo.
- Deux photos prises dans la même seconde ne s'écrasent pas : la seconde devient `1726057599000 (2).jpg`.

L'analyse renvoie aussi au téléphone, dans `exif`, la date telle qu'écrite par l'appareil, la marque et le modèle, la vitesse, l'ouverture, la focale et l'ISO. L'application les affiche sur la carte. Sans date EXIF, elle affiche « Date inconnue ».

## Limites à connaître

- **Date absente :** certains navigateurs retirent les données EXIF à l'envoi. La photo est alors nommée d'après l'heure d'envoi, et la carte affiche « Date inconnue ».
- **Photos non validées :** si l'utilisateur clique sur « Autre photo » ou ferme la page, la photo reste dans `uploads/` jusqu'au prochain démarrage du serveur, qui vide ce dossier.
- **Redémarrage :** la liste des photos en attente n'existe qu'en mémoire. Si le serveur redémarre entre l'analyse et la validation, la validation échoue avec « La photo n'a pas pu être enregistrée ».
