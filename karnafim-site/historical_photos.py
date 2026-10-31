"""Licensed, attributed historical photos. Never infer that depicted people served in Company B."""
import html
from flask import Response

PHOTOS = (
 {
  "title":"מרכבה סימן 4 בלטרון — מאי 2006",
  "year":"2006",
  "description":"צילום מקורי מתערוכת יום העצמאות ה־58 באתר יד לשריון בלטרון. הצילום אינו מתעד את פלוגת הקרנפים.",
  "image":"https://upload.wikimedia.org/wikipedia/commons/6/63/Merkava4-atzmaut1.jpg",
  "source":"https://commons.wikimedia.org/wiki/File:Merkava4-atzmaut1.jpg",
  "credit":"MathKnight · Wikimedia Commons",
  "license":"CC BY-SA 3.0 / CC BY 2.5"
 },
 {
  "title":"מרכבה סימן 4 במלחמת לבנון השנייה",
  "year":"2006",
  "description":"צילום של טנק מרכבה סימן 4 בפעילות מבצעית במארון א־ראס, 29 ביולי 2006. אין במקור שיוך לפלוגת הקרנפים.",
  "image":"https://upload.wikimedia.org/wikipedia/commons/2/2c/2006_Lebanon_War._LXXXII.jpg",
  "source":"https://commons.wikimedia.org/wiki/File:2006_Lebanon_War._LXXXII.jpg",
  "credit":"דובר צה״ל · Wikimedia Commons",
  "license":"CC BY-SA 3.0"
 },
 {
  "title":"מרכבה סימן 4 של חטיבה 401",
  "year":"2014",
  "description":"חטיבה 401 בגזרת גבול רצועת עזה, 2014. זהו צילום מאוחר מתקופת השירות, והוא מוצג להמחשת מורשת החטיבה בלבד.",
  "image":"https://upload.wikimedia.org/wikipedia/commons/thumb/7/74/401st_armoured_brigade_of_the_Armored_Corps_Operate_Near_the_Gaza_Border-20-july-2014-.jpg/1280px-401st_armoured_brigade_of_the_Armored_Corps_Operate_Near_the_Gaza_Border-20-july-2014-.jpg",
  "source":"https://commons.wikimedia.org/wiki/File:401st_armoured_brigade_of_the_Armored_Corps_Operate_Near_the_Gaza_Border-20-july-2014-.jpg",
  "credit":"Israel Defense Forces · Wikimedia Commons",
  "license":"CC BY-SA 2.0"
 }
)

def e(v):return html.escape(str(v),quote=True)

def gallery_cards():
    cards=[]
    for p in PHOTOS:
        cards.append('<figure class="photo-card"><a target="_blank" rel="noopener noreferrer" href="'+e(p["source"])+'">'
                     '<img loading="lazy" decoding="async" referrerpolicy="no-referrer" src="'+e(p["image"])+'" alt="'+e(p["title"])+'"></a>'
                     '<figcaption><span class="year">'+e(p["year"])+'</span><h3>'+e(p["title"])+'</h3>'
                     '<p>'+e(p["description"])+'</p>'
                     '<small>צילום: '+e(p["credit"])+' · '+e(p["license"])+'</small><p><a target="_blank" rel="noopener noreferrer" href="'+e(p["source"])+'">מקור ורישיון התמונה ↗</a></p></figcaption></figure>')
    return '<div class="photo-grid">'+''.join(cards)+'</div>'

def gallery_css():
    return '''<style>
    .photo-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(235px,1fr));gap:17px;margin-top:20px}
    .photo-card{overflow:hidden;border-radius:17px;border:1px solid #d9e5d7;background:white;margin:0;box-shadow:0 6px 20px #1b352417}
    .photo-card img{display:block;width:100%;height:220px;object-fit:cover;background:#e2e8de}
    .photo-card figcaption{padding:17px}
    .photo-card figcaption h3{font-size:20px;line-height:1.3;margin:8px 0}
    .photo-card figcaption p{margin:10px 0;color:#496050}
    .photo-card figcaption small{font-size:12px;color:#4c6156}
    .photo-warning{border-right:5px solid #c1b17c;background:#f8f4e9;padding:14px;border-radius:8px}
    </style>'''

def gallery_page():
    from public_pages import shell,NOTICE
    content='<section><h1>📸 תמונות ומורשת השריון</h1><p>גלריה אמיתית של תצלומי ארכיון מורשים לשימוש, עם השנה המדויקת, הקרדיט וקישור לרישיון המקורי.</p>'
    content+='<p class="photo-warning"><strong>חשוב:</strong> התמונות אינן מזוהות כתמונות חברי הפלוגה, ואין לייחס את הלוחמים המצולמים לקרנפים ללא תיעוד. תמונות של החללים יופיעו בדפי ההנצחה רק לאחר אימות והרשאת שימוש.</p>'
    content+=gallery_cards()+'<p><a href="/memorials">מעבר לדפי ההנצחה ←</a> · <a href="/">חזרה לעמוד הבית ←</a></p></section>'
    return shell(gallery_css()+NOTICE+content,"גלריית תמונות מורשת")
