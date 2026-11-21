"""Inject the logo and watermark (base64) into template.html -> ../naftal-badges.html"""
import pathlib, sys

here = pathlib.Path(__file__).parent
assets = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else here
html = (here / 'template.html').read_text(encoding='utf-8')
html = html.replace('__LOGO__', (assets / 'logo.b64').read_text().strip())
html = html.replace('__WM__', (assets / 'wm.b64').read_text().strip())
html = html.replace('__AUTHOR__', (assets / 'author.b64').read_text().strip())
html = html.replace('__ICON__', (assets / 'icon.b64').read_text().strip())
html = html.replace('__ICONWIDE__', (assets / 'iconwide.b64').read_text().strip())
out = here.parent / 'naftal-badges.html'
out.write_text(html, encoding='utf-8')
print(out, len(html) // 1024, 'KB')
