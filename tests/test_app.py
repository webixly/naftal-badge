"""End-to-end tests for naftal-badges.html (Playwright, headless Chromium).
Usage: python test_app.py <out_dir>"""
import json, pathlib, sys, io, re
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = (ROOT / 'naftal-badges.html').as_uri()
OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'tests' / 'out')
OUT.mkdir(parents=True, exist_ok=True)

results = []
def check(name, cond, info=''):
    results.append((name, bool(cond), info))
    print(('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else ''))

# fixtures
img = Image.new('RGB', (600, 800), '#7a9cc6'); d = ImageDraw.Draw(img)
d.ellipse((200, 150, 400, 380), fill='#e8c3a0'); d.rectangle((150, 420, 450, 800), fill='#203050')
photo_path = OUT / 'photo.jpg'; img.save(photo_path)
csv_path = OUT / 'import.csv'
csv_path.write_text('﻿Matricule;Nom;Prénom;Fonction;Structure;Affectation;Type;Valide au;Groupe sanguin\n'
                    '20001;BENALI;Karim;Chef de service;Direction Finances;Siège;Carte Professionnelle;31/12/2027;0 +\n'
                    '20002;"SAÏDI; KHELIL";Amina;Stagiaire;Département Informatique;Dépôt Caroubier;Carte Stagiaire;01/01/2020;ab neg\n'
                    ';SANSMAT;X;;;;;;\n', encoding='utf-8')

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={'width': 1600, 'height': 960}, accept_downloads=True)
    page = ctx.new_page()
    errors = []
    page.on('console', lambda m: m.type == 'error' and errors.append(m.text))
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(APP); page.wait_for_function('window.__badgesReady === true'); page.wait_for_timeout(600)

    # 1. boot
    check('boot: preview card rendered', page.locator('#previewCard').count() == 1)
    check('boot: serial pre-filled', re.match(r'^\d{4}-0001$', page.input_value('#fSerial')), page.input_value('#fSerial'))
    check('boot: storage uses IndexedDB', page.evaluate("document.getElementById('storageInfo').textContent").find('limité') == -1)
    check('boot: default validity +12 months filled', page.input_value('#fValide') != '')
    check('validity: row shown when date set', page.locator('#previewCard .r5').count() == 1)
    page.fill('#fValide', ''); page.dispatch_event('#fValide', 'input'); page.wait_for_timeout(150)
    check('validity: row hidden when no date', page.locator('#previewCard .r5').count() == 0)
    page.click('[data-valid="12"]'); page.wait_for_timeout(150)
    check('validity: row back after picking date', page.locator('#previewCard .r5').count() == 1)
    check('credit: developer signature visible', page.is_visible('#credit') and 'Aymen' in page.inner_text('#credit'))
    page.screenshot(path=str(OUT / '01_empty.png'))

    # 2. Code128 table + encoding vs JsBarcode reference
    tbl = page.evaluate('window.__badges.C128')
    sums_ok = all(sum(map(int, s)) == 11 for s in tbl[:106]) and sum(map(int, tbl[106])) == 13
    check('code128: table has 107 patterns with correct widths', len(tbl) == 107 and sums_ok and len(set(tbl)) == 107)
    page.add_script_tag(url='https://cdn.jsdelivr.net/npm/jsbarcode@3.11.5/dist/JsBarcode.all.min.js')
    cmp = page.evaluate("""() => {
      const toBits = (svg) => { // read rects from an svg -> '1/0' module string
        const rects=[...svg.querySelectorAll('rect')].filter(r=>r.getAttribute('style')?.includes('fill:#000')||r.getAttribute('fill')==='#000'||!r.getAttribute('style'));
        return rects; };
      const mine = (t) => { const pat = window.__badges.code128Codes(t).map(c=>window.__badges.C128[c]).join(''); let s='',b=1; for(const w of pat){s+=String(b).repeat(+w); b^=1;} return s; };
      const ref = (t, fmt) => { const svg=document.createElementNS('http://www.w3.org/2000/svg','svg'); JsBarcode(svg,t,{format:fmt,width:1,margin:0,displayValue:false});
        const g=svg.querySelector('g'); const rects=[...g.querySelectorAll('rect')]; let total=0; rects.forEach(r=>{total=Math.max(total,+r.getAttribute('x')+ +r.getAttribute('width'))});
        const bits=Array(total).fill('0'); rects.forEach(r=>{for(let i=+r.getAttribute('x');i<+r.getAttribute('x')+ +r.getAttribute('width');i++)bits[i]='1'}); return bits.join(''); };
      const cases=[['12345','CODE128B'],['A-77','CODE128B'],['MANSOURI 2026','CODE128B'],['1234','CODE128C'],['000000','CODE128C'],['20001234','CODE128C']];
      return cases.map(([t,f])=>[t, mine(t)===ref(t,f)]);
    }""")
    check('code128: output identical to JsBarcode for 6 samples', all(ok for _, ok in cmp), str(cmp))

    # 3. validation
    check('photo: remove button hidden with no photo', not page.is_visible('#btnRemovePhoto'))
    page.click('#btnSave')
    check('validation: empty nom flagged', page.locator('#gNom.invalid').count() == 1)
    check('validation: empty matricule flagged', page.locator('#gMat.invalid').count() == 1)
    check('validation: nothing saved', page.evaluate('window.__badges.records.length') == 0)

    # 4. fill + photo + live preview
    page.fill('#fNom', 'Mansouri'); page.fill('#fPrenom', 'Yacine')
    page.fill('#fFonction', 'Ingénieur d\'études'); page.fill('#fStructure', 'Département Informatique')
    page.fill('#fMatricule', '12345')
    page.set_input_files('#fPhoto', str(photo_path)); page.wait_for_selector('#previewCard .c-photo img')
    check('live: nom on card (uppercase via CSS)', page.inner_text('#previewCard .r1 .v').strip().upper() == 'MANSOURI')
    check('live: barcode number', page.inner_text('#previewCard .c-barnum') == '12345')
    check('live: invalid flags cleared', page.locator('.f.invalid').count() == 0)
    check('blood: nothing on card when not set', page.locator('#previewCard .c-blood').count() == 0)
    page.select_option('#fGroupe', 'AB-'); page.wait_for_timeout(100)
    check('blood: shown on card (true minus sign)', page.inner_text('#previewCard .c-blood').strip() == 'AB\u2212')
    page.select_option('#fGroupe', 'O+'); page.wait_for_timeout(100)
    geo = page.evaluate("""(()=>{const r=s=>document.querySelector('#previewCard '+s).getBoundingClientRect(); const b=r('.c-blood'), bar=r('.c-bar'), band=r('.c-siege'), c=r('');
      return [b.left>=bar.right, b.right<=band.left, b.bottom<=c.bottom]})()""")
    check('blood: between barcode and blue band, inside card', all(geo), str(geo))
    check('blood: normalisation', page.evaluate("['o +','0+','AB pos','b\u2212','a neg','X+',''].map(window.__badges.normBlood)") == ['O+', 'O+', 'AB+', 'B-', 'A-', '', ''])
    dims = page.evaluate("(()=>{const i=document.querySelector('#previewCard .c-photo img'); return [i.naturalWidth,i.naturalHeight]})()")
    check('photo: cropped to 22.7x26 ratio', abs(dims[0] / dims[1] - 22.7 / 26) < 0.01, str(dims))
    check('photo: remove button visible after upload', page.is_visible('#btnRemovePhoto'))
    check('form: dirty indicator', 'dirty' in page.get_attribute('#formMode', 'class'))

    # 5. save
    page.keyboard.press('Control+s'); page.wait_for_timeout(300)
    check('save (Ctrl+S): 1 record', page.evaluate('window.__badges.records.length') == 1)
    check('save: registry row active', page.locator('.row.active').count() == 1)
    check('save: dirty cleared', 'dirty' not in page.get_attribute('#formMode', 'class'))
    page.screenshot(path=str(OUT / '02_saved.png'))
    page.locator('#previewCard').screenshot(path=str(OUT / '03_card.png'))

    # 6. persistence
    page.reload(); page.wait_for_function('window.__badgesReady === true'); page.wait_for_timeout(300)
    check('persist: record survives reload', page.locator('.row').count() == 1)
    check('persist: next serial is 0002', page.input_value('#fSerial').endswith('-0002'))
    check('persist: photo kept', page.locator('.row img').count() == 1)
    check('persist: blood group saved', page.evaluate('window.__badges.records[0].groupe') == 'O+')

    # 7. duplicate matricule warning
    page.fill('#fNom', 'Test'); page.fill('#fMatricule', '12345'); page.click('#btnSave')
    page.wait_for_selector('#dlgConfirm[open]')
    check('duplicate matricule: confirm dialog shown', 'Matricule déjà utilisé' in page.inner_text('#cfTitle'))
    page.click('#cfCancel'); page.wait_for_timeout(150)
    check('duplicate matricule: cancel keeps 1 record', page.evaluate('window.__badges.records.length') == 1)

    # 8. second record, expired, long names -> autofit
    page.fill('#fNom', 'Boumediene-Abdelmoumene'); page.fill('#fPrenom', 'Abdelkader Mohamed Amine Seddik')
    page.fill('#fFonction', 'Responsable de la maintenance des installations de stockage')
    page.fill('#fStructure', 'Direction de la Distribution et de la Logistique Régionale')
    page.fill('#fMatricule', 'A-77'); page.fill('#fValide', '2024-01-01'); page.fill('#fAffect', 'Dépôt Caroubier')
    check('date warning for past date', 'exp' in page.get_attribute('#dateWarn', 'class'))
    over = page.evaluate("""[...document.querySelectorAll('#previewCard [data-fit]')].map(e=>[e.className, e.scrollWidth<=e.clientWidth+1 || e.style.textOverflow==='ellipsis', e.style.fontSize])""")
    check('autofit: long texts fit their boxes', all(o[1] for o in over), str(over))
    page.locator('#previewCard').screenshot(path=str(OUT / '04_card_long.png'))
    page.click('#btnSave'); page.wait_for_timeout(300)
    check('save 2nd record', page.evaluate('window.__badges.records.length') == 2)

    # 9. search + filters
    page.fill('#search', 'boumed'); page.wait_for_timeout(100)
    check('search: accent/case-insensitive', page.locator('.row').count() == 1)
    page.fill('#search', 'zzz'); check('search: empty state', page.locator('.empty').count() == 1)
    page.fill('#search', '')
    page.click('[data-filter="expired"]'); check('filter expired', page.locator('.row').count() == 1)
    page.click('[data-filter="valid"]'); check('filter valid', page.locator('.row').count() == 1)
    page.click('[data-filter="all"]'); check('filter all', page.locator('.row').count() == 2)

    # 10. open record with dirty guard
    page.fill('#fNom', 'Modifie')
    page.locator('.row').filter(has_text='MANSOURI').click()
    page.wait_for_selector('#dlgConfirm[open]')
    check('dirty guard: dialog on switching record', True)
    page.click('#cfOk'); page.wait_for_timeout(200)
    check('dirty guard: switched to MANSOURI', page.input_value('#fNom') == 'Mansouri')
    check('edit mode title', page.inner_text('#formTitle') == 'Modifier le badge')

    # 11. edit keeps serial
    serial = page.input_value('#fSerial')
    page.fill('#fFonction', 'Chef de projet'); page.click('#btnSave'); page.wait_for_timeout(200)
    rec = page.evaluate("window.__badges.records.find(r=>r.nom==='Mansouri')")
    check('edit: updated in place, serial kept', rec['fonction'] == 'Chef de projet' and rec['serial'] == serial and page.evaluate('window.__badges.records.length') == 2)

    # 12. duplicate as template (double-click)
    page.locator('.row').filter(has_text='MANSOURI').dblclick(); page.wait_for_timeout(200)
    check('template: name cleared, structure kept', page.input_value('#fNom') == '' and page.input_value('#fStructure') == 'Département Informatique')
    check('template: blood group cleared (personal data)', page.input_value('#fGroupe') == '')
    page.click('#btnNew'); page.wait_for_timeout(150)

    # 13. CSV import
    page.set_input_files('#fileImport', str(csv_path)); page.wait_for_timeout(500)
    recs = page.evaluate('window.__badges.records')
    names = sorted(r['nom'] for r in recs)
    check('csv import: 2 valid rows added, 1 skipped', len(recs) == 4 and 'SAÏDI; KHELIL' in names, str(names))
    saidi = next(r for r in recs if r['nom'].startswith('SAÏDI'))
    check('csv import: date dd/mm/yyyy converted', saidi['valide'] == '2020-01-01' and saidi['type'] == 'Carte Stagiaire')
    benali = next(r for r in recs if r['nom'] == 'BENALI')
    check('csv import: blood group column normalised', benali['groupe'] == 'O+' and saidi['groupe'] == 'AB-', f"{benali.get('groupe')} {saidi.get('groupe')}")
    check('csv import: unique serials', len({r['serial'] for r in recs}) == 4, str([r['serial'] for r in recs]))
    page.set_input_files('#fileImport', str(csv_path)); page.wait_for_timeout(400)
    check('csv re-import: duplicates ignored', page.evaluate('window.__badges.records.length') == 4)

    # 14. exports
    with page.expect_download() as dl: page.click('#btnExport')
    jpath = OUT / 'backup.json'; dl.value.save_as(jpath)
    data = json.loads(jpath.read_text(encoding='utf-8'))
    check('export json: 4 badges + settings', len(data['badges']) == 4 and 'settings' in data)
    page.click('#btnSettings'); page.wait_for_selector('#dlgSettings[open]')
    with page.expect_download() as dl: page.click('#btnExportCsv')
    cpath = OUT / 'export.csv'; dl.value.save_as(cpath)
    lines = cpath.read_text(encoding='utf-8-sig').strip().splitlines()
    check('export csv: header + 4 rows, BOM for Excel', len(lines) == 5 and lines[0].startswith('Matricule;'), str(len(lines)))
    check('export csv: blood group column', 'Groupe sanguin' in lines[0] and any(';O+;' in l for l in lines[1:]), lines[0])
    check('export json: blood group kept', any(b.get('groupe') == 'O+' for b in data['badges']))

    # 15. settings
    page.fill('#sDistrict', 'District Commercialisation Blida')
    page.uncheck('#sWm'); page.click('#settingsSave'); page.wait_for_timeout(300)
    check('settings: district on card', 'Blida' in page.inner_text('#previewCard .c-district'))
    check('settings: watermark removed', page.locator('#previewCard .c-wm').count() == 0)
    page.reload(); page.wait_for_function('window.__badgesReady === true'); page.wait_for_timeout(300)
    check('settings: persisted after reload', 'Blida' in page.inner_text('#previewCard .c-district'))
    check('credit: fixed photo embedded', page.evaluate("document.getElementById('creditPhoto').naturalWidth") == 160 and page.evaluate("document.getElementById('creditPhoto').src.startsWith('data:image/jpeg')"))
    check('credit: photo not changeable from UI', page.locator('#credit input[type=file], #credit button').count() == 0 and page.locator('#dlgSettings input[type=file]#sAuthorFile').count() == 0)
    check('credit: name not editable in settings', page.locator('#sAuthor').count() == 0 and 'Aymen' in page.inner_text('#credit'))
    check('icon: favicon embedded', page.evaluate("(()=>{const l=document.querySelector('link[rel=icon]'); return !!l && l.href.startsWith('data:image/png;base64,') && l.href.length>1000})()"))
    check('icon: favicon decodes 256px', page.evaluate("new Promise(r=>{const i=new Image();i.onload=()=>r(i.naturalWidth);i.onerror=()=>r(0);i.src=document.querySelector('link[rel=icon]').href})") == 256)
    check('icon: shown in topbar', page.is_visible('header .brand #appIcon') and page.evaluate("document.getElementById('appIcon').naturalWidth") == 200)
    check('credit: placed bottom-left in registry column', page.locator('aside.reg #credit').count() == 1 and page.evaluate("document.getElementById('credit').getBoundingClientRect().left") < 50)
    page.locator('#credit').screenshot(path=str(OUT / '11_credit.png'))
    page.click('#btnSettings'); page.fill('#sDistrict', 'District Commercialisation Alger'); page.check('#sWm'); page.click('#settingsSave'); page.wait_for_timeout(200)

    # 16. delete + undo
    page.locator('.row').first.locator('input[type=checkbox]').check()
    check('selection bar shows', page.locator('#selbar.show').count() == 1)
    page.click('#btnSelDelete'); page.wait_for_selector('#dlgConfirm[open]'); page.click('#cfOk'); page.wait_for_timeout(300)
    check('delete: 3 left', page.evaluate('window.__badges.records.length') == 3)
    page.click('#toastBtn'); page.wait_for_timeout(300)
    check('undo delete: 4 again', page.evaluate('window.__badges.records.length') == 4)
    page.reload(); page.wait_for_function('window.__badgesReady === true')
    check('undo persisted', page.evaluate('window.__badges.records.length') == 4)

    # 17. JSON re-import skips existing ids
    page.set_input_files('#fileImport', str(jpath)); page.wait_for_timeout(300)
    if page.locator('#dlgConfirm[open]').count(): page.click('#cfCancel'); page.wait_for_timeout(300)
    check('json re-import: no duplicates', page.evaluate('window.__badges.records.length') == 4)

    # 17b. verso: preview toggle + editable text in settings
    page.click('[data-face="back"]'); page.wait_for_timeout(200)
    check('verso: preview shows back', page.locator('#previewCard.back').count() == 1 and 'IMPORTANT' in page.inner_text('#previewCard .v-title'))
    check('verso: message + footer from template', 'STRICTEMENT PERSONNELLE' in page.inner_text('#previewCard .v-msg') and 'Ahmed Azouz' in page.inner_text('#previewCard .v-foot') and page.locator('#previewCard .v-rule').count() == 1)
    check('verso: spacing kept in footer', 'Tel : 023 75 14 01   Fax' in page.text_content('#previewCard .v-foot'))
    over = page.evaluate("""[...document.querySelectorAll('#previewCard .v-line[data-fit], #previewCard .v-title')].every(e => e.scrollWidth <= e.clientWidth + 1)""")
    check('verso: no text cut', over)
    page.click('#btnSettings'); page.wait_for_selector('#dlgSettings[open]')
    page.fill('#sVFoot', 'Naftal, Adresse test.\nTel : 000'); page.click('#settingsSave'); page.wait_for_timeout(300)
    check('verso: footer edited from settings', 'Adresse test' in page.inner_text('#previewCard .v-foot'))
    page.click('#btnSettings'); page.wait_for_selector('#dlgSettings[open]')
    page.click('#btnVersoReset'); page.click('#settingsSave'); page.wait_for_timeout(300)
    check('verso: reset to original text', 'Ahmed Azouz' in page.inner_text('#previewCard .v-foot'))
    page.fill('#fFonction', page.input_value('#fFonction') + ' '); page.wait_for_timeout(150)
    check('verso: typing in form returns to recto', page.locator('#previewCard.back').count() == 0 and page.get_attribute('[data-face="front"]', 'aria-pressed') == 'true')
    page.fill('#fFonction', page.input_value('#fFonction').rstrip())
    page.fill('#fNom', page.input_value('#fNom')); page.click('#flipper'); page.wait_for_timeout(900)
    check('flip: clicking the card turns it to verso (even right after typing)', page.evaluate("document.getElementById('flipper').classList.contains('is-back')") and page.get_attribute('[data-face="back"]', 'aria-pressed') == 'true')
    rot = page.evaluate("getComputedStyle(document.getElementById('flipper')).transform")
    check('flip: verso rotated 180deg in 3D', rot.startswith('matrix3d'), rot)
    page.click('[data-face="front"]'); page.wait_for_timeout(900)
    check('flip: Recto button turns it back', not page.evaluate("document.getElementById('flipper').classList.contains('is-back')") and page.locator('#previewCard.back').count() == 0)

    # 18. printing: CR80 single, then A4 batch -> real PDFs
    page.evaluate('() => { window.print = () => { window.__printed = (window.__printed||0)+1 } }')
    page.locator('.row').filter(has_text='MANSOURI').click(); page.wait_for_timeout(200)
    page.click('#btnPrint'); page.wait_for_selector('#dlgPrint[open]')
    page.check('input[name=pfmt][value=cr80]'); page.click('#printGo'); page.wait_for_timeout(1500)
    check('print cr80: window.print called', page.evaluate('window.__printed') == 1)
    check('print cr80: 1 card in print root', page.locator('#printRoot .card').count() == 1)
    check('print cr80: no black outline (avoids edge line on card printers)', page.locator('#printRoot .card.no-border').count() == 1)
    check('credit: not inside printed card', page.locator('#printRoot #credit').count() == 0)
    page.emulate_media(media='print')
    page.pdf(path=str(OUT / 'print_cr80.pdf'), prefer_css_page_size=True, print_background=True)
    page.emulate_media(media='screen')

    page.check('#selAll'); page.click('#btnSelPrint'); page.wait_for_selector('#dlgPrint[open]')
    page.check('input[name=pfmt][value=a4]'); page.click('#printGo'); page.wait_for_timeout(600)
    check('print a4: outline kept as cut guide', page.locator('#printRoot .card:not(.no-border)').count() == 4)
    check('print a4: 4 cards on 1 sheet with crop marks', page.locator('#printRoot .sheet').count() == 1 and page.locator('#printRoot .card').count() == 4 and page.locator('#printRoot .crop').count() == 18)
    page.emulate_media(media='print')
    page.pdf(path=str(OUT / 'print_a4.pdf'), prefer_css_page_size=True, print_background=True)
    page.emulate_media(media='screen')
    page.click('#selAll')
    # recto + verso, A4: front sheet then mirrored back sheet
    page.check('#selAll'); page.click('#btnSelPrint'); page.wait_for_selector('#dlgPrint[open]')
    page.check('input[name=pfmt][value=a4]'); page.select_option('#pSides', 'both'); page.click('#printGo'); page.wait_for_timeout(600)
    check('print a4 recto-verso: 2 sheets, 4 fronts + 4 backs', page.locator('#printRoot .sheet').count() == 2 and page.locator('#printRoot .sheet.front .card:not(.back)').count() == 4 and page.locator('#printRoot .sheet.back .card.back').count() == 4)
    lefts = page.evaluate("[...document.querySelectorAll('#printRoot .sheet.back .card')].slice(0,2).map(c => parseFloat(c.style.left))")
    check('print a4 recto-verso: backs mirrored for duplex', abs(lefts[0] - 105.0) < 0.05 and abs(lefts[1] - 19.4) < 0.05, str(lefts))
    page.emulate_media(media='print')
    page.pdf(path=str(OUT / 'print_a4_rv.pdf'), prefer_css_page_size=True, print_background=True)
    page.emulate_media(media='screen')
    page.click('#selAll')
    # recto + verso, CR80 single badge: 2 pages
    page.locator('.row').filter(has_text='MANSOURI').click(); page.wait_for_timeout(200)
    page.click('#btnPrint'); page.wait_for_selector('#dlgPrint[open]')
    check('print dialog: remembers recto-verso choice', page.input_value('#pSides') == 'both')
    page.check('input[name=pfmt][value=cr80]'); page.click('#printGo'); page.wait_for_timeout(800)
    cls = page.evaluate("[...document.querySelectorAll('#printRoot .card')].map(c => c.classList.contains('back'))")
    check('print cr80 recto-verso: front then back', cls == [False, True], str(cls))
    check('print cr80 recto-verso: no outline on back', page.locator('#printRoot .card.back.no-border').count() == 1)
    page.emulate_media(media='print')
    page.pdf(path=str(OUT / 'print_cr80_rv.pdf'), prefer_css_page_size=True, print_background=True)
    page.emulate_media(media='screen')
    page.click('#btnPrint'); page.wait_for_selector('#dlgPrint[open]')
    page.select_option('#pSides', 'back'); page.click('#printGo'); page.wait_for_timeout(600)
    check('print verso only: 1 back card', page.locator('#printRoot .card').count() == 1 and page.locator('#printRoot .card.back').count() == 1)
    page.click('#btnPrint'); page.wait_for_selector('#dlgPrint[open]')
    page.select_option('#pSides', 'front'); page.click('#printGo'); page.wait_for_timeout(400)


    # 19. app chrome screenshots at 3 widths, no horizontal scroll
    page.screenshot(path=str(OUT / '05_desktop.png'))
    for w, h, name in [(1100, 900, '06_laptop.png'), (390, 844, '07_mobile.png')]:
        page.set_viewport_size({'width': w, 'height': h}); page.wait_for_timeout(300)
        sw = page.evaluate('document.documentElement.scrollWidth')
        check(f'responsive {w}px: no horizontal scroll', sw <= w, f'scrollWidth={sw}')
        page.screenshot(path=str(OUT / name), full_page=(w < 500))
    check('no console errors', not errors, '; '.join(errors[:5]))
    ctx.close()

    # 20. legacy migration from the old version's localStorage
    ctx2 = browser.new_context()
    pg = ctx2.new_page()
    pg.goto(APP); pg.wait_for_function('window.__badgesReady === true')
    pg.evaluate("""async () => {
      await new Promise(r => { const q = indexedDB.deleteDatabase('naftal_badges'); q.onsuccess = q.onerror = q.onblocked = r; });
    }""")
    pg.evaluate("""localStorage.setItem('naftal_badges_v2', JSON.stringify([{id:'b_old1',seq:7,serial:'2025-0007',nom:'ANCIEN',prenom:'Agent',matricule:'999',siege:'Dépôt',type:'Carte Professionnelle',created:1}])); localStorage.setItem('naftal_seq','7');""")
    pg.reload(); pg.wait_for_function('window.__badgesReady === true'); pg.wait_for_timeout(300)
    r = pg.evaluate('window.__badges.records')
    check('migration: old localStorage badges imported', len(r) == 1 and r[0]['affectation'] == 'Dépôt', str(r))
    check('migration: serial continues at 0008', pg.input_value('#fSerial').endswith('-0008'))
    ctx2.close()
    browser.close()

# PDF page checks
try:
    import pypdf
    for f, n, size in [('print_cr80.pdf', 1, (85.6, 53.98)), ('print_a4.pdf', 1, (210, 297)), ('print_cr80_rv.pdf', 2, (85.6, 53.98)), ('print_a4_rv.pdf', 2, (210, 297))]:
        rd = pypdf.PdfReader(str(OUT / f)); pg = rd.pages[0]
        wmm, hmm = float(pg.mediabox.width) / 72 * 25.4, float(pg.mediabox.height) / 72 * 25.4
        check(f'pdf {f}: {n} page(s), {size[0]}x{size[1]} mm', len(rd.pages) == n and abs(wmm - size[0]) < 1 and abs(hmm - size[1]) < 1, f'{len(rd.pages)}p {wmm:.1f}x{hmm:.1f}')
except ImportError:
    print('SKIP pdf checks (pypdf missing)')

failed = [r for r in results if not r[1]]
print(f'\n{len(results) - len(failed)}/{len(results)} passed')
sys.exit(1 if failed else 0)
