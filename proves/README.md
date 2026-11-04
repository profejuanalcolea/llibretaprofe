# Proves automàtiques

Comproven que la Llibreta del Profe continua funcionant abans de publicar un `index.html` nou.

## Norma

**Només dades inventades.** Aquest repositori és públic. Mai hi poseu noms, notes ni cap dada d'alumnes reals.
Google (login, Drive i Classroom) se simula: les proves no es connecten mai a cap compte.

## Com es passen

Des de l'arrel del repositori:

```
pip install playwright
playwright install chromium
python3 proves/proves.py
```

- `python3 proves/proves.py --fitxer altre.html` prova un altre fitxer (per exemple, una versió en preparació).
- `python3 proves/proves.py --referencia` torna a generar `referencia-mitjanes.json`. Feu-ho **només** quan un canvi
  hagi de canviar les mitjanes de la llibreta EXEMPLE a propòsit, i reviseu-ne la diferència.
- La prova de PDF necessita jsPDF 2.5.1 i jspdf-autotable 3.8.2. Si no hi ha accés a jsDelivr, indiqueu una carpeta
  `node_modules` amb tots dos paquets a la variable `PROVES_NPM`. Si no es troben, la prova surt com a «omesa».

## Què comproven

| Prova | Què vigila |
|---|---|
| Arrencada | L'app carrega sense errors i crea la llibreta EXEMPLE |
| Mitjanes | Les mitjanes de la llibreta EXEMPLE són exactament les de `referencia-mitjanes.json` |
| Càlcul | Mitjana per categoria, ponderació, F (compta 0), FJ (no compta) i notes sobre un altre màxim |
| Edició | Escriure a la taula, «fj» → FJ, coma decimal, fletxes i desfer |
| Desat | Les notes es conserven en tornar a carregar |
| Drive (simulat) | Entra amb Google, desa al fitxer i un altre navegador el llegeix |
| Anotacions | Marcar i comentar una cel·la amb el clic dret |
| Avaluació | La pestanya Avaluació es pinta per a tots els alumnes |
| Arxiu | Arxivar, veure-la a l'Arxiu i desarxivar |
| Llista | Una llista sense notes no té pestanya d'Avaluació |
| Calculadora | Operacions, coma decimal i percentatges |
| Mode mòbil | Un telèfon obre la vista de consulta |
| PDF | Es genera el PDF de la llibreta EXEMPLE |

El programa acaba amb codi 0 si tot és correcte i 1 si alguna prova falla.
