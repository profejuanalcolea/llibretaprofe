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
- `PROVES_CAPTURES=carpeta` desa captures de pantalla d'algunes proves.
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
| Calculadora | Càlcul propi: operacions, coma decimal, percentatges i missatges d'error |
| Mode mòbil | Un telèfon obre la vista de consulta |
| PDF | Es genera el PDF de la llibreta EXEMPLE |
| Seguretat (SRI) | Una biblioteca de PDF manipulada no s'executa |
| Textos llargs | Rètol amb el text complet i punts suspensius a les columnes Lliure |
| Sons | Tots els sons del temporitzador sonen, sense saturar i més curts que l'interval |
| Bloc | Pestanyes, text desat, pòsits al Bloc i fora d'Eines, número d'avís a la icona |
| Migració del Bloc | Dades antigues amb pòsits a Eines passen al Bloc sense perdre res |
| Sortides | Menú al nom, botó a la barra (agrupat a partir de 3), avís amb cucut, Esperem, tornada, consulta, PDF i curs nou |
| No compta | Una columna dins d'una categoria s'exclou del càlcul, es marca amb ⊘ i torna a comptar |
| «No ava» | nav/noava/no ava, color taronja, no compta, desplegables i «D'una altra llibreta» |
| Columnes amagades | La llista del xip «amagades» s'obre i es tanca i no tapa la taula |
| Ordinador | «És el teu ordinador?»: pregunta un cop, mode temporal, etiqueta, avís en sortir i botó d'esborrar |
| Arxiu (2) | Cursos del més nou al més antic, curs automàtic, llistes distingides i mida del fitxer |
| Pestanyes | Dues pestanyes i dos ordinadors: avís, una pestanya cedeix i no desa, conflicte en desar |
| Arxiu (3) | Exportar a PDF i esborrar amb confirmació escrivint el nom, i desfer |
| Data i duplica | Botó 📅 (nom editable, «(2)» si es repeteix) i «Duplica la columna» buida al costat |
| Classes | Migració de Nivell+Lletres, recuperar dels Llistats (previsualització, còpia, desfer, duplicats) i propagació a llibretes actives però no arxivades |
| Recursos | El quadre «Nou enllaç» s'obre i desa |
| Capçalera | Menú ⋯, arrossegar dins la categoria, desplegar clicant la franja, nom en dues línies |
| Mòbil (2) | Barra Llibreta/Bloc/Enllaços, Bloc editable, «És el teu mòbil?» |
| Full de càlcul | Pestanya per llibreta activa i per llistat, nota final com a número, sense fórmules, convertit a Full de Google a la carpeta del Drive |
| Barra plegable | Franja amb el nom a l'esquerra i avisos, es recorda, canvi de llibreta pel nom i Alt+↑/↓, Llibreta/Avaluació |
| Franja de columna solta | Color de la columna a la franja de dalt, text lliure des de Propietats i doble clic |
| Opcions amb icones | Opcions només amb icones es desen i s'enganxen bé; els suggeriments omplen opcions i colors sense perdre les cel·les |
| Opcions | Desplegable propi, colors, recompte, comptar per a la nota, treure opcions en ús i llistes |

El programa acaba amb codi 0 si tot és correcte i 1 si alguna prova falla.
