#ADD TEXT NOTE BOX FOR COMPONENTS TABLE
#MULTILINE COMMENTS FOR FUNCTIONS

import sqlite3
import re
from collections import Counter
from typing import List, Optional
import asyncio
from datetime import datetime

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import pandas as pd
from urllib.parse import quote

DB = 'experiment_db.sqlite'

def start_server():
    '''
    used in test.py to start sqlite server with tables
    '''

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
    conn.commit()
    conn.close()

class Chemical:
    '''
    Object to process chemical component types; takes in chemical formulas, and stores dictionary, 'elements,'
    with counts of each element.
    '''
    ELEMENTS = ['H', 'He', 'Li', 'Be', 'B', 'C', 'N', 'O', 'F', 'Ne', 'Na', 'Mg'
    , 'Al', 'Si', 'P', 'S', 'Cl', 'Ar', 'K', 'Ca', 'Sc', 'Ti', 'V', 'Cr', 'Mn',
    'Fe', 'Co', 'Ni', 'Cu', 'Zn', 'Ga', 'Ge', 'As', 'Se', 'Br', 'Kr','Rb', 'Sr',
    'Y', 'Zr', 'Nb', 'Mo', 'Tc', 'Ru', 'Rh', 'Pd', 'Ag', 'Cd', 'In', 'Sn', 'Sb',
    'Te', 'I', 'Xe', 'Cs', 'Ba', 'La', 'Ce', 'Pr', 'Nd', 'Pm', 'Sm', 'Eu', 'Gd',
    'Tb', 'Dy', 'Ho', 'Er', 'Tm', 'Yb', 'Lu', 'Hf', 'Ta', 'W', 'Re', 'Os', 'Ir',
    'Pt', 'Au', 'Hg', 'Tl', 'Pb', 'Bi', 'Th', 'Pa', 'U', 'Np', 'Pu', 'Am', 'Cm',
    'Bk','Cf', 'Es', 'Fm', 'Md', 'No', 'Lr', 'Rf', 'Db', 'Sg', 'Bh', 'Hs', 'Mt',
     'Ds', 'Rg', 'Cn', 'Nh', 'Fl', 'Mc', 'Lv', 'Ts', 'Og']
    def __init__(self, formula=' ', notes='', molar_mass=0, price=0):
        self.elements = self.parse_formula(formula)
        self.notes = notes
        self.molar_mass = molar_mass
        self.price = price # PRICE IS IN TERMS OF $/ML AND $/G

    def parse_formula(self, formula): #recursive function to parse equivalent formulas
        '''
        Recursively parses through a formula string, accounting for parentheses and different orderings for elements.
        Returns a 'Counter' object, which is really just a dictionary with elements on the left, and amounts on the
        right.
        '''

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
        '''
        equivalence check which compares elements.
        '''
        if isinstance(other, Chemical):
            return self.elements == other.elements
        return False

    def __str__(self):
        '''
        outputs formula as a string with elements sorted by element number
        '''
        sorted_elements = sorted(self.elements.items(), key=lambda x: self.ELEMENTS.index(x[0]))
        return ''.join(f'{element}{count}' if count > 1 else f'{element}' for element, count in sorted_elements)

def get_electrolyte_by_components(components: dict):
    '''
    takes in dictionary of components and amounts, ex: {"formula1": 3.23, "formula2": .57}
    returns id of an electrolyte.
    '''
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
    conn.commit()
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

    adds a new electrolyte to database with components as dictionary
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
    try:
        matched_ids = c.fetchall()[0]
    except:
        matched_ids = []

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
    '''
    Checks if an electrolyte with matching components and amounts already exists in the dictionary.
    '''

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
    conn.commit()
    conn.close()

    # If we have at least one result, the electrolyte exists
    return len(candidate_ids) > 0

def get_components_by_id(electrolyte_id):
    '''
    takes in electrolyte id, and returns dictionary of components and amounts per component
    '''
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
    '''
    self-evident--only takes in Chemical class
    '''
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    #check if chemical is already in database
    c.execute("SELECT * FROM components WHERE formula = ?", (chemical.__str__(),))
    conn.commit()
    rows = c.fetchall()

    if(len(rows) != 0):
      print(f'{str(len(rows))} entries with formula {chemical.__str__()} already in database')
    else:
      c.execute("INSERT INTO components (formula, notes, molar_mass, price) VALUES (?,?,?,?)", (str(chemical),chemical.notes, chemical.molar_mass, chemical.price))
      conn.commit()
      conn.close()

def get_component_type(
    formula: str
):
    '''
    returns chemical type of a component, from just its formula.
    '''
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
        print(rows[0][1], rows[0][2], rows[0][3], rows[0][4])
        return Chemical(rows[0][1], rows[0][2], rows[0][3], rows[0][4])
    
    conn.close()

def remove_component_type(
    formula: str
):
    '''
    removes component from table just from formula
    '''
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

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def write_excel():
    def get_the_time():
        now = datetime.now("%Y-%m-%d_%H-%M-%S")
        return now.strftime()
    conn = sqlite3.connect(DB)

    # List your tables here
    tables = ["electrolytes", "electrolyte_components", "components"]
    with pd.ExcelWriter('/app/history/tables.xlsx') as writer:
        for table in tables:
            df = pd.read_sql_query(f"SELECT * from {table}", conn)
            df.to_excel(writer, sheet_name=table, index = False)

    conn.close()
    file_name = f"table_{get_the_time()}.xlsx"
    return FileResponse('tables.xlsx', media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', filename=file_name)

async def save_tables():
    while True:
        await write_excel()
        await asyncio.sleep(60)

@app.on_event("startup")
async def startup_event():
    bg_tasks = BackgroundTasks()
    bg_tasks.add_task(write_excel)

app.mount("/static", StaticFiles(directory="../static"), name="static")

templates = Jinja2Templates(directory="../templates")

@app.get("/", response_class=HTMLResponse)
async def static(request: Request):
    return templates.TemplateResponse("alec.html", {"request": request})

@app.post("/input_electrolyte/")
async def input_electrolyte(
    request: Request,
    component_types: Optional[str] = Form(...), #not actually optional
    amounts: Optional[str] = Form(...),
    conductivity: Optional[float] = Form(...),
    conduct_uncert_bound: Optional[float] = Form(...),
    concent_uncert_bound: Optional[float] = Form(...),

    density: Optional[float] = Form(None), # Actually Optional
    temperature: Optional[float] = Form(None),
    viscosity: Optional[float] = Form(None),
    v_window_low_bound: Optional[float] = Form(None),
    v_window_high_bound: Optional[float] = Form(None),
    surface_tension: Optional[float] = Form(None),
):
    def str2dict(string1 = component_types, string2 = amounts):
        # Split the strings into lists
        str_list = string1.split()
        float_list = [float(x) for x in string2.split()]

        if len(str_list) != len(float_list): raise ValueError
        # Create a dictionary from the two lists
        dictionary = dict(zip(str_list, float_list))
        return dictionary
    
    components = str2dict(component_types, amounts)

    def str_to_float(s):
        return float(s) if s else None

    density = str_to_float(density)
    temperature = str_to_float(temperature)
    viscosity = str_to_float(viscosity)
    v_window_low_bound = str_to_float(v_window_low_bound)
    v_window_high_bound = str_to_float(v_window_high_bound)
    surface_tension = str_to_float(surface_tension)

    try:
        add_electrolyte(
            components,
            conductivity,
            conduct_uncert_bound,
            concent_uncert_bound,

            density,
            temperature,
            viscosity,
            v_window_low_bound,
            v_window_high_bound,
            surface_tension
        )
        response_str = 'Success!'
    except(TypeError):
        response_str = 'Your formula syntaxes are wrong somehow.'
    except ValueError as e:
        response_str = "Error Occurred, see message and try again: " + e.args[0]
    except IndexError as e:
        response_str = "Error Occurred, see message and try again: " + e.args[0]

    encoded_message = quote(response_str)

    url = f"{app.url_path_for('input_electrolyte_form')}?message={encoded_message}"
    response = RedirectResponse(url=url, status_code=303)
    return response

@app.get("/input_electrolyte/", response_class=HTMLResponse)
async def input_electrolyte_form(request: Request, message: Optional[str] = None):
    return templates.TemplateResponse("alec.html", {"request": request, "message": message})

@app.post("/input_component/")
async def input_component(
    request: Request, #NONE OF THESE ARE ACTUALLY OPTIONAL, FASTAPI IS JUST WEIRD
    formula: Optional[str] = Form(...),
    notes: Optional[str] = Form(None),
    molar_mass: Optional[float] = Form(...),
    price: Optional[float] = Form(...)
):
    try:
        response_str = 'Success!'
        component = Chemical(formula, notes, molar_mass, price)
        add_component_type(component)

    except Exception as e:
        response_str = "Error Occurred, see message and try again: " + e.args[0]
    encoded_message = quote(response_str)

    url = f"{app.url_path_for('input_component_form')}?message={encoded_message}"
    response = RedirectResponse(url=url, status_code=303)
    return response


@app.get("/input_component/", response_class=HTMLResponse)
async def input_component_form(request: Request, message: Optional[str] = None):
    return templates.TemplateResponse("alec.html", {"request": request, "message": message})

@app.post("/execute_sql/")
async def execute_sql(sql_query: str = Form(...)):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(sql_query)
    results = c.fetchall()
    conn.commit()
    conn.close()
    return JSONResponse(content=results)

@app.get("/download_excel/")
async def download_excel():
    conn = sqlite3.connect(DB)

    # List your tables here
    tables = ["electrolytes", "electrolyte_components", "components"]
    with pd.ExcelWriter('tables.xlsx') as writer:
        for table in tables:
            df = pd.read_sql_query(f"SELECT * from {table}", conn)
            df.to_excel(writer, sheet_name=table, index = False)

    conn.close()

    return FileResponse('tables.xlsx', media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', filename='tables.xlsx')

@app.post("/upload_excel/")
async def upload_excel(file: UploadFile = File(...)):
    df_dict = pd.read_excel(file.file, sheet_name=None)

    conn = sqlite3.connect(DB)

    for table_name, df in df_dict.items():
        df.to_sql(table_name, conn, if_exists='append', index=False)

    conn.close()

    return {"detail": "Data successfully uploaded from Excel file"}