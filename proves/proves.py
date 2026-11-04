#!/usr/bin/env python3
"""Proves automàtiques de la Llibreta del Profe.

Ús (des de l'arrel del repositori):
    python3 proves/proves.py                 # passa totes les proves contra index.html
    python3 proves/proves.py --referencia    # torna a generar proves/referencia-mitjanes.json
    python3 proves/proves.py --fitxer altre.html

Requisits: Python 3 i Playwright amb Chromium (pip install playwright; playwright install chromium).
Per a la prova de PDF cal jsPDF 2.5.1 i jspdf-autotable 3.8.2: es baixen de jsDelivr o, si no hi ha
xarxa, es fan servir els de la carpeta indicada a la variable d'entorn PROVES_NPM (node_modules).

NOMÉS DADES INVENTADES. Aquest repositori és públic: mai hi poseu noms ni notes d'alumnes reals.
Google (login, Drive i Classroom) se simula: les proves no es connecten mai a cap compte real.
"""
import json, os, re, sys, threading, functools, itertools, urllib.parse, http.server, socketserver, traceback, base64
from playwright.sync_api import sync_playwright

ARREL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(ARREL, 'proves', 'referencia-mitjanes.json')
args = sys.argv[1:]
FITXER = args[args.index('--fitxer') + 1] if '--fitxer' in args else 'index.html'
GENERA_REF = '--referencia' in args
NPM = os.environ.get('PROVES_NPM', '')

# ---------------------------------------------------------------- servidor local
class Silenci(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
srv = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Silenci, directory=ARREL))
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f'http://127.0.0.1:{PORT}/{FITXER}'

# ---------------------------------------------------------------- Google simulat
ids = itertools.count(1)
PDFS = []
INIT = """window.__tok=[];window.google={accounts:{oauth2:{initTokenClient:o=>({requestAccessToken:()=>{window.__tok.push(o.scope);
setTimeout(()=>o.callback({access_token:'T'+window.__tok.length,expires_in:3600,scope:o.scope}),10)}}),revoke:()=>{}}}};"""

def lib_pdf(url):
    nom = 'jspdf/dist/jspdf.umd.min.js' if 'jspdf@' in url else 'jspdf-autotable/dist/jspdf.plugin.autotable.min.js'
    if NPM and os.path.exists(os.path.join(NPM, nom)):
        return open(os.path.join(NPM, nom)).read()
    return None

def google_amb(FILES):
  """Google simulat amb un Drive propi (FILES: id -> {name, content, props, folder})."""
  def google(route, req):
      url, m = req.url, req.method
      j = lambda o, st=200: route.fulfill(status=st, content_type='application/json', body=json.dumps(o))
      if 'gsi/client' in url:
          return route.fulfill(status=200, content_type='text/javascript', body='')
      if 'cdn.jsdelivr.net' in url:
          cos = lib_pdf(url)
          return route.fulfill(status=200, content_type='text/javascript', body=cos) if cos else route.continue_()
      if 'googleapis.com' not in url:
          return route.continue_()
      if '/about' in url:
          return j({'user': {'emailAddress': 'profe@exemple.cat'}})
      if 'upload/drive/v3/files' in url:
          buf = req.post_data_buffer or b''
          if b'application/pdf' in buf:
              meta = json.loads(buf.split(b'\r\n\r\n')[1].split(b'\r\n--')[0]); PDFS.append(meta.get('name'))
              return j({'id': 'P%d' % next(ids)})
          parts = buf.decode().split('\r\n\r\n')
          meta = json.loads(parts[1].split('\r\n--')[0]); content = parts[2].split('\r\n--')[0]
          if m == 'POST':
              fid = 'F%d' % next(ids); FILES[fid] = {'name': meta.get('name'), 'content': content, 'props': meta.get('appProperties', {})}
          else:
              fid = url.split('/files/')[1].split('?')[0]; FILES[fid]['content'] = content; FILES[fid]['props'].update(meta.get('appProperties', {}))
          return j({'id': fid})
      if 'drive/v3/files' in url:
          q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query); path = urllib.parse.urlparse(url).path
          if m == 'POST':
              meta = json.loads(req.post_data); fid = 'D%d' % next(ids); FILES[fid] = {'name': meta['name'], 'folder': True, 'props': {}}
              return j({'id': fid})
          if path.endswith('/files'):
              qq = q.get('q', [''])[0]; res = []
              for fid, f in FILES.items():
                  if 'folder' in qq:
                      if f.get('folder') and f['name'] in qq: res.append({'id': fid})
                  elif 'in parents' in qq: pass
                  elif not f.get('folder') and f['name'] == 'llibreta-notes.json' and f['props'].get('copia') != '1':
                      res.append({'id': fid, 'appProperties': f['props']})
              return j({'files': res})
          fid = path.split('/files/')[1]
          if q.get('alt') == ['media']:
              return route.fulfill(status=200, content_type='application/json', body=FILES[fid]['content'])
          return j({'appProperties': FILES[fid]['props']})
      return j({})
  return google

# ---------------------------------------------------------------- utilitats
RESULTATS = []
def prova(nom):
    def dec(f):
        def run(*a):
            try:
                f(*a); RESULTATS.append(('OK', nom, ''))
            except Omesa as e:
                RESULTATS.append(('OMESA', nom, str(e)))
            except Exception as e:
                RESULTATS.append(('FALLA', nom, (str(e) or e.__class__.__name__).split('\n')[0][:300]))
        run.__name__ = f.__name__; return run
    return dec
class Omesa(Exception): pass
def comprova(cond, msg):
    if not cond: raise AssertionError(msg)

def pagina_local(b, **kw):
    """Entra amb el Google simulat i un Drive buit: l'app crea la llibreta EXEMPLE (dades inventades)."""
    FILES = {}
    ctx = b.new_context(viewport={'width': 1400, 'height': 850}, **kw); ctx.add_init_script(INIT); ctx.route('**/*', google_amb(FILES))
    pg = ctx.new_page(); pg.errs = []; pg.drive = FILES
    pg.on('pageerror', lambda e: pg.errs.append(str(e)))
    pg.goto(URL); pg.evaluate('localStorage.clear()'); pg.reload(); pg.wait_for_timeout(400)
    pg.click('#lgEntra'); pg.wait_for_timeout(1200)
    return ctx, pg

MITJANES_JS = """(()=>{const out={};for(const sub of state.subjects){if(sub.tipus==='llista')continue;const r={};
 for(const st of sub.students){const k=st.cognoms+', '+st.nom;const cats={};
  for(const c of sub.categories){const x=catResult(sub,c,st);cats[c.name]=x?x.label:null}
  const f=finalDe(sub,st);r[k]={cats,final:f?Math.round(f.num*10000)/10000:null}}
 out[sub.name]=r}return out})()"""

# ---------------------------------------------------------------- proves
@prova('Arrencada: carrega sense errors i amb la llibreta EXEMPLE')
def p_arrencada(b):
    ctx, pg = pagina_local(b)
    comprova(not pg.errs, 'errors JS: %s' % pg.errs)
    comprova(pg.evaluate('state.subjects[0].name') == 'EXEMPLE', 'no hi ha EXEMPLE')
    comprova(pg.evaluate('state.subjects[0].students.length') == 10, 'EXEMPLE no té 10 alumnes')
    comprova(pg.locator('#tw tbody tr[data-s]').count() == 10, 'la taula no mostra 10 files')
    ctx.close()

@prova('Mitjanes: EXEMPLE dona exactament els valors de referència')
def p_mitjanes(b):
    ctx, pg = pagina_local(b)
    act = pg.evaluate(MITJANES_JS)
    if GENERA_REF:
        json.dump(act, open(REF, 'w'), ensure_ascii=False, indent=1, sort_keys=True); ctx.close(); return
    comprova(os.path.exists(REF), 'falta proves/referencia-mitjanes.json (genereu-lo amb --referencia)')
    ref = json.load(open(REF))
    dif = []
    for llib, al in ref.items():
        for nom, v in al.items():
            a = act.get(llib, {}).get(nom)
            if a != v: dif.append(f'{llib} · {nom}: esperat {v}, surt {a}')
    comprova(not dif, '; '.join(dif[:4]) + (' …' if len(dif) > 4 else ''))
    ctx.close()

@prova('Càlcul: mitjana per categoria, ponderació, F, FJ i notes sobre un altre màxim')
def p_calcul(b):
    ctx, pg = pagina_local(b)
    r = pg.evaluate("""(()=>{const s=novaSub('Prova càlcul','buida','🧪');s.categories=[
       {id:'kA',name:'Exàmens',sigla:'EX',weight:60,method:'mean'},{id:'kB',name:'Treballs',sigla:'TR',weight:40,method:'mean'}];
     s.columns=[{id:'c1',name:'Ex1',type:'num',cat:'kA',max:10},{id:'c2',name:'Ex2',type:'num',cat:'kA',max:10},
       {id:'c3',name:'Tr1',type:'num',cat:'kB',max:20},{id:'c4',name:'Tr2',type:'num',cat:'kB',max:10}];
     s.students=[{id:'a1',nom:'Ada',cognoms:'Prova'},{id:'a2',nom:'Bru',cognoms:'Prova'},{id:'a3',nom:'Cesc',cognoms:'Prova'}];
     state.subjects.push(s);
     setG(s,'c1','a1',6);setG(s,'c2','a1',8);setG(s,'c3','a1',10);setG(s,'c4','a1',7);   // EX 7 · TR (5+7)/2=6 · final 6,6
     setG(s,'c1','a2',8);setG(s,'c2','a2','F');setG(s,'c3','a2',20);                     // EX (8+0)/2=4 · TR 10 · final 6,4
     setG(s,'c1','a3',9);setG(s,'c2','a3','FJ');                                          // EX 9 (FJ no compta) · sense TR · final 9
     const f=st=>Math.round(finalDe(s,st).num*1000)/1000;return s.students.map(f)})()""")
    comprova(r == [6.6, 6.4, 9], f'finals {r}, esperats [6.6, 6.4, 9]')
    ctx.close()

@prova('Edició: escriure notes a la taula, F/FJ i moure amb les fletxes')
def p_edicio(b):
    ctx, pg = pagina_local(b)
    cid = pg.evaluate("cur().columns.find(c=>c.type==='num').id")
    cel = pg.locator(f'td[data-c="{cid}"] input.g').first
    cel.click(); cel.fill('fj'); pg.keyboard.press('ArrowDown'); pg.wait_for_timeout(150)
    comprova(pg.evaluate(f"getG(cur(),'{cid}',alumnesVisibles(cur())[0].id)") == 'FJ', 'fj no es desa com FJ')
    comprova(pg.evaluate("document.activeElement.closest('tr').rowIndex") >= 2, 'la fletxa avall no baixa de fila')
    cel2 = pg.locator(f'td[data-c="{cid}"] input.g').nth(1); cel2.fill('7,5'); cel2.press('Tab'); pg.wait_for_timeout(150)
    comprova(pg.evaluate(f"getG(cur(),'{cid}',alumnesVisibles(cur())[1].id)") == 7.5, 'la coma decimal no es desa com 7.5')
    n = pg.evaluate('HIST.und.length'); pg.click('#btnUndo'); pg.wait_for_timeout(150)
    comprova(pg.evaluate('HIST.und.length') < n, 'desfer no funciona')
    comprova(not pg.errs, 'errors JS: %s' % pg.errs)
    ctx.close()

@prova('Desat: les notes es conserven en tornar a carregar la pàgina')
def p_desat_local(b):
    ctx, pg = pagina_local(b)
    pg.evaluate("(()=>{const s=cur(),c=s.columns.find(c=>c.type==='num');setG(s,c.id,s.students[0].id,3.25);save()})()")
    pg.wait_for_timeout(3500); pg.reload(); pg.wait_for_timeout(400)
    if pg.locator('#lgEntra').is_visible(): pg.click('#lgEntra')
    pg.wait_for_timeout(1200)
    v = pg.evaluate("(()=>{const s=cur(),c=s.columns.find(c=>c.type==='num');return getG(s,c.id,s.students[0].id)})()")
    comprova(v == 3.25, f'després de recarregar surt {v}')
    ctx.close()

@prova('Drive (simulat): entra amb Google, desa al fitxer i el torna a llegir')
def p_drive(b):
    FILES = {}
    ctx = b.new_context(viewport={'width': 1400, 'height': 850}); ctx.add_init_script(INIT); ctx.route('**/*', google_amb(FILES))
    pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(URL); pg.wait_for_timeout(400); pg.click('#lgEntra'); pg.wait_for_timeout(1200)
    comprova(pg.evaluate('state.subjects.length') >= 1, 'no ha entrat')
    pg.evaluate("(()=>{const s=cur(),c=s.columns.find(c=>c.type==='num');setG(s,c.id,s.students[1].id,4.75);save('prova')})()")
    pg.wait_for_timeout(3500)
    f = [x for x in FILES.values() if x.get('name') == 'llibreta-notes.json' and x['props'].get('copia') != '1']
    comprova(f, 'no s\'ha creat llibreta-notes.json al Drive')
    comprova('4.75' in f[0]['content'], 'el fitxer del Drive no porta la nota nova')
    ctx2 = b.new_context(viewport={'width': 1400, 'height': 850}); ctx2.add_init_script(INIT); ctx2.route('**/*', google_amb(FILES))
    pg2 = ctx2.new_page(); pg2.goto(URL); pg2.wait_for_timeout(400); pg2.click('#lgEntra'); pg2.wait_for_timeout(1500)
    v = pg2.evaluate("(()=>{const s=state.subjects.find(x=>x.name==='EXEMPLE'),c=s.columns.find(c=>c.type==='num');return getG(s,c.id,s.students[1].id)})()")
    comprova(v == 4.75, f'un altre navegador llegeix {v} del Drive')
    comprova(not errs, 'errors JS: %s' % errs)
    ctx.close(); ctx2.close()

@prova('Anotacions de cel·la: marcar i comentar amb el clic dret')
def p_anotacions(b):
    ctx, pg = pagina_local(b)
    td = pg.locator('#tw tbody td[data-c]').nth(4); td.click(button='right'); pg.wait_for_timeout(100); pg.click('[data-an=h]'); pg.wait_for_timeout(150)
    td = pg.locator('#tw tbody td[data-c]').nth(4); td.click(button='right'); pg.click('[data-an=t]'); pg.fill('#qIn', 'Examen repetit')
    pg.click('#qBtns button:last-child'); pg.wait_for_timeout(150)
    an = pg.evaluate('Object.values(cur().anot)')
    comprova(an and an[0].get('h') and an[0].get('t') == 'Examen repetit', f'anotació: {an}')
    comprova(pg.locator('.antri').count() == 1, 'no surt el triangle del comentari')
    ctx.close()

@prova('Avaluació: es calcula i es pinta per a tots els alumnes')
def p_avaluacio(b):
    ctx, pg = pagina_local(b)
    pg.click('#tabs button[data-t=resum]'); pg.wait_for_timeout(250)
    comprova(pg.locator('table.aval tbody tr').count() >= 10, 'la taula d\'Avaluació no té els alumnes')
    comprova(not pg.errs, 'errors JS: %s' % pg.errs)
    ctx.close()

@prova('Arxiu: arxivar, veure-la a l\'Arxiu (només lectura) i desarxivar')
def p_arxiu(b):
    ctx, pg = pagina_local(b)
    pg.evaluate("(()=>{const s=novaSub('Llibreta a arxivar','eso','📗');state.subjects.push(s);s.archived={cat:'Curs 2025-26',data:'2026-06-30'};save();tab='arxiu';render()})()")
    pg.wait_for_timeout(200)
    comprova('Curs 2025-26' in pg.inner_text('#main'), 'no surt la carpeta Curs 2025-26')
    comprova(pg.locator('[data-desarx]').count() == 1, 'no surt el botó Desarxiva')
    comprova(pg.evaluate("[...document.querySelectorAll('#llSel option')].every(o=>!o.textContent.includes('Llibreta a arxivar'))") , 'l\'arxivada surt al desplegable')
    pg.locator('[data-desarx]').first.click(); pg.wait_for_timeout(200)
    comprova(pg.evaluate("state.subjects.find(s=>s.name==='Llibreta a arxivar').archived") is None, 'no s\'ha desarxivat')
    ctx.close()

@prova('Llista sense notes: no té Avaluació')
def p_llista(b):
    ctx, pg = pagina_local(b)
    pg.evaluate("(()=>{const s=novaSub('Excursió','llista','📋');s.tipus='llista';state.subjects.push(s);state.cur=s.id;save();tab='llibreta';render()})()")
    pg.wait_for_timeout(200)
    comprova(pg.locator('#tabs [data-t=resum]').is_hidden(), 'la llista mostra la pestanya Avaluació')
    comprova(not pg.errs, 'errors JS: %s' % pg.errs)
    ctx.close()

@prova('Calculadora: operacions, coma decimal i percentatges')
def p_calculadora(b):
    ctx, pg = pagina_local(b)
    res = pg.evaluate("""(()=>{const o={};for(const e of ['7,5*0,4+8*0,6','200+10%','(2+3)*4']){calcObre(true);cin.value=e;calcAvalua();o[e]=cin.value}return o})()""")
    comprova(res['7,5*0,4+8*0,6'] in ('7,8', '7.8'), f'7,5*0,4+8*0,6 → {res}')
    comprova(res['200+10%'] in ('220',), f'200+10% → {res}')
    comprova(res['(2+3)*4'] == '20', f'(2+3)*4 → {res}')
    ctx.close()

@prova('Mode mòbil: un telèfon obre la vista de consulta')
def p_mobil(b):
    ctx = b.new_context(**p_mobil.dev); ctx.add_init_script(INIT); ctx.route('**/*', google_amb({}))
    pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(URL); pg.evaluate('localStorage.clear()'); pg.reload(); pg.wait_for_timeout(900)
    comprova(pg.evaluate('esMobil()'), 'esMobil() és fals en un telèfon')
    comprova(not errs, 'errors JS: %s' % errs)
    ctx.close()

@prova('PDF: genera el PDF de la llibreta EXEMPLE')
def p_pdf(b):
    ctx, pg = pagina_local(b)
    try:
        n = pg.evaluate("(async()=>{const d=await fesPDF([state.subjects[0]],false);return d.output('arraybuffer').byteLength})()")
    except Exception as e:
        if 'jspdf' in str(e).lower() or 'carreg' in str(e).lower() or 'Failed' in str(e):
            raise Omesa('no s\'ha pogut carregar jsPDF (sense xarxa i sense PROVES_NPM)')
        raise
    comprova(n > 5000, f'PDF massa petit ({n} bytes)')
    ctx.close()

# ---------------------------------------------------------------- execució
with sync_playwright() as p:
    b = p.chromium.launch()
    p_mobil.dev = p.devices['iPhone 13']
    proves = [p_arrencada, p_mitjanes, p_calcul, p_edicio, p_desat_local, p_drive, p_anotacions,
              p_avaluacio, p_arxiu, p_llista, p_calculadora, p_mobil, p_pdf]
    if GENERA_REF: proves = [p_mitjanes]
    for f in proves: f(b)
    b.close()
srv.shutdown()

if GENERA_REF:
    print('Referència desada a', REF); sys.exit(0)
ok = sum(r[0] == 'OK' for r in RESULTATS); fa = [r for r in RESULTATS if r[0] == 'FALLA']; om = [r for r in RESULTATS if r[0] == 'OMESA']
for est, nom, msg in RESULTATS:
    print(f"{'✔' if est=='OK' else '✘' if est=='FALLA' else '–'} {nom}" + (f'\n    {msg}' if msg else ''))
print(f'\n{ok} correctes · {len(fa)} fallades · {len(om)} omeses · fitxer provat: {FITXER}')
sys.exit(1 if fa else 0)
