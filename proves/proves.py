#!/usr/bin/env python3
"""Proves automàtiques de la Llibreta del Profe.

Ús (des de l'arrel del repositori):
    python3 proves/proves.py                 # passa totes les proves contra index.html
    python3 proves/proves.py --referencia    # torna a generar proves/referencia-mitjanes.json
    python3 proves/proves.py --fitxer altre.html
    python3 proves/proves.py --nomes pdf,sri       # només les proves que contenen aquests noms

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
NOMES = args[args.index('--nomes') + 1].split(',') if '--nomes' in args else []
NPM = os.environ.get('PROVES_NPM', '')
CAPT = os.environ.get('PROVES_CAPTURES', '')   # carpeta on desar captures de pantalla (opcional)
def captura(pg, nom):
    if CAPT: pg.screenshot(path=os.path.join(CAPT, nom + '.png'))

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
INIT_BASE = """window.__tok=[];window.google={accounts:{oauth2:{initTokenClient:o=>({requestAccessToken:()=>{window.__tok.push(o.scope);
setTimeout(()=>o.callback({access_token:'T'+window.__tok.length,expires_in:3600,scope:o.scope}),10)}}),revoke:()=>{}}}};"""
# per defecte, les proves fan com si l'ordinador fos de la persona (la pregunta «És el teu ordinador?» es prova a part)
INIT = INIT_BASE + "try{localStorage.setItem('llibreta-ordinador','meu')}catch(e){}"


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
          if cos and FILES.get('__manipula'): cos = cos + '\n/* manipulat */'
          # jsDelivr envia Access-Control-Allow-Origin: *, imprescindible perquè funcioni l'empremta (SRI)
          return route.fulfill(status=200, content_type='text/javascript', body=cos, headers={'Access-Control-Allow-Origin': '*'}) if cos else route.continue_()
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
       {id:'kA',name:'Exàmens',sigla:'EX',color:'#E69F00',weight:60,method:'mean'},{id:'kB',name:'Treballs',sigla:'TR',color:'#009E73',weight:40,method:'mean'}];
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

@prova('Calculadora: càlcul propi, coma decimal, percentatges i missatges d\'error')
def p_calculadora(b):
    ctx, pg = pagina_local(b)
    casos = {'7,5*0,4+8*0,6': 7.8, '200+10%': 220, '200-15%': 170, '50*20%': 10, '15%': 0.15, '(2+3)*4': 20,
             '2(3+1)': 8, '7,5×0,4+8×0,6': 7.8, '10÷4': 2.5, '−3+5': 2, '-(2+3)': -5, '0.1+0.2': 0.3,
             '(200+10%)*2': 440, '100+10%+10%': 121, '2*-3': -6, '1/3*3': 1}
    res = pg.evaluate("c=>Object.fromEntries(Object.keys(c).map(e=>{try{return [e,calcula(e)]}catch(x){return [e,'ERR '+x.message]}}))", casos)
    mal = {e: (v, res[e]) for e, v in casos.items() if not (isinstance(res[e], (int, float)) and abs(res[e] - v) < 1e-9)}
    comprova(not mal, f'resultats incorrectes: {mal}')
    errs = {'(2+3': 'parèntesi', '2+3)': 'parèntesi', '5/0': 'zero', '2+': 'número', '3+alert(1)': 'no vàlid',
            '1,2,3': 'mal escrit', '': 'operació', '*4': 'número'}
    res = pg.evaluate("c=>Object.fromEntries(Object.keys(c).map(e=>{try{return [e,'OK '+calcula(e)]}catch(x){return [e,x.message]}}))", errs)
    mal = {e: res[e] for e, frag in errs.items() if frag not in res[e]}
    comprova(not mal, f'missatges d\'error inesperats: {mal}')
    pg.evaluate("calcObre(true)"); pg.fill('#calcIn', '200+10%'); pg.press('#calcIn', 'Enter')
    comprova(pg.input_value('#calcIn') == '220' and '200+10%' in pg.inner_text('#calcHist'), 'la finestra de la calculadora no mostra 220')
    pg.fill('#calcIn', '(2+3'); pg.press('#calcIn', 'Enter')
    comprova('parèntesi' in pg.inner_text('#calcHist'), 'la finestra no mostra el missatge d\'error')
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

@prova('Seguretat: una biblioteca de PDF manipulada no s\'executa (empremta SRI)')
def p_sri(b):
    if not NPM: raise Omesa('cal PROVES_NPM')
    ctx, pg = pagina_local(b)
    pg.drive['__manipula'] = True
    r = pg.evaluate("(async()=>{try{await fesPDF([state.subjects[0]],false);return 'fet'}catch(e){return e.message}})()")
    comprova(r != 'fet', 'el PDF s\'ha fet amb una biblioteca manipulada')
    comprova('segura' in r, f'missatge inesperat: {r}')
    comprova(not pg.evaluate('!!window.jspdf'), 'la biblioteca manipulada s\'ha executat')
    ctx.close()

@prova('Textos llargs a Lliure: rètol amb el text complet i punts suspensius')
def p_textllarg(b):
    ctx, pg = pagina_local(b)
    llarg = 'Ha portat el material de laboratori però ha oblidat la bata i les ulleres de protecció'
    cid = pg.evaluate("cur().columns.find(c=>c.type==='lliure').id")
    cel = pg.locator(f'td[data-c="{cid}"] input.lliure').first
    cel.click(); cel.fill(llarg); cel.press('Tab'); pg.wait_for_timeout(200)
    comprova(pg.evaluate(f"getG(cur(),'{cid}',alumnesVisibles(cur())[0].id)") == llarg, 'el text no es desa sencer')
    comprova(cel.get_attribute('title') == llarg, 'el rètol no té el text complet (mentre s\'escriu)')
    pg.evaluate("rLlibreta()"); pg.wait_for_timeout(150)
    cel = pg.locator(f'td[data-c="{cid}"] input.lliure').first
    comprova(cel.get_attribute('title') == llarg, 'el rètol no té el text complet (després de repintar)')
    comprova(cel.evaluate("e=>getComputedStyle(e).textOverflow") == 'ellipsis', 'no hi ha punts suspensius')
    comprova(cel.evaluate("e=>e.scrollWidth>e.clientWidth"), 'el text de prova hi cap sencer: la prova no serveix')
    ctx.close()

@prova('Temporitzador: tots els sons sonen, amb un volum semblant i sense saturar')
def p_sons(b):
    ctx, pg = pagina_local(b)
    r = pg.evaluate("""(async()=>{const o={};for(const [k,v] of Object.entries(SONS)){
        T.ac=new OfflineAudioContext(1,44100*9,44100);T.out=null;v.f();const buf=await T.ac.startRendering();const d=buf.getChannelData(0);
        let pk=0,sq=0,n=0,fi=0;for(let i=0;i<d.length;i++){const a=Math.abs(d[i]);if(a>pk)pk=a;sq+=d[i]*d[i];if(a>.002)fi=i}
        o[k]={nom:v.nom,pic:+pk.toFixed(3),durada:+(fi/44100).toFixed(2),cada:v.cada}}T.ac=null;return o})()""")
    comprova({'joc', 'bip', 'bach', 'urba', 'cucut'} <= set(r) and 'plou' not in r, f'sons: {list(r)}')
    for k, v in r.items():
        comprova(v['pic'] > 0.05, f'{v["nom"]} no sona (pic {v["pic"]})')
        comprova(v['pic'] <= 1.0, f'{v["nom"]} satura (pic {v["pic"]})')
        comprova(v['durada'] * 1000 < v['cada'], f'{v["nom"]} dura més ({v["durada"]} s) que l\'interval de repetició')
    p_sons.info = r
    ctx.close()

@prova('Bloc: pestanyes, text desat, pòsits al Bloc i fora d\'Eines, número d\'avís a la icona')
def p_bloc(b):
    ctx, pg = pagina_local(b)
    pg.evaluate("(()=>{state.posits.push({id:'pz',text:'Portar les pipetes',color:PCOL[1],data:new Date().toISOString().slice(0,10),llib:''});save();render()})()")
    pg.wait_for_timeout(150)
    n = pg.evaluate("String(state.posits.filter(p=>nivPosit(p)).length)")
    comprova(pg.locator('.tabic[data-t=bloc] #bdg').is_visible() and pg.inner_text('#bdg') == n, f'el número d\'avís ({n}) no surt a la icona del Bloc')
    pg.click('.tabic[data-t=eines]'); pg.wait_for_timeout(150)
    comprova(pg.locator('.posit').count() == 0 and 'Pòsits' not in pg.inner_text('#main'), 'els pòsits encara surten a Eines')
    pg.click('.tabic[data-t=bloc]'); pg.wait_for_timeout(200)
    comprova(pg.evaluate('tab') == 'bloc', 'la icona no obre el Bloc')
    comprova(pg.locator('.posit', has_text='Portar les pipetes').count() == 1 or pg.locator('textarea[data-ptxt=pz]').count() == 1, 'el pòsit no surt al Bloc')
    pg.fill('#blTxt', 'Comprar guix\nReunió dimarts'); pg.wait_for_timeout(900)
    pg.click('#blNou'); pg.fill('#qIn', 'Material'); pg.click('#qBtns button:last-child'); pg.wait_for_timeout(200)
    comprova(pg.locator('.blp:not(.nou)').count() == 2 and pg.input_value('#blTxt') == '', 'no s\'ha creat la pestanya nova buida')
    pg.fill('#blTxt', '30 tubs d\'assaig'); pg.wait_for_timeout(900)
    pg.locator('.blp', has_text='Notes').click(); pg.wait_for_timeout(150)
    comprova(pg.input_value('#blTxt') == 'Comprar guix\nReunió dimarts', 'en tornar a la primera pestanya no hi ha el text')
    pg.locator('.blp', has_text='Material').dblclick(); pg.wait_for_timeout(150); pg.fill('#qIn', 'Laboratori'); pg.click('#qBtns button:last-child'); pg.wait_for_timeout(150)
    comprova(pg.locator('.blp', has_text='Laboratori').count() == 1, 'el doble clic no canvia el nom')
    pg.locator('.blp', has_text='Laboratori').drag_to(pg.locator('.blp', has_text='Notes')); pg.wait_for_timeout(200)
    comprova(pg.evaluate("state.bloc.pestanyes.map(p=>p.nom)") == ['Laboratori', 'Notes'], 'arrossegar no reordena les pestanyes')
    captura(pg, 'bloc')
    pg.keyboard.press('Escape'); pg.wait_for_timeout(150)
    comprova(pg.evaluate('tab') == 'llibreta', 'Esc no torna a la llibreta')
    pg.wait_for_timeout(3000); pg.reload(); pg.wait_for_timeout(400)
    if pg.locator('#lgEntra').is_visible(): pg.click('#lgEntra')
    pg.wait_for_timeout(1200)
    comprova(pg.evaluate("state.bloc.pestanyes.map(p=>p.nom+':'+p.text)") == ["Laboratori:30 tubs d'assaig", 'Notes:Comprar guix\nReunió dimarts'], 'el Bloc no es conserva en tornar a carregar')
    pg.click('.tabic[data-t=bloc]'); pg.wait_for_timeout(200)
    pg.click('#blDel'); pg.click('#qBtns button:last-child'); pg.wait_for_timeout(200)
    comprova(pg.evaluate("state.bloc.pestanyes.length") == 1, 'no s\'ha eliminat la pestanya')
    comprova(pg.locator('#blDel').count() == 0, 'es pot eliminar l\'última pestanya')
    comprova(not pg.errs, 'errors JS: %s' % pg.errs)
    ctx.close()

@prova('Migració: unes dades antigues amb pòsits a Eines passen al Bloc sense perdre res')
def p_migra_bloc(b):
    ctx, pg = pagina_local(b)
    r = pg.evaluate("""(()=>{const d=JSON.parse(JSON.stringify(state));delete d.bloc;d.eines.ordre=['aula','posits','recll','recgen'];
        d.posits=[{id:'p1',text:'Antic',color:PCOL[0],data:'',llib:''}];const m=migra(d);
        return {ordre:m.eines.ordre,pest:m.bloc.pestanyes.length,posits:m.posits.map(p=>p.text)}})()""")
    comprova(r == {'ordre': ['aula', 'recll', 'recgen'], 'pest': 1, 'posits': ['Antic']}, f'migració: {r}')
    ctx.close()

@prova('Sortides: menú al nom, botó a la barra, avís, Esperem, tornada, consulta, PDF i curs nou')
def p_sortides(b):
    ctx, pg = pagina_local(b)
    nom = pg.locator('#tw tbody tr[data-s] td.fx.nomc').first
    stid = nom.evaluate("e=>e.closest('tr').dataset.s"); snom = nom.inner_text()
    nom.click(button='right'); pg.wait_for_timeout(100)
    comprova(pg.is_visible('#soMenu') and pg.locator('#soMenu [data-som=wc]').count() == 1, 'el clic dret al nom no obre el menú WC/Sortida')
    pg.click('#soMenu [data-som=wc]'); pg.wait_for_timeout(150)
    comprova(pg.locator('#soBar .sobtn').count() == 1 and snom in pg.inner_text('#soBar'), 'no surt el botó de l\'alumne a la barra')
    comprova(pg.locator('#tw tbody td[data-c] .antri').count() == 0 and pg.evaluate("Object.keys(cur().anot||{}).length") == 0, 'la sortida ha tocat la taula')
    # doble clic en un altre alumne → Sortida
    nom2 = pg.locator('#tw tbody tr[data-s] td.fx.nomc').nth(1); nom2.dblclick(); pg.wait_for_timeout(100); pg.click('#soMenu [data-som=sortida]'); pg.wait_for_timeout(150)
    comprova(pg.locator('#soBar .sobtn').count() == 2, 'el doble clic no registra una segona sortida')
    # avís als 7 minuts
    pg.evaluate(f"(()=>{{const x=cur().sortides.find(z=>z.st==='{stid}');x.ini=Date.now()-8*60000;pintaSortides()}})()"); pg.wait_for_timeout(100)
    comprova(pg.locator('#soAvis .soav').count() == 1 and 'Porta 8 minuts' in pg.inner_text('#soAvis'), 'no surt l\'avís als 7 minuts')
    comprova(pg.locator('#soBar .sobtn.tard').count() == 1, 'el botó no es posa vermell')
    comprova(pg.evaluate('soLoop!==null'), 'el cucut no sona en bucle amb l\'avís')
    pg.click('#soAvis [data-soesp]'); pg.wait_for_timeout(100)
    comprova(pg.locator('#soAvis .soav').count() == 0, 'Esperem no amaga l\'avís')
    comprova(pg.evaluate('soLoop===null'), 'el cucut no para amb «Esperem»')
    comprova(pg.evaluate("[...soAvisats.values()].some(v=>v>Date.now()+170000&&v<Date.now()+190000)"), 'Esperem no torna a avisar al cap de 3 minuts')
    pg.evaluate("soAvisats.forEach((v,k)=>{if(!String(k).startsWith('o:'))soAvisats.set(k,Date.now()-1000)});pintaSortides()"); pg.wait_for_timeout(100)
    comprova(pg.locator('#soAvis .soav').count() == 1, 'no torna a avisar després d\'Esperem')
    pg.click('#soAvis .soav button:has-text("Ja ha tornat")'); pg.wait_for_timeout(150)
    comprova(pg.locator('#soAvis .soav').count() == 0 and pg.locator('#soBar .sobtn').count() == 1, '«Ja ha tornat» no tanca la sortida')
    comprova(pg.evaluate('soLoop===null'), 'el cucut no para amb «Ja ha tornat»')
    pg.click('#soBar .sobtn'); pg.wait_for_timeout(150)
    comprova(pg.locator('#soBar .sobtn').count() == 0, 'clicar el botó de la barra no registra la tornada')
    r = pg.evaluate("cur().sortides.map(x=>[x.tipus,!!x.fi,Math.round((x.fi-x.ini)/60000)])")
    comprova(sorted(r) == sorted([['wc', True, 8], ['sortida', True, 0]]), f'registre: {r}')
    # tres o més fora: un sol botó agrupat amb la llista
    pg.evaluate("(()=>{const s=cur();s.students.slice(2,6).forEach((st,i)=>s.sortides.push({id:'g'+i,st:st.id,tipus:'wc',ini:Date.now()-(i+1)*60000,fi:null}));pintaSortides()})()")
    comprova(pg.locator('#soBar .sobtn').count() == 1 and '4 fora' in pg.inner_text('#soBar'), 'amb 4 fora no surt un sol botó agrupat')
    alt = pg.evaluate("document.querySelector('header').getBoundingClientRect().height")
    comprova(alt <= 60, f'la barra es descuadra (alçada {alt})')
    pg.click('#soGrup'); pg.wait_for_timeout(100)
    comprova(pg.locator('#soLlista .soit').count() == 4, 'la llista no mostra els 4 alumnes')
    captura(pg, 'sortides_grup')
    pg.locator('#soLlista .soit').first.locator('button').click(); pg.wait_for_timeout(100)
    comprova('3 fora' in pg.inner_text('#soBar') and pg.locator('#soLlista .soit').count() == 3, '«Ha tornat» de la llista no funciona')
    pg.evaluate("cur().sortides.filter(x=>!x.fi).forEach(x=>soTorna(cur(),x.id))")
    comprova(pg.locator('#soBar .sobtn').count() == 0, 'no es buida la barra')
    # configuració dels minuts: el resum de ⚙ s'actualitza en el moment
    pg.click('.tabic[data-t=config]'); pg.wait_for_timeout(150); pg.locator('details[data-cfg=sortides] > summary').click()
    pg.fill('#kSoMin', '12'); pg.locator('details[data-cfg=sortides] > summary').click(); pg.wait_for_timeout(150)
    comprova(pg.evaluate('state.sortidesMin') == 12 and pg.inner_text('details[data-cfg=sortides] .cres') == 'avís als 12 min', 'el resum dels minuts no s\'actualitza')
    pg.click('.tabic[data-t=config]'); pg.wait_for_timeout(150)
    pg.evaluate("state.sortidesMin=10;save()"); pg.evaluate(f"(()=>{{cur().sortides.push({{id:'q',st:'{stid}',tipus:'wc',ini:Date.now()-8*60000,fi:null}});pintaSortides()}})()")
    comprova(pg.locator('#soAvis .soav').count() == 0, 'avisa als 8 minuts amb l\'avís posat a 10')
    pg.evaluate("soTorna(cur(),'q')")
    # consulta
    pg.evaluate("obreSortides()"); pg.wait_for_timeout(150)
    txt = pg.inner_text('#soW')
    tot = pg.evaluate(f"Math.floor(cur().sortides.filter(x=>x.st==='{stid}').reduce((a,x)=>a+x.fi-x.ini,0)/60000)")
    comprova('Per alumne' in txt and snom in txt and f'{tot} min' in txt, f'la consulta no mostra el resum per alumne ({tot} min)')
    comprova(pg.evaluate("textSortides().split('\\n').length") >= 8, 'el text per copiar és incomplet')
    if NPM:
        n = pg.evaluate("(async()=>{const {sub,llista}=soFiltrades();const d=await pdfSortides(sub,llista);return d.output('arraybuffer').byteLength})()")
        comprova(n > 3000, 'el PDF de sortides no es genera')
    pg.click('#soX')
    # curs nou: les sortides del curs anterior s'esborren
    pg.evaluate("cur().sortides.push({id:'v',st:cur().students[0].id,tipus:'wc',ini:new Date((+cursKey().slice(0,4)-1)+'-11-10T10:00').getTime(),fi:new Date((+cursKey().slice(0,4)-1)+'-11-10T10:05').getTime()})")
    pg.evaluate("soCursNou();0"); pg.wait_for_timeout(200)
    comprova('curs passat' in pg.inner_text('#qTxt'), 'no pregunta per les sortides del curs anterior')
    pg.click('#qBtns button:has-text("Esborra-les")'); pg.wait_for_timeout(150)
    comprova(pg.evaluate("cur().sortides.some(x=>x.id==='v')") is False and pg.evaluate("cur().sortides.length") == 7, 'no s\'ha esborrat només el curs anterior')
    comprova(not pg.errs, 'errors JS: %s' % pg.errs)
    captura(pg, 'sortides')
    ctx.close()

CALC_JS = """(()=>{const s=novaSub('Prova càlcul','buida','🧪');s.categories=[
       {id:'kA',name:'Exàmens',sigla:'EX',color:'#E69F00',weight:60,method:'mean'},{id:'kB',name:'Treballs',sigla:'TR',color:'#009E73',weight:40,method:'mean'}];
     s.columns=[{id:'c1',name:'Ex1',type:'num',cat:'kA',max:10},{id:'c2',name:'Ex2',type:'num',cat:'kA',max:10},
       {id:'c3',name:'Tr1',type:'num',cat:'kB',max:20},{id:'c4',name:'Tr2',type:'num',cat:'kB',max:10}];
     s.students=[{id:'a1',nom:'Ada',cognoms:'Prova'},{id:'a2',nom:'Bru',cognoms:'Prova'},{id:'a3',nom:'Cesc',cognoms:'Prova'}];
     state.subjects.push(s);state.cur=s.id;
     setG(s,'c1','a1',6,1);setG(s,'c2','a1',8,1);setG(s,'c3','a1',10,1);setG(s,'c4','a1',7,1);
     setG(s,'c1','a2',8,1);setG(s,'c2','a2','F',1);setG(s,'c3','a2',20,1);
     setG(s,'c1','a3',9,1);setG(s,'c2','a3','FJ',1);save();render();return s.id})()"""
FINALS_JS = "cur().students.map(st=>{const f=finalDe(cur(),st);return f?Math.round(f.num*1000)/1000:null})"

@prova('No compta: una columna dins d\'una categoria es pot excloure del càlcul i es marca amb ⊘')
def p_nocompta(b):
    ctx, pg = pagina_local(b)
    pg.evaluate(CALC_JS); pg.wait_for_timeout(200)
    comprova(pg.evaluate(FINALS_JS) == [6.6, 6.4, 9], 'el punt de partida no és [6.6, 6.4, 9]')
    pg.locator('th.colh[data-col=c2]').dblclick(); pg.wait_for_timeout(150)
    comprova(pg.is_visible('#cComptaF') and pg.is_checked('#cCompta'), 'la casella «Compta per a la nota» no surt marcada en una Numèrica')
    pg.uncheck('#cCompta'); pg.click('#cOk'); pg.wait_for_timeout(200)
    comprova(pg.evaluate("cur().columns.find(c=>c.id==='c2').noCompta") is True, 'no es desa noCompta')
    # sense Ex2: Ada EX 6 · TR 6 → 6 · Bru EX 8 · TR 10 → 8.8 · Cesc EX 9 → 9
    comprova(pg.evaluate(FINALS_JS) == [6, 8.8, 9], f'finals amb Ex2 exclosa: {pg.evaluate(FINALS_JS)}')
    th = pg.locator('th.colh[data-col=c2]')
    comprova('nopond' in th.get_attribute('class') and '⊘' in th.inner_text() and 'No compta' in th.get_attribute('title'), 'la capçalera no porta el signe ⊘')
    comprova(th.locator('.hn').evaluate("e=>getComputedStyle(e).fontStyle") == 'normal' and th.evaluate("e=>getComputedStyle(e).backgroundColor") != 'rgb(236, 236, 236)', 'la capçalera encara surt grisa o en cursiva')
    comprova(th.locator('.npx').evaluate("e=>getComputedStyle(e).color") == 'rgb(153, 153, 153)', 'el símbol ⊘ no és gris')
    comprova(pg.evaluate("cur().columns.find(c=>c.id==='c2').cat") == 'kA', 'la columna ha sortit de la categoria')
    # tornar a comptar
    pg.locator('th.colh[data-col=c2]').dblclick(); pg.wait_for_timeout(150); pg.check('#cCompta'); pg.click('#cOk'); pg.wait_for_timeout(200)
    comprova(pg.evaluate(FINALS_JS) == [6.6, 6.4, 9], 'en tornar a marcar-la no torna a comptar')
    # columna nova sense categoria: casella desactivada
    pg.evaluate("obreCol(null)"); pg.wait_for_timeout(100); pg.select_option('#cCat', '')
    comprova(pg.is_disabled('#cCompta') and 'Sense categoria' in pg.inner_text('#cComptaF'), 'sense categoria la casella no queda desactivada')
    pg.select_option('#cTipus', 'check'); pg.wait_for_timeout(50)
    comprova(not pg.is_checked('#cCompta'), 'el Check no surt desmarcat per defecte')
    pg.click('#cCanc')
    # vista alumne en detall
    pg.evaluate("cur().columns.find(c=>c.id==='c2').noCompta=true;tab='resum';render()"); pg.wait_for_timeout(150)
    pg.click('#aVA'); pg.select_option('#vaMode', 'detall'); pg.wait_for_timeout(150)
    comprova('no compta' in pg.inner_text('.vacard'), 'la vista alumne no marca la columna que no compta')
    if NPM:
        n = pg.evaluate("(async()=>{const d=await fesPDF([cur()],false);return d.output('arraybuffer').byteLength})()")
        comprova(n > 5000, 'el PDF falla amb una columna que no compta')
    comprova(not pg.errs, 'errors JS: %s' % pg.errs)
    ctx.close()

@prova('«No ava»: s\'escriu com nav/noava/no ava, es veu taronja i no compta a la mitjana')
def p_noava(b):
    ctx, pg = pagina_local(b)
    pg.evaluate(CALC_JS); pg.wait_for_timeout(200)
    for i, txt in enumerate(['nav', 'noava', 'No Ava']):
        cel = pg.locator('td[data-c=c4] input.g').nth(i)
        cel.click(); cel.fill(txt); cel.press('Tab'); pg.wait_for_timeout(120)
    vals = pg.evaluate("cur().students.map(st=>getG(cur(),'c4',st.id))")
    comprova(vals == ['NAV', 'NAV', 'NAV'], f'valors desats: {vals}')
    cel = pg.locator('td[data-c=c4]').first
    comprova(cel.locator('input').input_value() == 'no ava', 'la cel·la no mostra «no ava»')
    comprova('vNAV' in cel.get_attribute('class') and cel.locator('input').evaluate("e=>getComputedStyle(e).color") == 'rgb(217, 72, 15)', 'no surt en taronja')
    # Ada tenia Tr2=7; ara no compta: TR = 5 → final 0.6*7+0.4*5 = 6.2
    comprova(pg.evaluate(FINALS_JS) == [6.2, 6.4, 9], f'finals: {pg.evaluate(FINALS_JS)}')
    # assoliments: desplegable amb «no ava»
    pg.evaluate("(()=>{const s=cur();s.columns.push({id:'c5',name:'Act',type:'ass',cat:'kB'});save();rLlibreta()})()"); pg.wait_for_timeout(150)
    sel = pg.locator('td[data-c=c5] select.g').first
    comprova('no ava' in sel.inner_text(), 'el desplegable d\'assoliments no té «no ava»')
    sel.select_option('NAV'); pg.wait_for_timeout(150)
    comprova(pg.evaluate("getG(cur(),'c5','a1')") == 'NAV' and pg.evaluate(FINALS_JS)[0] == 6.2, 'triar «no ava» al desplegable compta o no es desa')
    comprova(pg.evaluate("textCella(cur(),cur().columns.find(c=>c.id==='c4'),cur().students[0])") == 'no ava', 'al PDF no surt «no ava»')
    # d'una altra llibreta
    r = pg.evaluate("""(()=>{const src=cur(),d=JSON.parse(JSON.stringify(src));d.id='dup';d.name='Còpia';d.columns=[{id:'e1',name:'Ext',type:'ext',cat:'kA',src:src.id,item:'c4'}];d.grades={};
        state.subjects.push(d);const r=resolveExt(d,d.columns[0],d.students[0]);const f=finalDe(d,d.students[0]);return [r&&r.label,r&&r.k,f]})()""")
    comprova(r == ['no ava', 'nav', None], f'«D\'una altra llibreta»: {r}')
    comprova(not pg.errs, 'errors JS: %s' % pg.errs)
    ctx.close()

@prova('Opcions: desplegable propi, colors, recompte, comptar per a la nota, llistes i PDF')
def p_opcions(b):
    ctx, pg = pagina_local(b)
    pg.evaluate(CALC_JS); pg.wait_for_timeout(200)
    pg.evaluate("obreCol(null)"); pg.wait_for_timeout(100)
    comprova(pg.locator('#cTipus option[value=icones]').evaluate("e=>e.hidden"), 'les Icones encara es proposen per a columnes noves')
    pg.select_option('#cTipus', 'opc'); pg.wait_for_timeout(100)
    comprova(pg.locator('#cOpcL .opcr').count() == 3 and not pg.is_checked('#cCompta'), 'el tipus Opcions no surt amb 3 opcions i sense comptar')
    pg.fill('#cNom', 'Dossier'); pg.select_option('#cCat', 'kB')
    pg.click('#cOpcAf'); pg.locator('#cOpcL input').nth(3).fill('Copiat')
    pg.locator('#cOpcL [data-opcc="3"][data-c="#BBDEFB"]').click()
    pg.click('#cOk'); pg.wait_for_timeout(200)
    c = pg.evaluate("cur().columns.find(c=>c.type==='opc')")
    comprova(c and [o['t'] for o in c['opcions']] == ['Lliurat', 'Tard', 'No lliurat', 'Copiat'] and c['opcions'][3]['col'] == '#BBDEFB' and not c.get('compta'), f'columna: {c}')
    cid = c['id']; ids = [o['id'] for o in c['opcions']]
    comprova(pg.evaluate(FINALS_JS) == [6.6, 6.4, 9], 'una columna Opcions informativa ha canviat la mitjana')
    sel = pg.locator(f'td[data-c="{cid}"] select.g')
    sel.nth(0).select_option(ids[0]); pg.wait_for_timeout(150)
    pg.locator(f'td[data-c="{cid}"] select.g').nth(1).select_option(ids[1]); pg.wait_for_timeout(150)
    pg.locator(f'td[data-c="{cid}"] select.g').nth(2).select_option(ids[0]); pg.wait_for_timeout(150)
    comprova(pg.evaluate(f"cur().students.map(st=>getG(cur(),'{cid}',st.id))") == [ids[0], ids[1], ids[0]], 'les opcions no es desen')
    comprova(pg.locator(f'td[data-c="{cid}"]').first.evaluate("e=>getComputedStyle(e).backgroundColor") == 'rgb(200, 230, 201)', 'la cel·la no agafa el color de l\'opció')
    pg.evaluate("cur().settings.filaTotals=true;save();rLlibreta()"); pg.wait_for_timeout(150)
    tot = pg.locator(f'tfoot td').filter(has_text='Lliurat').inner_text()
    comprova('2 Lliurat' in tot and '1 Tard' in tot, f'recompte a la fila de totals: {tot}')
    comprova('⊘' in pg.locator(f'th.colh[data-col="{cid}"]').inner_text(), 'la columna informativa dins de categoria no porta ⊘')
    # que compti: Lliurat → AN (7,5 si assVals per defecte), Tard → AS
    pg.locator(f'th.colh[data-col="{cid}"]').dblclick(); pg.wait_for_timeout(150); pg.check('#cCompta'); pg.wait_for_timeout(100)
    comprova(pg.locator('#cMapa select').count() == 4, 'no surt la conversió de cada opció a assoliment')
    pg.click('#cOk'); pg.wait_for_timeout(200)
    r = pg.evaluate("(()=>{const s=cur(),k=s.categories.find(x=>x.id==='kB');return s.students.map(st=>{const r=catResult(s,k,st);return r&&r.label})})()")
    comprova(r[2] is not None, f'en comptar, l\'opció no entra a la categoria: {r}')
    # enganxar text
    comprova(pg.evaluate(f"valorDe(cur(),cur().columns.find(c=>c.id==='{cid}'),'no LLIURAT').val") == ids[2], 'enganxar el text de l\'opció no funciona')
    comprova(pg.evaluate(f"textCella(cur(),cur().columns.find(c=>c.id==='{cid}'),cur().students[1])") == 'Tard', 'al PDF no surt el nom de l\'opció')
    # treure una opció en ús demana confirmació
    pg.locator(f'th.colh[data-col="{cid}"]').dblclick(); pg.wait_for_timeout(150)
    pg.locator('#cOpcL [data-optx="1"]').click(); pg.click('#cOk'); pg.wait_for_timeout(150)
    comprova(pg.is_visible('#dlgQ') and 'quedaran buides' in pg.inner_text('#qTxt'), 'no avisa en treure una opció en ús')
    pg.click('#qBtns button:has-text("Continua")'); pg.wait_for_timeout(200)
    comprova(pg.evaluate(f"getG(cur(),'{cid}','a2')") is None and len(pg.evaluate(f"cur().columns.find(c=>c.id==='{cid}').opcions")) == 3, 'l\'opció treta no buida les cel·les')
    captura(pg, 'opcions')
    # llista sense notes
    pg.evaluate("(()=>{const s=novaSub('Excursió','llista','📋');s.tipus='llista';s.students=[{id:'x1',nom:'Ada',cognoms:'Prova'}];s.columns=[{id:'o1',name:'Autorització',type:'opc',cat:'',opcions:[{id:'p',t:'Portada',col:''},{id:'n',t:'Pendent',col:''}]}];state.subjects.push(s);state.cur=s.id;save();tab='llibreta';render()})()")
    pg.wait_for_timeout(150)
    comprova(pg.locator('td[data-c=o1] select.g').count() == 1, 'la columna Opcions no funciona en una llista')
    comprova(not pg.errs, 'errors JS: %s' % pg.errs)
    ctx.close()

@prova('Columnes amagades: la llista no queda oberta tapant la taula')
def p_amagades(b):
    ctx, pg = pagina_local(b)
    pg.locator('th.colh[data-col]').nth(2).dblclick(); pg.wait_for_timeout(150); pg.check('#cOcu'); pg.click('#cOk'); pg.wait_for_timeout(300)
    comprova(pg.locator('#chipOc').is_visible() and not pg.locator('#ocList').is_visible(), 'la llista de columnes amagades queda oberta')
    pg.click('#chipOc'); pg.wait_for_timeout(100)
    comprova(pg.locator('#ocList').is_visible(), 'clicar el xip no obre la llista')
    pg.mouse.click(700, 500); pg.wait_for_timeout(100)
    comprova(not pg.locator('#ocList').is_visible(), 'clicar fora no tanca la llista')
    pg.click('#chipOc'); pg.locator('[data-obtot]').click(); pg.wait_for_timeout(200)
    comprova(pg.locator('#chipOc').count() == 0, '«Mostra-les totes» no torna a mostrar les columnes')
    ctx.close()

@prova('«És el teu ordinador?»: pregunta un cop, mode temporal en un ordinador aliè i botó d\'esborrar')
def p_ordinador(b):
    FILES = {}
    def ctx_nou():
        c = b.new_context(viewport={'width': 1400, 'height': 850}); c.add_init_script(INIT_BASE); c.route('**/*', google_amb(FILES)); return c
    # 1) ordinador propi: pregunta, «Sí» queda recordat i la còpia va a localStorage
    c1 = ctx_nou(); pg = c1.new_page(); pg.goto(URL); pg.wait_for_timeout(300); pg.click('#lgEntra'); pg.wait_for_timeout(300)
    comprova(pg.is_visible('#dlgQ') and 'És el teu ordinador' in pg.inner_text('#qTit'), 'no pregunta si l\'ordinador és propi')
    pg.click('#qBtns button:has-text("Sí, és meu")'); pg.wait_for_timeout(1500)
    comprova(pg.evaluate("localStorage.getItem('llibreta-ordinador')") == 'meu' and pg.evaluate("!!localStorage.getItem('llibreta-drive-cache')"), 'en un ordinador propi no es guarda la còpia')
    comprova(not pg.locator('#alieTag').is_visible(), 'surt l\'etiqueta d\'ordinador aliè en un de propi')
    pg.reload(); pg.wait_for_timeout(300); pg.click('#lgEntra'); pg.wait_for_timeout(1200)
    comprova(not (pg.is_visible('#dlgQ') and 'És el teu ordinador' in pg.inner_text('#qTit')), 'torna a preguntar en un ordinador que ja és propi: '+(pg.inner_text('#qTit') if pg.is_visible('#dlgQ') else ''))
    # botó d'esborrar
    pg.evaluate("tab='config';render()"); pg.wait_for_timeout(150); pg.evaluate("document.querySelector('details[data-cfg=dades]').open=true")
    pg.click('#dEsbOrd'); pg.click('#qBtns button:has-text("Esborra")'); pg.wait_for_timeout(300)
    comprova(pg.evaluate("localStorage.getItem('llibreta-drive-cache')") is None and pg.evaluate("localStorage.getItem('llibreta-ordinador')") is None, 'el botó no esborra la còpia')
    pg.evaluate("(()=>{const s=cur(),c=s.columns.find(c=>c.type==='num');setG(s,c.id,s.students[0].id,2)})()"); pg.wait_for_timeout(300)
    comprova(pg.evaluate("localStorage.getItem('llibreta-drive-cache')") is None, 'després d\'esborrar es torna a guardar al navegador')
    c1.close()
    # 2) ordinador aliè: res a localStorage, etiqueta visible i avís en sortir
    c2 = ctx_nou(); pg = c2.new_page(); pg.goto(URL); pg.wait_for_timeout(300); pg.click('#lgEntra'); pg.wait_for_timeout(300)
    pg.click('#qBtns button:has-text("No, és")'); pg.wait_for_timeout(1500)
    comprova(pg.evaluate("localStorage.getItem('llibreta-drive-cache')") is None and pg.evaluate("!!sessionStorage.getItem('llibreta-drive-cache')"), 'en un ordinador aliè la còpia no va només a la pestanya')
    comprova(pg.evaluate("localStorage.getItem('llibreta-email')") is None, 'en un ordinador aliè es desa el correu')
    comprova(pg.locator('#alieTag').is_visible(), 'no surt l\'etiqueta «Ordinador d\'una altra persona»')
    pg.evaluate("(()=>{const s=cur(),c=s.columns.find(c=>c.type==='num');setG(s,c.id,s.students[0].id,3)})()"); pg.wait_for_timeout(2500)
    pg.click('#btnSurt') if pg.locator('#btnSurt').is_visible() else pg.evaluate("$('#btnSurt').click()"); pg.wait_for_timeout(800)
    comprova(pg.is_visible('#dlgQ') and 'sessió de Google' in pg.inner_text('#qTit'), 'en sortir no recorda tancar la sessió de Google')
    comprova(pg.evaluate("sessionStorage.getItem('llibreta-drive-cache')") is None, 'en sortir queda la còpia a la pestanya')
    c2.close()
    # 3) la pestanya nova (sessió nova) en l'ordinador aliè torna a preguntar i no hi ha cap còpia
    c3 = ctx_nou(); pg = c3.new_page(); pg.goto(URL); pg.wait_for_timeout(300)
    comprova(not pg.locator('#lgOff').is_visible(), 'surt «Continua sense connexió» sense cap còpia')
    c3.close()

@prova('Arxiu: cursos del més nou al més antic, curs automàtic, llistes distingides i mida del fitxer')
def p_arxiu2(b):
    ctx, pg = pagina_local(b)
    pg.evaluate("""(()=>{const mk=(n,t,cat)=>{const s=novaSub(n,t==='llista'?'llista':'eso','📗');if(t==='llista')s.tipus='llista';s.archived={cat,data:'2025-06-30'};state.subjects.push(s)};
      mk('Bio vella','notes','Curs 2024-25');mk('Excursió','llista','Curs 2025-26');mk('Bio','notes','Curs 2025-26');mk('Reunions','llista','Altres');mk('Solta','notes','');save();tab='arxiu';render()})()""")
    pg.wait_for_timeout(200)
    h = pg.locator('#main .seccio h2').all_inner_texts()
    ordre = [x.split('✎')[0].replace('📁', '').strip() for x in h]
    comprova(ordre == ['Curs 2025-26', 'Curs 2024-25', 'Altres', 'Sense categoria'], f'ordre de les carpetes: {ordre}')
    primera = pg.locator('#main .seccio').first.locator('.fitxa').all_inner_texts()
    comprova('Bio' in primera[0] and 'notes' in primera[0] and 'llista' in primera[1], f'dins del curs, llibretes i llistes: {primera}')
    pg.evaluate("tab='llibreta';render();obreArx()"); pg.wait_for_timeout(100)
    k = pg.evaluate('cursKey()')
    comprova(pg.input_value('#aCat') == 'Curs ' + k, 'en arxivar no proposa el curs actual')
    pg.fill('#aCat', ''); pg.click('#aOk'); pg.wait_for_timeout(200)
    comprova(pg.evaluate("state.subjects.find(s=>s.name==='EXEMPLE').archived.cat") == 'Curs ' + k, 'arxivar sense carpeta no posa el curs')
    pg.evaluate("desarxiva(state.subjects.find(s=>s.name==='EXEMPLE').id);tab='config';render()"); pg.wait_for_timeout(150)
    pg.evaluate("document.querySelector('details[data-cfg=dades]').open=true")
    comprova(re.search(r'\d+ kB', pg.inner_text('#dMida') or ''), 'no surt la mida del fitxer a ⚙ › Dades')
    comprova(not pg.errs, 'errors JS: %s' % pg.errs)
    ctx.close()

# ---------------------------------------------------------------- execució
with sync_playwright() as p:
    b = p.chromium.launch()
    p_mobil.dev = p.devices['iPhone 13']
    proves = [p_arrencada, p_mitjanes, p_calcul, p_edicio, p_desat_local, p_drive, p_anotacions,
              p_avaluacio, p_arxiu, p_llista, p_calculadora, p_mobil, p_pdf, p_sri, p_textllarg, p_sons, p_bloc, p_migra_bloc, p_sortides, p_nocompta, p_noava, p_opcions, p_amagades, p_ordinador, p_arxiu2]
    if GENERA_REF: proves = [p_mitjanes]
    if NOMES: proves = [f for f in proves if any(n in f.__name__ for n in NOMES)]
    for f in proves: f(b)
    b.close()
srv.shutdown()

if getattr(p_sons, 'info', None) and '-v' in args: print(p_sons.info)
if GENERA_REF:
    print('Referència desada a', REF); sys.exit(0)
ok = sum(r[0] == 'OK' for r in RESULTATS); fa = [r for r in RESULTATS if r[0] == 'FALLA']; om = [r for r in RESULTATS if r[0] == 'OMESA']
for est, nom, msg in RESULTATS:
    print(f"{'✔' if est=='OK' else '✘' if est=='FALLA' else '–'} {nom}" + (f'\n    {msg}' if msg else ''))
print(f'\n{ok} correctes · {len(fa)} fallades · {len(om)} omeses · fitxer provat: {FITXER}')
sys.exit(1 if fa else 0)
