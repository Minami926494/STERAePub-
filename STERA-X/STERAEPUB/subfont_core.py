#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from fontTools.ttLib import TTFont, TTCollection
from fontTools.subset import load_font, Subsetter, Options
from lxml.html import XHTMLParser, document_fromstring
from css_parser.parse import CSSParser
from regex import compile
from os.path import join, dirname
from multiprocessing import Pool
from io import BytesIO
from html import unescape
try:
    from .bookenv_core import book, getbsn, first
except ImportError:
    from bookenv_core import book, getbsn, first

# 字体子集化
white_clear, html_line, css_splitsel, css_clssel, css_idsel, css_regsel = compile(r'[\s　]+'), compile(
    r'font-family:\s*([^;\"\']+?)\s*(!important)?\s*(?:[;\"\']|$)'), compile(r'[ >]+'), compile(r'\.[A-Za-z\d*]+\s*$'), compile(r'#[A-Za-z\d*]+\s*$'), compile(r'\]\s*$')


def subfont(bk: book):
    print('\n字体子集化……')
    GLYPH, ELEM, FONT, CHANGED = {}, {}, {}, {}
    for ele in bk.iter('css'):
        sheet, ele.imp, ele.font, ele.sel = CSSParser(
            loglevel='CRITICAL', parseComments=False, validate=False).parseString(ele.read()).cssRules, [], {}, {}
        for i in sheet:
            if i.type == 3:
                imp = bk.get(bsn=first(getbsn(i.href)))
                if imp and imp not in ele.imp:
                    ele.imp.append(imp)
            elif hasattr(i, 'style'):
                fml = i.style.fontFamily
                if fml:
                    if i.type == 5:
                        src = [bk.get(bsn=font) for font in getbsn(i.style.src) if font]
                        if src:
                            ele.font[fml.strip('\'" ')] = src
                    elif i.type == 1:
                        sel = i.selectorText
                        for part in css_splitsel.split(sel):
                            im = 0
                            if part.startswith(tuple('abcdefghijklmnopqrstuvwxyz*')):
                                im += 1
                            if css_clssel.search(part) or css_regsel.search(part):
                                im += 10
                            if css_idsel.search(part):
                                im += 100
                        ele.sel[sel] = (tuple(j.strip() for j in fml.split(',') if '\'' not in j and '"' not in j), im+10000 if i.style.getPropertyPriority('font-family') else im)
    for ele in bk.iter('font'):
        try:
            cmap = set(TTFont(ele.fp).getBestCmap())
        except:
            fc, bsn = TTCollection(ele.fp).fonts[0], ele.name+'.ttf'
            cmap, fp = set(fc.getBestCmap()), join(dirname(ele.fp), bsn)
            bk.delete(ele)
            fc.save(fp)
            ele = bk.set(bk.elem(fp))
        ele.cmap = cmap
    for ele in bk.iter('text'):
        dom, ele.sel = document_fromstring(ele.read(True), XHTMLParser(remove_comments=True)), {}
        for i in dom.xpath('//link'):
            css = bk.get(bsn=first(getbsn(i.get('href'))))
            if css:
                for imp in css.imp:
                    ele.sel.update(imp.sel)
                ele.sel.update(css.sel)
        for i in dom.xpath('//style'):
            sheet=CSSParser(loglevel='CRITICAL', parseComments=False,validate=False).parseString(i.text).cssRules
            for rule in sheet:
                if rule.type == 1:
                    fml = rule.style.fontFamily
                    if fml:
                        sel = rule.selectorText
                        for part in css_splitsel.split(sel):
                            im = 100
                            if part.startswith(tuple('abcdefghijklmnopqrstuvwxyz*')):
                                im += 1
                            if css_clssel.search(part) or css_regsel.search(part):
                                im += 10
                            if css_idsel.search(part):
                                im += 100
                        if sel not in ele.sel or im>=ele.sel[sel][1]:
                            ele.sel[sel] = (tuple(f.strip() for f in fml.split(',') if '\'' not in f and '"' not in f), im+10000 if rule.style.getPropertyPriority('font-family') else im)
        for i in dom.xpath('//*[contains(@style,"font-family")]'):
            m, n = html_line.search(i.get('style')).groups()
            ELEM[i] = [{i} | set(i.iterdescendants()), m, 7 if n else 3]
        for j in STYLE:
            if css_clssel.search(j[0]) or css_regsel.search(j[0]):
                im = 1
            elif css_idsel.search(j[0]):
                im = 2
            else:
                im = 0
            for k in dom.cssselect(j[0], translator='xhtml'):
                level = im+4 if j[2] else im
                if k not in ELEM or ELEM[k][2] <= level:
                    ELEM[k] = [{k} | set(k.iterdescendants()), j[1], level]
        for j, (des, fml, im) in ELEM.items():
            inherit = 'unset'
            for k in j.iterancestors():
                if k in ELEM:
                    if 'inherit' in fml:
                        inherit = ELEM[k][1]
                    if ELEM[k][2] < 4 or ELEM[k][2] <= im:
                        ELEM[k][0] -= des
            if inherit != 'unset':
                ELEM[j][1] = fml.replace('inherit', inherit)
        for j in ELEM:
            e = tuple(k for k in font_split.split(ELEM[j][1].strip(
            )) if k in GLYPH and k != 'initial' and k != 'unset' and k != 'inherit')
            if not e:
                continue
            if e not in FONT:
                FONT[e] = set()
            FONT[e].update(ord(l) for l in white_clear.sub('', unescape(
                ''.join(''.join(k.xpath('./text()')) for k in ELEM[j][0]))))
    HAS, LOSS = {}.fromkeys(GLYPH, set()), {}.fromkeys(GLYPH, set())
    for i1, i2 in FONT.items():
        for j in i1:
            if i2:
                has = i2 & GLYPH[j]
                HAS[j] = HAS[j] | has
                i2 -= has
            else:
                break
        else:
            LOSS[i1[-1]] = LOSS[i1[-1]] | i2
    pool = Pool()
    for i in GLYPH:
        fid, has, loss = FML2ID[i], ''.join(
            chr(j) for j in HAS[i]), ''.join(chr(j) for j in LOSS[i])
        bsn = bk.id_to_href(fid).rsplit('/', 1)[-1]
        if not has:
            print('　-删除：【', bsn, '】', sep='')
            bk.deletefile(fid)
        elif loss:
            ll = len(loss)
            print('　-缺字', str(ll), '个：【', bsn, '】=>【',
                  loss[:80], '】' if ll <= 80 else '】等', sep='')
        else:
            hl = len(has)
            HAS[i].add(30340)
            CHANGED[(fid, bsn)] = pool.apply_async(
                sbf, args=(ID2FILE[fid], HAS[i]))
            print('　+保留', str(hl), '个：【', bsn, '】=>【',
                  has[:80], '】' if hl <= 80 else '】等', sep='')
    pool.close(), pool.join()
    for (fid, bsn), file in CHANGED.items():
        n, f = bsn.rsplit('.', 1)
        if f == 'ttf':
            bk.writefile(fid, file.get())
        else:
            nbsn = ''.join((n, '.ttf'))
            bk.deletefile(fid), bk.addfile(fid, nbsn, file.get())
            for j in bk.iter('text', 'css'):
                inner = bk.readfile(j[0])
                if bsn in inner:
                    bk.writefile(j[0], inner.replace(bsn, nbsn))


def sbf(f, d):
    OPT, file = Options(), BytesIO()
    OPT.layout_features, OPT.glyph_names, OPT.desubroutinize, OPT.drop_tables, OPT.flavor, subsetter, font = '*', True, True, [
        'DSIG'], 'woff2', Subsetter(OPT), load_font(f, OPT)
    subsetter.populate(unicodes=d), subsetter.subset(
        font), font.save(file), font.close()
    font = file.getvalue()
    file.close()
    return font
