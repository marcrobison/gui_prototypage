# Livrables – projet intégré (5A ESE)

| Fichier | Contenu |
|---|---|
| `rapport.pdf` | Rapport technique (parties 1 à 3 + bilan de conformité) |
| `presentation.pdf` | Support de présentation (15 min) |
| `Robison_Marc_5A_ESE_projet_integre.zip` | Archive Moodle : PDF + code source + base de données exemple (générée, non versionnée) |

## Reconstruire
```bash
./build.sh            # recompile les deux PDF et l'archive .zip
```

Les captures d'écran (`figures/captures/`) viennent de l'application réelle. Pour les refaire :
```bash
python -m venv /tmp/pw && /tmp/pw/bin/pip install playwright
/tmp/pw/bin/python scripts/capture.py ../../.venv/bin/python3 /usr/bin/chromium figures/captures build/data
```
Les maquettes basse fidélité : `../../.venv/bin/python scripts/wireframes.py figures/wireframes`.
