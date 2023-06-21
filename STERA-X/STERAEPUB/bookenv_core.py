#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from os import path, walk
from time import time
from collections.abc import Generator
from regex import compile, sub, Match
from lxml.etree import parse, tostring
from .epubio_core import pjoin, elem, InvalidEpubError

# EPUB解析
linkpath, navmap, ol1, ol2, navpoint, navlabel = compile(r'(?<=url\(|url\([\'\"]|href=[\'\"]|[^-]src=[\'\"]|@import [\'\"])[^)\'\"#:]+?(?=[)\'\"#])'), compile(r'(?i)[\s\S]*<navMap>([\s\S]*)</navMap>[\s\S]*'), compile(
    r'</li>\s*(?=</li>)'), compile(r'(<li>(?:(?!</li>)[\s\S])*?)(?=<li>)'), compile(r'(?i)<(/)?navPoint[^>]*?>'), compile(r'(?i)<navLabel[^>]*?>\s*<text[^>]*?>([^<]*?)</text>\s*</navLabel>\s*<content[^>]*?src="[^"]*?([^"/]+)"[^>]*?/>')


def extlower(bsn: str) -> str:
    name, ext = path.splitext(bsn)
    return name+ext.lower()


class book:
    def __init__(self, src: str, runInSigil: bool = False):
        '''
        传入源EPUB以初始化book类并执行规范化，将在系统的用户文件夹下建立工作区。\n
        src -> 源EPUB文件（夹）路径\n
        runInSigil -> 是否在Sigil中作为插件运行
        '''
        self.runInSigil, norepeat = runInSigil, {'container.xml', 'mimetype'}
        elems = self.elems = {elem(pjoin(metainf, 'container.xml')).write(
            '<?xml version="1.0" encoding="UTF-8"?>\n<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n<rootfiles>\n<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>\n</rootfiles>\n</container>'), elem(pjoin(outdir, 'mimetype')).write('application/epub+zip')}
        outdir = self.outdir = pjoin(path.expanduser('~').replace(
            '\\', '/'), 'STERAEPUB', str(time()).replace('.', '-'))
        oebps = self.oebps = pjoin(outdir, 'OEBPS')
        metainf = self.metainf = pjoin(outdir, 'META-INF')
        stdopfpath, stdncxpath = pjoin(
            oebps, 'content.opf'), pjoin(oebps, 'toc.ncx')
        opfpath = ncxpath = None
        elem(src).copy(outdir, True) if runInSigil == 'sigil' else elem(
            src).extract(outdir, True)
        mid2ele = self.mid2ele = {}
        href2ele = self.href2ele = {}
        fp2ele = self.fp2ele = {}
        bsn2ele = self.bsn2ele = {}
        for r, d, f in walk(outdir):
            for n in f:
                ele, stdpath = elem(pjoin(r, n)), None
                fp, ext, group = ele.fp, ele.ext, ele.group
                if ext != ext.lower():
                    n = extlower(n)
                    ele.rename(n)
                if n in norepeat:
                    continue
                elif group:
                    stdpath = pjoin(metainf, ele.bsn) if ele.form == 'other' else pjoin(
                        oebps, group, ele.bsn)
                elif ext == '.opf' and not opfpath:
                    stdpath = opfpath = stdopfpath
                elif ext == '.ncx' and not ncxpath:
                    stdpath = ncxpath = stdncxpath
                if not stdpath:
                    ele.remove()
                    continue
                elif fp != stdpath:
                    ele.move(stdpath)
                elems.add(ele)
                norepeat.add(n)
                fp2ele[stdpath], bsn2ele[n] = ele, ele
                if ele.href:
                    href2ele[ele.href] = ele
        if not opfpath:
            raise InvalidEpubError('未找到有效的OPF')
        opf = self.opf = fp2ele[opfpath]
        opftree, self.ncx, self.nav = parse(
            opf.read()), fp2ele.get(ncxpath), None
        for item in opftree.xpath('//item[@id and @href]'):
            mid, href, prop = item.get('id'), item.get(
                'href'), item.get('properties')
            ele = bsn2ele.get(extlower(path.basename(href)))
            if ele:
                ele.mid, ele.prop = mid, prop if prop else None
                if prop == 'nav':
                    if self.nav:
                        prop = None
                    else:
                        self.nav = ele
                mid2ele[mid] = ele
        spine = self.spine = []
        for itemref in opftree.xpath('//itemref[@idref]'):
            idref, linear, prop = itemref.get('idref'), itemref.get(
                'linear'), itemref.get('properties')
            ele = mid2ele.get(idref)
            if ele:
                ele.spineLinear, ele.spineProp = linear if linear else None, prop if prop else None
                spine.append(ele)
        for ele in self.iter('text'):
            if ele not in spine:
                spine.append(ele)
        guide = self.guide = []
        for reference in opftree.xpath('//reference[@href and @type and @title]'):
            href, type_, title = reference.get(
                'href'), reference.get('type'), itemref.get('title')
            ele = self.get(bsn=extlower(path.basename(href)))
            if ele:
                ele.guideType, ele.guideTitle = type_, title if title else ''
                guide.append(ele)
        stdmeta = '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:opf="http://www.idpf.org/2007/opf">'
        for meta in opftree.xpath('//metadata'):
            self.metadata = sub(r'<metadata[^>]*?>', stdmeta, tostring(meta))
            break
        else:
            self.metadata = stdmeta+'\n</metadata>'
        for sp in opftree.xpath('//spine'):
            ppd = sp.get('page-progression-direction')
            self.ppd = ppd if ppd == 'ltr' or ppd == 'rtl' else None
            break
        else:
            self.ppd = None
        self.ref('text', 'css', 'ncx').stdopf(
        ) if self.nav else self.newnav(False)

    def get(self, mid: str | None = None, href:  str | None = None, fp:  str | None = None, bsn:  str | None = None) -> elem | None:
        '''
        通过对应的参数返回元素对应的elem对象，填入多个参数时按下述顺序查找直至有返回结果。\n
        mid -> 文件对应的manifest id\n
        href -> 文件在OPF中的href\n
        fp -> 文件的绝对路径\n
        bsn -> 文件的完整文件名
        '''
        if mid and mid in self.mid2ele:
            return self.mid2ele[mid]
        elif href and href in self.href2ele:
            return self.href2ele[href]
        elif fp and fp in self.fp2ele:
            return self.fp2ele[fp]
        elif bsn and bsn in self.bsn2ele:
            return self.bsn2ele[bsn]

    def iter(self, *form: str) -> Generator[elem] | None:
        '''
        通过类型参数返回包含所有该类型文件elem对象的迭代器，多个参数时可匹配多类型文件。\n
        form -> 文件类型参数（'text'：HTML类文档 | 'css'：CSS样式表 | 'font'：字体文件 | 'audio'：音频文件 | 'video'：视频文件 | 'ncx'：NCX文件 | 'other'：META-INF中的XML文件 | 'misc'：其他常见类型文件）
        '''
        for ele in self.elems:
            if ele.form in form:
                yield ele

    def add(self, bsn: str, data: str | bytes, manifest: bool = True):
        '''
        通过新文件的完整文件名和文件内容向EPUB添加文件，当重名时将自动重命名，返回新文件的elem对象。\n
        bsn -> 新文件的完整文件名\n
        data -> 新文件的文件内容\n
        manifest -> 是否为新文件新增OPF条目（manifest和spine）
        '''
        fp = pjoin(self.metainf, bsn)
        new = elem(fp).write(data)
        name, ext, group = new.name, new.ext.lower(), new.group
        while name+ext in self.bsn2ele:
            name += '_'
        nbsn = name+ext
        self.fp2ele[fp], self.bsn2ele[nbsn] = new, new
        self.elems.add(new)
        if manifest:
            if not group:
                raise InvalidEpubError('不支持的文件类型')
            new.move(pjoin(self.oebps, group, nbsn))
            while nbsn in self.mid2ele:
                nbsn += '_'
            new.mid = nbsn
            self.mid2ele[nbsn], self.href2ele[new.href] = new, new
            self.spine.append(new)
            self.stdopf()
        elif nbsn != bsn:
            new.rename(nbsn)
        return new

    def delete(self, ele: elem, delfile: bool = True):
        '''
        将elem对象对应的文件从EPUB中删除，移除其OPF条目（manifest和spine，如果存在），返回被删除文件的elem对象（如果存在）。\n
        ele -> 文件的elem对象\n
        delfile -> 是否删除文件本身
        '''
        mid = self.mid2ele.pop(ele.mid, None)
        self.href2ele.pop(ele.href, None)
        self.fp2ele.pop(ele.fp, None)
        self.bsn2ele.pop(ele.bsn, None)
        self.elems.discard(ele)
        if mid:
            if ele in self.spine:
                self.spine.remove(mid)
            self.stdopf()
        return ele.remove() if delfile else ele

    def ref(self, *form: str):
        '''
        重定向类型参数所对应文件内容中存在的无效超链接地址，返回book对象，多个参数时可匹配多类型文件。\n
        form -> 文件类型参数（'text'：HTML类文档 | 'css'：CSS样式表 | 'font'：字体文件 | 'audio'：音频文件 | 'video'：视频文件 | 'ncx'：NCX文件 | 'other'：META-INF中的XML文件 | 'misc'：其他常见类型文件）
        '''
        for ele in self.iter(*form):
            data = ele.read()
            if linkpath.search(data):
                ele.write(linkpath.sub(
                    lambda x: self.__ref(x, ele.form), data))
        return self

    def __ref(self, match: Match[str], form: str) -> str:
        match = match.group(0)
        ele = self.bsn2ele.get(path.basename(match))
        if not ele:
            return match
        elif form == 'ncx':
            return ele.href
        elif ele.form == form:
            return ele.bsn
        else:
            return '../'+ele.href

    def newnav(self, cover: bool = True) -> elem:
        '''
        通过NCX生成新的NAV，返回新NAV的elem对象。\n
        cover -> 是否覆盖已存在的NAV
        '''
        if not self.ncx:
            raise InvalidEpubError('未找到有效的NCX')
        newnav = navmap.sub(lambda x: '\n'.join(('<?xml version="1.0" encoding="utf-8" standalone="no"?>\n<!DOCTYPE html>\n<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh" xmlns:epub="http://www.idpf.org/2007/ops" xmlns:xml="http://www.w3.org/XML/1998/namespace">\n<head>\n<title>導航</title>\n<link href="../Styles/stylesheet.css" type="text/css" rel="stylesheet"/>\n<script type="text/javascript" src="../Misc/script.js"></script>\n</head>\n<body epub:type="frontmatter" id="nav">\n<nav epub:type="toc" id="toc" role="doc-toc">\n<ol>',
                            x.group(1), '</ol>\n</nav>\n<nav epub:type="landmarks" id="landmarks" hidden="">\n<ol>', *('<li><a epub:type="'+ele.guideType+'" href="'+ele.href+'">'+ele.guideTitle+'</a></li>' for ele in self.guide), '</ol>\n</nav>\n</body>\n</html>')), ol1.sub('</li>\n</ol>', ol2.sub(r'', r'\1\n<ol>', navpoint.sub(r'<\1li>', navlabel.sub(r'<a href="\2">\1</a>', self.ncx.read())))))
        if not self.nav:
            self.nav = self.add('nav.xhtml', newnav)
        elif cover:
            self.nav.write(newnav)
        return self.ref('text', 'css', 'ncx').nav

    def stdopf(self) -> elem:
        '''
        生成新的OPF并覆盖旧的OPF，返回OPF的elem对象。
        '''
        return self.opf.write('\n'.join(('<?xml version="1.0" encoding="utf-8"?>\n<package version="3.0" unique-identifier="BookId" prefix="rendition: http://www.idpf.org/vocab/rendition/#" xmlns="http://www.idpf.org/2007/opf">', self.metadata, *('<item id="%s" href="%s" media-type="%s"/>' % (ele.mid, ele.href, ele.mime+'" properties="'+ele.prop if ele.prop else ele.mime) for ele in self.elems), '<spine%s%s>' % (' page-progression-direction="'+self.ppd+'"' if self.ppd else '', ' toc="'+self.ncx.mid+'"' if self.ncx else ''), *('<itemref idref="%s"%s%s/>' % (ele.mid, ' linear="'+ele.spineLinear+'"' if ele.spineLinear else '', ' properties="'+ele.spineProp+'"' if ele.spineProp else '') for ele in self.spine), '</spine>\n<guide>', *('<reference type="'+ele.guideType+'" title="'+ele.guideTitle+'" href="'+ele.href+'"/>' for ele in self.guide), '</guide>\n</package>')))

    def save(self, dst: str, done: bool = False):
        '''
        将工作区中内容保存并输出为EPUB文件，返回book类（如果存在）。\n
        dst -> EPUB文件输出路径\n
        done -> 是否已经完成处理，若完成将删除工作区和book类
        '''
        outdir = elem(self.outdir)
        outdir.create(dst, True)
        if not done:
            return self
        outdir.remove()
        del self