import sqlite3
import re
from collections import Counter
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

from urllib.parse import quote

DB = 'experiment_db.sqlite'

def start_server():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    #THIS DATABASE IS A LOOKUP TABLE FOR COMPONENTS
    #NEEDS STRICT CONVENTIONS FOR FORMULA FORMATTING
    c.execute('''
            CREATE TABLE IF NOT EXISTS components
            (
            id INTEGER PRIMARY KEY,
            formula TEXT,
            notes TEXT,
            molar_mass REAL,
            price REAL,
            is_salt INTEGER
            );
            ''')

    #NEEDS SPECIFICATION FOR DECIMAL
    #THIS TABLE IS FOR THE LIST OF ACTUAL COMPONENTS IN ELECTROLYTES
    c.execute('''
    CREATE TABLE IF NOT EXISTS electrolyte_components (
        electrolyte_id INT,
        component_id INT,
        amount REAL,
        PRIMARY KEY (electrolyte_id, component_id),
        FOREIGN KEY (electrolyte_id) REFERENCES electrolytes(id),
        FOREIGN KEY (component_id) REFERENCES components(id)
    );
            ''')
    #THIS TABLE IS FOR THE LIST OF ACTUAL ELECTROLYTES THINK ABOUT REMOVING FORMULA

    c.execute('''
    CREATE TABLE IF NOT EXISTS electrolytes (
        id INTEGER PRIMARY KEY,
        conductivity REAL,
        conduct_uncert_bound REAL,
        concent_uncert_bound REAL,

        density REAL,
        temperature REAL,
        viscosity REAL,
        v_window_low_bound REAL,
        v_window_high_bound REAL,
        surface_tension REAL
    );
    ''')
    conn.commit()
    conn.close()

'''
dimethyl_formamide = Chemical('(CH3)2NCH',0,.0277)#$/ml
dimethyl_sulfoxide=Chemical('C2H6OS',.0302)
propylene_carbonate=Chemical('C4H6O3',.03876)
sulfolane=Chemical('C4H8O2S', .0792)
#DENSITY FOR SOLVENTS AT 25C
solvents = [dimethyl_formamide,dimethyl_sulfoxide,propylene_carbonate,sulfolane]

calcium_chloride=Chemical('CaCl2', .0207) #$/g
calcium_perchlorate=Chemical('Ca(ClO4)2', .244)
calcium_hexafluorophosphate=Chemical('Ca(PF6)2', 18.04)
calcium_tetrafluoroborate=Chemical('Ca(BF4)2', 2.94)
#MOLAR MASS FOR SALTS
salts = [calcium_chloride,calcium_perchlorate,calcium_hexafluorophosphate,calcium_tetrafluoroborate]

for salt in salts:
  add_component_type(salt)
for solvent in solvents:
  add_component_type(solvent)
'''