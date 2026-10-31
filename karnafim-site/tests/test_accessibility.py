"""Checks that all public pages can be given reliable Hebrew accessibility landmarks."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import accessibility_ui as ui

HTML='''<!doctype html><html lang="he" dir="rtl"><head><title>בדיקה</title></head>
<body><header><nav><a href="/">ראשי</a></nav></header>
<main><h1>שלום</h1><p>תוכן</p></main></body></html>'''

def main():
    active=ui.integrate_html(HTML)
    assert 'id="main-content"' in active and 'tabindex="-1"' in active
    assert 'href="#main-content"' in active
    assert active.index('skip-to-content') < active.index('<header>')
    assert 'aria-pressed="false"' in active and 'data-access="contrast"' in active
    assert 'aria-live="polite"' in active
    assert active.count('id="karnafim-accessibility-css"') == 1
    assert 'id="karnafim-accessibility-js"' in active
    assert ui.integrate_html(active)==active,"Accessibility must not be injected twice"
    locked=ui.integrate_html(HTML,scripts_allowed=False,toolbar_enabled=False)
    assert 'href="#main-content"' in locked and 'id="main-content"' in locked
    assert 'data-access=' not in locked and '<script' not in locked
    statement=ui.accessibility_statement_body(read_only=True)
    assert '<h1' in statement and 'WCAG' in statement
    assert 'לא בוצעה עדיין בדיקת תאימות' in statement
    print("PASS accessibility: landmarks, skip navigation, controls, safe lockdown, honest statement")

if __name__=="__main__":main()
