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
            molality REAL,
            price REAL
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

class Chemical:
    ELEMENTS = ['H', 'He', 'Li', 'Be', 'B', 'C', 'N', 'O', 'F', 'Ne', 'Na', 'Mg'
    , 'Al', 'Si', 'P', 'S', 'Cl', 'Ar', 'K', 'Ca', 'Sc', 'Ti', 'V', 'Cr', 'Mn',
    'Fe', 'Co', 'Ni', 'Cu', 'Zn', 'Ga', 'Ge', 'As', 'Se', 'Br', 'Kr','Rb', 'Sr',
    'Y', 'Zr', 'Nb', 'Mo', 'Tc', 'Ru', 'Rh', 'Pd', 'Ag', 'Cd', 'In', 'Sn', 'Sb',
    'Te', 'I', 'Xe', 'Cs', 'Ba', 'La', 'Ce', 'Pr', 'Nd', 'Pm', 'Sm', 'Eu', 'Gd',
    'Tb', 'Dy', 'Ho', 'Er', 'Tm', 'Yb', 'Lu', 'Hf', 'Ta', 'W', 'Re', 'Os', 'Ir',
    'Pt', 'Au', 'Hg', 'Tl', 'Pb', 'Bi', 'Th', 'Pa', 'U', 'Np', 'Pu', 'Am', 'Cm',
    'Bk','Cf', 'Es', 'Fm', 'Md', 'No', 'Lr', 'Rf', 'Db', 'Sg', 'Bh', 'Hs', 'Mt',
     'Ds', 'Rg', 'Cn', 'Nh', 'Fl', 'Mc', 'Lv', 'Ts', 'Og']
    def __init__(self, formula=' ', molality=0, price=0):
        self.elements = self.parse_formula(formula)
        self.molality = molality
        self.price = price # PRICE IS IN TERMS OF $/ML AND $/G

    def parse_formula(self, formula): #recursive function to parse equivalent formulas
        elements = Counter()
        i = 0
        while i < len(formula):
            if formula[i] == '(':
                count = 1
                for j in range(i + 1, len(formula)):
                    if formula[j] == '(':
                        count += 1
                    elif formula[j] == ')':
                        count -= 1
                        if count == 0:
                            break
                else:
                    raise TypeError(f'Unbalanced parentheses in formula {formula}')

                sub_elements = self.parse_formula(formula[i + 1:j])
                i = j + 1

                factor = ''
                while i < len(formula) and formula[i].isdigit():
                    factor += formula[i]
                    i += 1
                factor = int(factor) if factor else 1
                for element, quantity in sub_elements.items():
                    elements[element] += quantity * factor
            elif formula[i].isalpha():
                element = formula[i]
                i += 1
                while i < len(formula) and formula[i].islower():
                    element += formula[i]
                    i += 1
                if element not in self.ELEMENTS:
                    raise TypeError(f'Unknown element {element} in formula {formula}')
                quantity = ''
                while i < len(formula) and formula[i].isdigit():
                    quantity += formula[i]
                    i += 1
                quantity = int(quantity) if quantity else 1
                elements[element] += quantity
            else:
                raise TypeError(f'Invalid character {formula[i]} in formula {formula}')
        return elements

    def __eq__(self, other):
        if isinstance(other, Chemical):
            return self.elements == other.elements
        return False

    def __str__(self):#outputs formula with elements sorted by element number
        sorted_elements = sorted(self.elements.items(), key=lambda x: self.ELEMENTS.index(x[0]))
        return ''.join(f'{element}{count}' if count > 1 else f'{element}' for element, count in sorted_elements)

def get_electrolyte_by_components(components: dict):
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    #creating long query string with all the requirements for amount and formula
    query_string = "SELECT e.id FROM electrolytes e WHERE e.id IN (SELECT ec.electrolyte_id FROM electrolyte_components ec WHERE "
    query_conditions = []
    query_values = []
    for formula, amount in components.items():
        chemical = Chemical(formula)
        query_conditions.append("(ec.component_id = (SELECT id FROM components WHERE formula = ?) AND ec.amount = ?)")
        query_values.extend([str(chemical), amount])
    query_string += " OR ".join(query_conditions) + " GROUP BY ec.electrolyte_id HAVING COUNT(ec.electrolyte_id) = ?)"
    query_values.append(len(components))

    c.execute(query_string, query_values)
    candidate_ids = [row[0] for row in c.fetchall()]

    #check that each candidate id doesn't have extra components
    
    for id in candidate_ids:
        c.execute("SELECT COUNT(*) FROM Electrolyte_Components WHERE Electrolyte_ID = ?", (id,))
        if c.fetchone()[0] != len(components):
            candidate_ids.remove(id)
    conn.close()
    
    if(len(candidate_ids) > 1):
        raise ValueError(f"{len(candidate_ids)} total duplicate electrolytes found with components {str(components)}")
    return candidate_ids[0]

def add_electrolyte(components: dict,

                    conductivity: float,
                    conduct_uncert_bound: float,
                    concent_uncert_bound: float,

                    density: float = -1,
                    temperature: float = -1,
                    viscosity: float = -1,
                    v_window_low_bound: float = -1,
                    v_window_high_bound: float = -1,
                    surface_tension: float = -1
                    ):
    """
    components: dict of chemical formula and amount; e.g. {str: float, ...}
    """
    if(check_electrolyte_exists(components)):
        raise ValueError(f'Electrolyte with formula {components} already exists')
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    attr_dict = {
        'conductivity': conductivity,
        'conduct_uncert_bound': conduct_uncert_bound,
        'concent_uncert_bound': concent_uncert_bound,
        'density': density,
        'temperature': temperature,
        'viscosity': viscosity,
        'v_window_low_bound': v_window_low_bound,
        'v_window_high_bound': v_window_high_bound,
        'surface_tension': surface_tension,
    }

    c.execute(f'''INSERT INTO electrolytes {tuple(attr_dict.keys())} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'''
    , tuple(attr_dict.values()))

    conn.commit()

    #GET ID BACK FROM ELECTROLYTES TABLE BY CHECKING ALL ATTRIBUTES
    # Generate the parts of the WHERE clause
    clauses = [f"{attr} = ?" for attr in attr_dict.keys()]
    where_clause = " AND ".join(clauses)

    query = f"SELECT id FROM electrolytes WHERE {where_clause}"
    
    c.execute(query, tuple(attr_dict.values()))
    
    matched_ids = c.fetchall()[0]

    c.execute('SELECT MAX(id) FROM electrolytes')
    electrolyte_id = c.fetchone()[0]

    if (electrolyte_id in matched_ids) and electrolyte_id != matched_ids:
      matched_ids.remove(electrolyte_id)
      print(f"Electrolytes with id(s): {matched_ids} have exactly identical attributes.")

    for formula, amount in components.items():
        chemical = Chemical(formula)
        c.execute("SELECT ID FROM components WHERE formula=?", (str(chemical),))

        component_id = c.fetchone()[0]
        print(electrolyte_id,component_id,amount)
        c.execute("INSERT INTO electrolyte_components (electrolyte_id, component_id, amount) VALUES (?, ?, ?)",
                  (electrolyte_id, component_id, amount))
        conn.commit()
    conn.close()

def check_electrolyte_exists(components: dict):
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    #long query string
    query_string = "SELECT e.id FROM electrolytes e WHERE e.id IN (SELECT ec.electrolyte_id FROM electrolyte_components ec WHERE "
    query_conditions = []
    query_values = []
    for formula, amount in components.items():
        chemical = Chemical(formula)
        query_conditions.append("(ec.component_id = (SELECT ID FROM components WHERE formula = ?) AND ec.amount = ?)")
        query_values.extend([str(chemical), amount])
    query_string += " OR ".join(query_conditions) + " GROUP BY ec.electrolyte_id HAVING COUNT(ec.electrolyte_id) = ?)"
    query_values.append(len(components))

    c.execute(query_string, query_values)
    candidate_ids = [row[0] for row in c.fetchall()]

    #check that each candidate id doesn't have extra components
    for id in candidate_ids:
        c.execute("SELECT COUNT(*) FROM Electrolyte_Components WHERE Electrolyte_ID = ?", (id,))
        if c.fetchone()[0] != len(components):
            candidate_ids.remove(id)
    conn.close()

    # If we have at least one result, the electrolyte exists
    return len(candidate_ids) > 0

def get_components_by_id(electrolyte_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    query = """
    SELECT c.formula, ec.amount
    FROM electrolyte_components ec 
    JOIN components c ON ec.component_id = c.id
    WHERE ec.electrolyte_id = ?
    """

    c.execute(query, (electrolyte_id,))
    result = c.fetchall()

    conn.close()

    # Return the components
    return {row[0]: row[1] for row in result}

def add_component_type(
    chemical: Chemical
):
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    #check if chemical is already in database
    c.execute("SELECT * FROM components WHERE formula = ?", (chemical.__str__(),))
    conn.commit()
    rows = c.fetchall()

    if(len(rows) != 0):
      print(f'{str(len(rows))} entries with formula {chemical.__str__()} already in database')
    else:
      c.execute("INSERT INTO components (formula, molality, price) VALUES (?,?,?)", (str(chemical), chemical.molality, chemical.price))
      conn.commit()
      conn.close()

def get_component_type(
    formula: str
):
    formatted_formula = Chemical(formula).__str__()

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute("SELECT * FROM components WHERE formula = ?", (Chemical(formula).__str__(),))
    conn.commit()
    rows = c.fetchall()

    if len(rows) > 1:
        print(f'Multiple components found for formula {formula}')
    elif len(rows) == 0:
        print(f'No components found for formula {formula}')
    else:
        print(rows[0][1], rows[0][2], rows[0][3])
        return Chemical(rows[0][1], rows[0][2], rows[0][3])
    
    conn.close()

def remove_component_type(
    formula: str
):
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    formatted = Chemical(formula).__str__()

    c.execute("SELECT * FROM components WHERE formula = ?", (formatted,))
    conn.commit()
    fetched = c.fetchall()
    if len(fetched) == 0:
        print(f'No components found for formula {formula}')
    else:
        c.execute("DELETE FROM components WHERE formula = ?", (formatted,))
        print("Deleted " + str(len(fetched)) + f" entries for formula {formula}.")
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