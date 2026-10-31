"""Build the TTF fonts in /fonts from @fontsource npm packages.

Fontsource ships fonts split per script (devanagari / latin). Each Hindi font is
rebuilt here as ONE TTF = Devanagari subset + Latin glyphs (digits, A-Z, punctuation)
so mixed text like "5 आदतें!" renders without tofu boxes. Families are renamed to
unique "KD ..." names so the renderer can address them unambiguously.

    cd /tmp/fnt && for p in yatra-one rozha-one noto-sans-devanagari baloo-2 mukta khand poppins montserrat; do
        npm pack @fontsource/$p && tar xzf fontsource-$p-*.tgz && mv package fontsource-$p; done
    python thumbnail/tools/build_fonts.py /tmp/fnt fonts
"""
import sys, os, copy
from fontTools.ttLib import TTFont

SRC, DST = sys.argv[1], sys.argv[2]
HINDI = [  # (package, weight, family name, out file)
    ('yatra-one', 400, 'KD Yatra', 'YatraOne-Deva'),
    ('rozha-one', 400, 'KD Rozha', 'RozhaOne-Deva'),
    ('noto-sans-devanagari', 800, 'KD Noto ExtraBold', 'NotoSansDeva-ExtraBold'),
    ('noto-sans-devanagari', 900, 'KD Noto Black', 'NotoSansDeva-Black'),
    ('baloo-2', 800, 'KD Baloo', 'Baloo2-Deva-ExtraBold'),
    ('mukta', 800, 'KD Mukta', 'Mukta-Deva-ExtraBold'),
    ('khand', 700, 'KD Khand', 'Khand-Deva-Bold'),
]
LATIN = [
    ('poppins', 900, 'KD Poppins Black', 'Poppins-Black'),
    ('poppins', 800, 'KD Poppins ExtraBold', 'Poppins-ExtraBold'),
    ('montserrat', 900, 'KD Montserrat Black', 'Montserrat-Black'),
    ('montserrat', 800, 'KD Montserrat ExtraBold', 'Montserrat-ExtraBold'),
]

def pkgdir(p):
    for d in os.listdir(SRC):
        if d.startswith('fontsource-' + p) and os.path.isdir(os.path.join(SRC, d)) and d[len('fontsource-' + p):len('fontsource-' + p) + 1] in ('', '-') and not d[len('fontsource-'+p)+1:][:1].isalpha():
            return os.path.join(SRC, d, 'files')
    raise SystemExit('package not found: ' + p)

def load(p, subset, w):
    f = TTFont(os.path.join(pkgdir(p), f'{p}-{subset}-{w}-normal.woff2'))
    f.flavor = None
    return f

def rename(t, fam):
    nm = t['name']
    for rec in list(nm.names):
        if rec.nameID in (16, 17, 21, 22, 25):
            nm.removeNames(nameID=rec.nameID)
    for args in ((3, 1, 0x409), (1, 0, 0)):
        nm.setName(fam, 1, *args); nm.setName('Regular', 2, *args)
        nm.setName(fam, 4, *args); nm.setName(fam.replace(' ', '-'), 6, *args)
    t['OS/2'].usWeightClass = 400
    t['OS/2'].fsSelection = (t['OS/2'].fsSelection & ~0b1100001) | 0b1000000
    t['head'].macStyle = 0

def merge_latin(D, L):
    dg, lg = D['glyf'], L['glyf']
    order = D.getGlyphOrder()
    have = set(order)
    dcmap = D.getBestCmap()
    mapping = {}

    def copy_glyph(name):
        if name in mapping:
            return mapping[name]
        new = name if name not in have else name + '.lat'
        mapping[name] = new
        g = copy.deepcopy(lg[name])
        if g.isComposite():
            for c in g.components:
                c.glyphName = copy_glyph(c.glyphName)
        order.append(new); have.add(new)
        dg.glyphs[new] = g
        D['hmtx'].metrics[new] = L['hmtx'].metrics[name]
        return new

    added = {}
    for cp, name in L.getBestCmap().items():
        if cp not in dcmap:
            added[cp] = copy_glyph(name)
    D.setGlyphOrder(order)
    dg.glyphOrder = order
    for st in D['cmap'].tables:
        if st.isUnicode():
            st.cmap.update({cp: n for cp, n in added.items() if st.format != 4 or cp <= 0xFFFF})
    D['maxp'].numGlyphs = len(order)
    return len(added)

os.makedirs(DST, exist_ok=True)
for p, w, fam, out in HINDI:
    D = load(p, 'devanagari', w)
    L = load(p, 'latin', w)
    assert D['head'].unitsPerEm == L['head'].unitsPerEm
    n = merge_latin(D, L)
    rename(D, fam)
    D.save(os.path.join(DST, out + '.ttf'))
    print(f'{out}.ttf  (+{n} latin glyphs)')
for p, w, fam, out in LATIN:
    t = load(p, 'latin', w)
    rename(t, fam)
    t.save(os.path.join(DST, out + '.ttf'))
    print(f'{out}.ttf')
