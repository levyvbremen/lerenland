from flask import Flask, render_template, jsonify, request
import anthropic
import random
import os
import json
import re
import sqlite3
from datetime import datetime, date

app = Flask(__name__)
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

DB_PATH = os.path.join(os.path.dirname(__file__), "lerenland.db")

def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _init_db():
    with _db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS sessies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            leeftijd INTEGER NOT NULL,
            spel TEXT NOT NULL,
            goed INTEGER NOT NULL DEFAULT 0,
            datum TEXT NOT NULL
        )""")
        conn.commit()

_init_db()

# ══════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/reken")
def reken():
    return render_template("reken.html")

@app.route("/tafels")
def tafels():
    return render_template("tafels.html")

@app.route("/spelling")
def spelling():
    return render_template("spelling.html")

@app.route("/woorden")
def woorden():
    return render_template("woorden.html")

# ══════════════════════════════════════════════
# REKENRAKET API
# ══════════════════════════════════════════════
def maak_som(leeftijd, type_som):
    niveau = "makkelijk" if leeftijd <= 8 else ("gemiddeld" if leeftijd <= 10 else "moeilijk")
    if type_som == "optellen":
        if niveau == "makkelijk": a, b = random.randint(1,10), random.randint(1,10)
        elif niveau == "gemiddeld": a, b = random.randint(10,50), random.randint(10,50)
        else: a, b = random.randint(100,999), random.randint(100,999)
        return {"som": f"{a} + {b}", "antwoord": a+b, "type": "optellen"}
    elif type_som == "aftrekken":
        if niveau == "makkelijk": a, b = random.randint(1,10), random.randint(1,10); a=max(a,b)
        elif niveau == "gemiddeld": a, b = random.randint(20,100), random.randint(1,20)
        else: a, b = random.randint(100,999), random.randint(100,500); a=max(a,b)
        return {"som": f"{a} - {b}", "antwoord": a-b, "type": "aftrekken"}
    elif type_som == "vermenigvuldigen":
        if niveau == "makkelijk": a, b = random.randint(1,5), random.randint(1,5)
        elif niveau == "gemiddeld": a, b = random.randint(2,10), random.randint(2,10)
        else: a, b = random.randint(6,12), random.randint(6,12)
        return {"som": f"{a} × {b}", "antwoord": a*b, "type": "vermenigvuldigen"}
    elif type_som == "delen":
        if niveau == "makkelijk": b=random.randint(1,5); a=b*random.randint(1,5)
        elif niveau == "gemiddeld": b=random.randint(2,10); a=b*random.randint(2,10)
        else: b=random.randint(3,12); a=b*random.randint(3,12)
        return {"som": f"{a} ÷ {b}", "antwoord": a//b, "type": "delen"}
    elif type_som == "breuken":
        noemer = random.choice([2,4,3,5,8,10] if niveau != "makkelijk" else [2,4])
        t1, t2 = random.randint(1,noemer-1), random.randint(1,noemer-1)
        tot = t1+t2; heel = tot//noemer; rest = tot%noemer
        if heel and rest: antwoord = f"{heel}en{rest}/{noemer}"
        elif heel: antwoord = str(heel)
        else: antwoord = f"{rest}/{noemer}"
        return {"som": f"{t1}/{noemer} + {t2}/{noemer}", "antwoord": antwoord, "type": "breuken", "teller": tot, "noemer": noemer}
    return {"som": "1 + 1", "antwoord": 2, "type": "optellen"}

@app.route("/api/som", methods=["POST"])
def api_som():
    data = request.json
    return jsonify(maak_som(int(data.get("leeftijd",8)), data.get("type","optellen")))

@app.route("/api/controleer", methods=["POST"])
def api_controleer():
    data = request.json
    gegeven = str(data.get("antwoord","")).strip()
    correct = str(data.get("correct","")).strip()
    type_som = data.get("type","optellen")
    if type_som == "breuken":
        teller, noemer = data.get("teller",0), data.get("noemer",1)
        g = gegeven.replace(" ","").lower()
        heel = teller//noemer; rest = teller%noemer
        opties = {f"{teller}/{noemer}", f"{rest}/{noemer}" if not heel else ""}
        if rest == 0: opties.add(str(heel))
        if heel and rest: opties.update([f"{heel}en{rest}/{noemer}", f"{heel} en {rest}/{noemer}"])
        try: opties.add(str(round(teller/noemer,2))); opties.add(str(round(teller/noemer,1)))
        except: pass
        goed = g in {o.lower() for o in opties if o}
    else:
        try: goed = float(gegeven.replace(",",".")) == float(correct)
        except: goed = gegeven.lower() == correct.lower()
    aanmoediging = random.choice(["Super goed! 🌟","Geweldig! ⭐","Helemaal correct! 🎉","Briljant! 🏆","Yes! 🎯","Wauw, perfect! 🚀"]) if goed else f"Bijna! Het antwoord was {correct} 💪"
    return jsonify({"goed": goed, "bericht": aanmoediging, "correct": correct})

# ══════════════════════════════════════════════
# STERRENSYSTEEM API
# ══════════════════════════════════════════════
def _bereken_sterren(goed):
    if goed >= 9: return 3
    if goed >= 6: return 2
    if goed >= 1: return 1
    return 0

@app.route("/api/sessie-opslaan", methods=["POST"])
def api_sessie_opslaan():
    data = request.json
    leeftijd = int(data.get("leeftijd", 0))
    spel = data.get("spel", "").strip()
    goed = int(data.get("goed", 0))
    if not spel or leeftijd < 1:
        return jsonify({"ok": False, "fout": "Ontbrekende data"})
    datum = date.today().isoformat()
    with _db() as conn:
        conn.execute("INSERT INTO sessies (leeftijd, spel, goed, datum) VALUES (?,?,?,?)", (leeftijd, spel, goed, datum))
        conn.commit()
    sterren = _bereken_sterren(goed)
    return jsonify({"ok": True, "sterren": sterren})

@app.route("/api/voortgang")
def api_voortgang():
    leeftijd = request.args.get("leeftijd", type=int)
    spellen = ["raken", "tafels", "spelling", "woorden", "avontuur"]
    resultaat = {}
    with _db() as conn:
        for spel in spellen:
            q = "SELECT goed, datum FROM sessies WHERE spel=?"
            params = [spel]
            if leeftijd:
                q += " AND leeftijd=?"
                params.append(leeftijd)
            rijen = conn.execute(q, params).fetchall()
            if not rijen:
                resultaat[spel] = {"sessies": 0, "beste": 0, "sterren": 0, "gemiddeld": 0}
            else:
                goeds = [r["goed"] for r in rijen]
                beste = max(goeds)
                gemiddeld = round(sum(goeds) / len(goeds), 1)
                resultaat[spel] = {
                    "sessies": len(rijen),
                    "beste": beste,
                    "sterren": _bereken_sterren(beste),
                    "gemiddeld": gemiddeld
                }
    return jsonify(resultaat)

@app.route("/api/uitleg", methods=["POST"])
def api_uitleg():
    data = request.json
    r = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=150,
        messages=[{"role":"user","content":f"Leg aan een kind van {data.get('leeftijd',8)} jaar uit hoe je {data.get('som','')} = {data.get('antwoord','')} oplost. Max 2 zinnen, simpele taal, Nederlands."}])
    return jsonify({"uitleg": r.content[0].text})

# ══════════════════════════════════════════════
# TAFELTIJGER API
# ══════════════════════════════════════════════
@app.route("/api/tafel-vraag", methods=["POST"])
def api_tafel_vraag():
    data = request.json
    tafel = int(data.get("tafel", random.randint(1,10)))
    b = random.randint(1, 10)
    return jsonify({"vraag": f"{tafel} × {b}", "antwoord": tafel*b, "tafel": tafel, "b": b})

# ══════════════════════════════════════════════
# SPELLINGBIJ API
# ══════════════════════════════════════════════
SPELLING_WOORDEN = {
    "makkelijk": [
        ("kat","Een huisdier dat miauwt"),("hond","Een trouw huisdier"),("vis","Zwemt in water"),
        ("boom","Groeit in het bos"),("raam","Glas in de muur"),("fiets","Rijdt op twee wielen"),
        ("brug","Verbindt twee oevers"),("melk","Wit drankje van een koe"),("boek","Bevat verhalen om te lezen"),
        ("lamp","Geeft licht"),("deur","Ga je doorheen naar buiten"),("bal","Rond en om mee te spelen"),
        ("maan","Schijnt 's nachts"),("zon","Schijnt overdag"),("roos","Een mooie bloem"),
    ],
    "gemiddeld": [
        ("school","Waar je leert"),("water","Je drinkt dit elke dag"),("appel","Een rood of groen fruit"),
        ("vlinder","Mooi insect met vleugels"),("trein","Rijdt op rails"),("spiegel","Hierin zie je jezelf"),
        ("sleutel","Opent een slot"),("tafel","Zit je aan om te eten"),("lucht","Dit adem je in"),
        ("strand","Zand naast de zee"),("kaart","Stuur je voor een verjaardag"),("dierentuin","Hier zie je veel dieren"),
        ("bibliotheek","Hier leen je boeken"),("chocolade","Lekker bruin snoepje"),("paraplu","Gebruik je als het regent"),
    ],
    "moeilijk": [
        ("vliegtuig","Vliegt door de lucht"),("schildpad","Heeft een schild op zijn rug"),
        ("bibliotheek","Hier kun je boeken lenen"),("chocoladetaart","Lekker verjaardagstaart"),
        ("vriendschap","Wanneer je goed met iemand omgaat"),("geschiedenis","Vak over vroeger op school"),
        ("wetenschap","Bestuderen hoe de wereld werkt"),("muziekinstrument","Hiermee maak je muziek"),
        ("avontuur","Spannende reis of ervaring"),("olifant","Het grootste landdier"),
        ("vliegveld","Waar vliegtuigen landen"),("huiswerk","Schoolopdrachten thuis maken"),
    ]
}

@app.route("/api/spelling-woord", methods=["POST"])
def api_spelling_woord():
    data = request.json
    leeftijd = int(data.get("leeftijd", 8))
    niveau = "makkelijk" if leeftijd <= 7 else ("gemiddeld" if leeftijd <= 10 else "moeilijk")
    woord, omschrijving = random.choice(SPELLING_WOORDEN[niveau])
    return jsonify({"omschrijving": omschrijving, "woord": woord, "niveau": niveau})

@app.route("/api/spelling-controleer", methods=["POST"])
def api_spelling_controleer():
    data = request.json
    gegeven = data.get("antwoord","").strip().lower()
    correct = data.get("woord","").strip().lower()
    goed = gegeven == correct
    return jsonify({"goed": goed, "correct": correct})

# ══════════════════════════════════════════════
# WOORDENSCHAT API
# ══════════════════════════════════════════════
@app.route("/api/woord-vraag", methods=["POST"])
def api_woord_vraag():
    data = request.json
    leeftijd = int(data.get("leeftijd", 8))
    niveau = "groep 3-4 (6-8 jaar)" if leeftijd <= 8 else ("groep 5-6 (9-10 jaar)" if leeftijd <= 10 else "groep 7-8 (11-12 jaar)")

    r = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=250,
        messages=[{"role":"user","content":f"""Maak een woordenschatvraag voor een kind van {leeftijd} jaar ({niveau}).
Geef een Nederlands woord en 4 korte betekenissen waarvan 1 correct is.
Geef ALLEEN dit JSON terug (geen uitleg):
{{"woord":"...","correct":"de juiste betekenis in max 8 woorden","opties":["betekenis1","betekenis2","betekenis3","betekenis4"]}}
De juiste betekenis moet ook in opties staan. Schrijf in het Nederlands."""}]
    )
    try:
        tekst = r.content[0].text.strip()
        if tekst.startswith("```"): tekst = tekst.split("```")[1].replace("json","").strip()
        vraag = json.loads(tekst)
        random.shuffle(vraag["opties"])
        return jsonify({"succes": True, **vraag})
    except:
        return jsonify({"succes": False, "fout": "Kon geen vraag maken"})

# ══════════════════════════════════════════════
# AVONTUUR LEER-APP
# ══════════════════════════════════════════════

def extract_json(tekst):
    tekst = tekst.strip()
    try:
        return json.loads(tekst)
    except Exception:
        pass
    m = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', tekst)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    m = re.search(r'\{[\s\S]*\}', tekst)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    raise ValueError("Geen geldige JSON gevonden in API-antwoord")

GROEP_INFO = {
    1: "groep 1 (4-5 jaar): letters herkennen, tellen tot 10, eenvoudige rijmpjes",
    2: "groep 2 (5-6 jaar): letters kennen, tellen tot 20, eenvoudige woordjes",
    3: "groep 3 (6-7 jaar): lezen, schrijven, optellen en aftrekken tot 20",
    4: "groep 4 (7-8 jaar): tafels van 1-5, sommen tot 100, woordenschat uitbreiden",
    5: "groep 5 (8-9 jaar): alle tafels, breuken intro, meer complexe woorden",
    6: "groep 6 (9-10 jaar): vermenigvuldigen, breuken, decimalen, synoniemen",
    7: "groep 7 (10-11 jaar): procenten, complexe spelling, woordbetekenis in context",
    8: "groep 8 (11-12 jaar): voorbereiding voortgezet onderwijs, alle vakgebieden"
}

NIVEAU_MAP = {-2: "heel makkelijk", -1: "makkelijk", 0: "normaal", 1: "uitdagend", 2: "heel moeilijk"}

@app.route("/avontuur")
def avontuur():
    return render_template("avontuur.html")

@app.route("/api/avontuur-vraag", methods=["POST"])
def api_avontuur_vraag():
    data = request.json
    groep = int(data.get("groep", 4))
    vak = data.get("vak", "rekenen")
    thema = data.get("thema", "Ruimtereis")
    level = int(data.get("level", 1))
    niveau = int(data.get("niveau", 0))
    niveau_label = NIVEAU_MAP.get(niveau, "normaal")
    level_naam = data.get("level_naam", "")
    groep_info = GROEP_INFO.get(groep, f"groep {groep}")

    system_prompt = f"""Jij bent een enthousiaste, vrolijke leercoach voor basisschoolkinderen. Je genereert vragen voor {groep_info} over het vak '{vak}' in het avonturenthema '{thema}' (nu in level {level}: '{level_naam}'). Moeilijkheidsgraad: {niveau_label}.

Maak de vraag thematisch: embed het in een kort verhaaltje passend bij '{thema}'. Geen droge sommen, maar spannende contexten!

Geef ALLEEN dit JSON-object terug (geen extra tekst, geen markdown, geen uitleg buiten het JSON):
{{
  "vraagTekst": "de vraag ingebed in een kort thematisch verhaalzinnetje",
  "vraagType": "open" of "meerkeuze",
  "opties": ["optie1","optie2","optie3","optie4"] of null,
  "correctAntwoord": "het correcte antwoord als string",
  "uitleg": "max 2 zinnen uitleg passend bij de leeftijd",
  "feedbackPositief": "max 1 zin enthousiaste bemoediging, passend bij thema '{thema}'"
}}

Regels:
- Gebruik 'meerkeuze' voor spelling en woordenschat; wissel af bij rekenen
- Bij meerkeuze: altijd exact 4 opties, correctAntwoord is exact gelijk aan één optie
- Bij open: correctAntwoord is het verwachte antwoord (getal of woord)
- Taalgebruik: simpel, vriendelijk, passend bij de groep
- Spellingsvragen: laat het kind kiezen tussen correct/fout gespelde versies OF dictee-stijl (open)"""

    try:
        r = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=system_prompt,
            messages=[{"role": "user", "content": f"Genereer een {vak}-vraag op niveau {niveau_label}."}]
        )
        vraag = extract_json(r.content[0].text)
        for veld in ["vraagTekst", "vraagType", "correctAntwoord", "uitleg", "feedbackPositief"]:
            if veld not in vraag:
                raise ValueError(f"Veld '{veld}' ontbreekt in antwoord")
        return jsonify({"succes": True, **vraag})
    except Exception as e:
        return jsonify({"succes": False, "fout": str(e)})

@app.route("/api/avontuur-tekst", methods=["POST"])
def api_avontuur_tekst():
    data = request.json
    thema = data.get("thema", "Ruimtereis")
    level = int(data.get("level", 1))
    level_naam = data.get("level_naam", "")
    soort = data.get("soort", "intro")
    naam = data.get("naam", "avonturier")

    prompts = {
        "intro": f"Schrijf een spannende introductiescène van 2-3 zinnen voor het avontuur '{thema}'. Spreek het kind direct aan als 'jij'. Maak het uitnodigend en avontuurlijk! Eindig met een uitnodiging om te beginnen.",
        "level_overgang": f"Schrijf een spannende verhaaltekst van 2-3 zinnen die het avontuur '{thema}' voortzet bij level {level}: '{level_naam}'. Spreek {naam} direct aan. Maak het opwindend en motiverend!",
        "einde": f"Schrijf een feestelijke eindscène van 3-4 zinnen voor het voltooien van alle levels van '{thema}'. Feliciteer {naam} heroïsch en enthousiast!"
    }

    try:
        r = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompts.get(soort, prompts["intro"])}]
        )
        return jsonify({"succes": True, "tekst": r.content[0].text.strip()})
    except Exception as e:
        fallbacks = {
            "intro": f"Welkom, dappere avonturier! Het avontuur '{thema}' begint nu. Maak je klaar voor spannende uitdagingen!",
            "level_overgang": f"Goed gedaan, {naam}! Level {level} staat voor je klaar: '{level_naam}'. Dit wordt spannend!",
            "einde": f"Wauw, {naam}, je hebt het gehaald! Je bent een echte held van '{thema}'. Fantastisch gedaan!"
        }
        return jsonify({"succes": False, "tekst": fallbacks.get(soort, "Het avontuur gaat door!"), "fout": str(e)})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5002)
