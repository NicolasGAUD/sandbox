# Comment la photo est copiée sur le serveur

**Application :** CLIP urbex (branche `feature/photo-upload-app`)
**Date :** 25 octobre 2026

La photo passe par trois étapes. À aucun moment elle n'est recompressée : c'est le fichier d'origine, octet pour octet, avec ses données EXIF.

## 1. Le téléphone envoie la photo

Fichier `app/src/app/analysis.service.ts`, lignes 89 à 91 :

```
const form = new FormData();
form.append('photo', file, file.name);
const analysis = await firstValueFrom(this.http.post<Analysis>('/api/analyses', form));
```

Le fichier choisi, ou pris avec l'appareil photo, part tel quel dans une requête `multipart/form-data`, avec son nom d'origine.

## 2. Le serveur l'analyse, puis la met en attente

Fichier `server.py`, lignes 84 à 103 :

```
content = photo.file.read()                                   # octets bruts du fichier reçu
image = ImageOps.exif_transpose(Image.open(io.BytesIO(content))).convert("RGB")
results, details, _ = analyzer.analyse(image, all_details=True)   # analyse en mémoire

analysis_id = uuid.uuid4().hex
path = UPLOADS / f"{analysis_id}{suffix}"                     # uploads/<identifiant>.jpg
path.write_bytes(content)                                     # copie exacte du fichier reçu
pending[analysis_id] = {"path": path, "name": shot_name(content, name)}
```

- L'analyse se fait sur une image décodée en mémoire, qui ne sert qu'à CLIP.
- Le fichier d'origine est écrit **après** l'analyse, dans `uploads/`, sous un nom unique (un UUID) pour éviter toute collision.
- Le serveur garde en mémoire le lien entre cet identifiant, le fichier et le nom sous lequel il sera rangé (voir plus bas). Le téléphone reçoit l'identifiant avec les réponses de CLIP.

## 3. À la validation, la photo est rangée

Fichier `server.py`, lignes 117 à 133 :

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

Les appareils photo des téléphones appellent souvent toutes leurs photos `image.jpg`. C'est le cas sur iPhone, par exemple. La photo est donc nommée d'après sa date de prise de vue, lue dans ses données EXIF (fichier `server.py`, lignes 41 à 54) :

```
exif = Image.open(io.BytesIO(content)).getexif()
# DateTimeOriginal (Exif sub-IFD), otherwise DateTime (last change).
taken = exif.get_ifd(0x8769).get(36867) or exif.get(306)
shot = datetime.strptime(str(taken).strip("\x00 "), "%Y:%m:%d %H:%M:%S")
return shot.strftime("%Y-%m-%d_%H-%M-%S") + Path(name).suffix.lower()
```

- Exemple : `DSC03077-HDR.jpg`, prise le 10 juin 2017 à 14 h 23 min 08 s, devient `2017-06-10_14-23-08.jpg`.
- Une photo sans date de prise de vue garde son nom d'origine.
- Deux photos prises dans la même seconde ne s'écrasent pas : la seconde devient `2017-06-10_14-23-08 (2).jpg`.

## Limites à connaître

- **Date absente :** certains navigateurs retirent les données EXIF à l'envoi. La photo garde alors son nom d'origine, parfois `image.jpg`, et les suivantes deviennent `image (2).jpg`, `image (3).jpg`…
- **Photos non validées :** si l'utilisateur clique sur « Autre photo » ou ferme la page, la photo reste dans `uploads/` jusqu'au prochain démarrage du serveur, qui vide ce dossier.
- **Redémarrage :** la liste des photos en attente n'existe qu'en mémoire. Si le serveur redémarre entre l'analyse et la validation, la validation échoue avec « La photo n'a pas pu être enregistrée ».
