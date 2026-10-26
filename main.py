from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import psycopg2
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel
from typing import List, Optional
import datetime

app = FastAPI(title="Gastro WMS API Pro - Local Fixed", version="3.8.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_CONFIG = {
    "dbname": "postgres",
    "user": "postgres",
    "password": "kamil8108.",
    "host": "127.0.0.1",
    "port": "5432"
}

def get_db():
    return psycopg2.connect(**DB_CONFIG)

def init_db():
    """Inicjalizacja i migracja lokalnej bazy danych"""
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ksef_config (
                id SERIAL PRIMARY KEY,
                nip VARCHAR(20) NOT NULL,
                token TEXT NOT NULL,
                environment VARCHAR(20) DEFAULT 'TEST',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS raw_materials (
                id SERIAL PRIMARY KEY,
                sku VARCHAR(100) UNIQUE NOT NULL,
                name VARCHAR(255) NOT NULL,
                unit VARCHAR(20) DEFAULT 'g',
                avg_purchase_price_net NUMERIC(10, 4) DEFAULT 0.0,
                current_stock NUMERIC(10, 2) DEFAULT 0.0,
                yield_percentage NUMERIC(5, 2) DEFAULT 100.0,
                category VARCHAR(50) DEFAULT 'jedzenie'
            );
            CREATE TABLE IF NOT EXISTS menu_items (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                price_gross NUMERIC(10, 2) NOT NULL,
                vat_rate NUMERIC(5, 2) DEFAULT 8.0,
                external_pos_id VARCHAR(100)
            );
            CREATE TABLE IF NOT EXISTS recipes (
                id SERIAL PRIMARY KEY,
                menu_item_id INT REFERENCES menu_items(id) ON DELETE CASCADE,
                raw_material_id INT REFERENCES raw_materials(id) ON DELETE CASCADE,
                quantity_required NUMERIC(10, 4) NOT NULL
            );
            CREATE TABLE IF NOT EXISTS price_alerts (
                id SERIAL PRIMARY KEY,
                raw_material_id INT REFERENCES raw_materials(id) ON DELETE CASCADE,
                old_price NUMERIC(10, 4),
                new_price NUMERIC(10, 4),
                percentage_increase NUMERIC(10, 2),
                status VARCHAR(20) DEFAULT 'UNREAD',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS ksef_invoices (
                id SERIAL PRIMARY KEY,
                invoice_number VARCHAR(100) NOT NULL,
                supplier_nip VARCHAR(20) NOT NULL,
                supplier_name VARCHAR(255),
                total_gross NUMERIC(10, 2),
                status VARCHAR(50) DEFAULT 'POBRANA',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

        migrations = [
            "ALTER TABLE raw_materials ADD COLUMN IF NOT EXISTS category VARCHAR(50) DEFAULT 'jedzenie';",
            "ALTER TABLE raw_materials ADD COLUMN IF NOT EXISTS current_stock NUMERIC(10, 2) DEFAULT 0.0;",
            "ALTER TABLE raw_materials ADD COLUMN IF NOT EXISTS yield_percentage NUMERIC(5, 2) DEFAULT 100.0;",
            "ALTER TABLE raw_materials ADD COLUMN IF NOT EXISTS avg_purchase_price_net NUMERIC(10, 4) DEFAULT 0.0;",
            "ALTER TABLE raw_materials ADD COLUMN IF NOT EXISTS sku VARCHAR(100);",
            "ALTER TABLE raw_materials ADD COLUMN IF NOT EXISTS unit VARCHAR(20) DEFAULT 'g';",
            "ALTER TABLE menu_items ADD COLUMN IF NOT EXISTS vat_rate NUMERIC(5, 2) DEFAULT 8.0;",
            "ALTER TABLE menu_items ADD COLUMN IF NOT EXISTS external_pos_id VARCHAR(100);"
        ]
        
        for q in migrations:
            try:
                cur.execute(q)
                conn.commit()
            except Exception:
                conn.rollback()

        cur.close()
        conn.close()
        print("✅ Baza PostgreSQL połączona pomyślnie!")
    except Exception as e:
        print("❌ Błąd połączenia z bazą:", e)

@app.on_event("startup")
def startup_event():
    init_db()

# --- SERWOWANIE DASHBOARDU ---
@app.get("/")
def serve_root():
    return FileResponse("dashboard.html")

@app.get("/dashboard")
def serve_dashboard():
    return FileResponse("dashboard.html")

# --- MODELE PYDANTIC ---

class MaterialCreate(BaseModel):
    sku: str
    name: str
    unit: str
    avg_purchase_price_net: float
    current_stock: float
    yield_percentage: Optional[float] = 100.0
    category: Optional[str] = "jedzenie"

class MaterialUpdate(BaseModel):
    sku: str
    name: str
    unit: str
    avg_purchase_price_net: float
    current_stock: float
    yield_percentage: Optional[float] = 100.0
    category: Optional[str] = "jedzenie"

class MenuItemCreate(BaseModel):
    name: str
    price_gross: float
    vat_rate: Optional[float] = 8.0
    external_pos_id: Optional[str] = None

class MenuItemUpdate(BaseModel):
    name: str
    price_gross: float
    vat_rate: Optional[float] = 8.0
    external_pos_id: Optional[str] = None

class RecipeItem(BaseModel):
    raw_material_id: int
    quantity_required: float

class RecipeCreate(BaseModel):
    menu_item_id: int
    ingredients: List[RecipeItem]

class KsefInvoiceItem(BaseModel):
    sku: str
    name: str
    unit: str
    quantity: float
    unit_price_net: float
    category: Optional[str] = "jedzenie"

class KsefInvoice(BaseModel):
    invoice_number: str
    supplier_nip: str
    supplier_name: Optional[str] = "Dostawca KSeF"
    items: List[KsefInvoiceItem]

class SaleOrder(BaseModel):
    menu_item_id: int
    quantity_sold: float
    source_platform: str

# --- ENDPOINTY: SUROWCE I KATEGORIE ---

@app.get("/raw-materials")
def get_raw_materials(category: Optional[str] = None):
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if category and category != 'all':
            cur.execute("SELECT * FROM raw_materials WHERE category = %s ORDER BY name;", (category,))
        else:
            cur.execute("SELECT * FROM raw_materials ORDER BY name;")
        items = cur.fetchall()
        cur.close()
        conn.close()
        return {"raw_materials": items}
    except Exception as e:
        print("❌ Błąd pobierania surowców:", e)
        return {"raw_materials": []}

@app.post("/raw-materials")
def create_raw_material(mat: MaterialCreate):
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            INSERT INTO raw_materials (sku, name, unit, avg_purchase_price_net, current_stock, yield_percentage, category)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *;
        """, (mat.sku, mat.name, mat.unit, mat.avg_purchase_price_net, mat.current_stock, mat.yield_percentage or 100.0, mat.category or 'jedzenie'))
        new_mat = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "data": new_mat}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/raw-materials/{mat_id}")
def update_raw_material(mat_id: int, mat: MaterialUpdate):
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            UPDATE raw_materials 
            SET sku = %s, name = %s, unit = %s, avg_purchase_price_net = %s, current_stock = %s, yield_percentage = %s, category = %s
            WHERE id = %s RETURNING *;
        """, (mat.sku, mat.name, mat.unit, mat.avg_purchase_price_net, mat.current_stock, mat.yield_percentage or 100.0, mat.category or 'jedzenie', mat_id))
        updated_mat = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "data": updated_mat}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/raw-materials/{mat_id}")
def delete_raw_material(mat_id: int):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM raw_materials WHERE id = %s;", (mat_id,))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Usunięto pozycję."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- ENDPOINTY: MENU & RECEPTURY ---

@app.get("/menu-items")
def get_menu_items():
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM menu_items ORDER BY name;")
        items = cur.fetchall()
        cur.close()
        conn.close()
        return {"menu_items": items}
    except Exception:
        return {"menu_items": []}

@app.post("/menu-items")
def create_menu_item(item: MenuItemCreate):
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            INSERT INTO menu_items (name, price_gross, vat_rate, external_pos_id)
            VALUES (%s, %s, %s, %s) RETURNING *;
        """, (item.name, item.price_gross, item.vat_rate or 8.0, item.external_pos_id))
        new_item = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "data": new_item}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/menu-items/{item_id}")
def update_menu_item(item_id: int, item: MenuItemUpdate):
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            UPDATE menu_items 
            SET name = %s, price_gross = %s, vat_rate = %s, external_pos_id = %s
            WHERE id = %s RETURNING *;
        """, (item.name, item.price_gross, item.vat_rate or 8.0, item.external_pos_id, item_id))
        updated_item = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "data": updated_item}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/menu-items/{item_id}")
def delete_menu_item(item_id: int):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM menu_items WHERE id = %s;", (item_id,))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Usunięto danie."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/recipes/{menu_item_id}")
def get_recipe(menu_item_id: int):
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT r.id, r.raw_material_id, rm.name AS material_name, rm.unit, 
                   r.quantity_required, rm.avg_purchase_price_net, rm.yield_percentage, rm.category
            FROM recipes r
            JOIN raw_materials rm ON r.raw_material_id = rm.id
            WHERE r.menu_item_id = %s;
        """, (menu_item_id,))
        ingredients = cur.fetchall()
        
        total_dish_cost = 0.0
        calculated_ingredients = []
        for ing in ingredients:
            yield_pct = float(ing["yield_percentage"]) if ing["yield_percentage"] and float(ing["yield_percentage"]) > 0 else 100.0
            unit_price = float(ing["avg_purchase_price_net"]) / (yield_pct / 100.0)
            cost = float(ing["quantity_required"]) * unit_price
            total_dish_cost += cost
            calculated_ingredients.append({
                "id": ing["id"],
                "raw_material_id": ing["raw_material_id"],
                "material_name": ing["material_name"],
                "unit": ing["unit"],
                "quantity_required": float(ing["quantity_required"]),
                "avg_purchase_price_net": float(ing["avg_purchase_price_net"]),
                "yield_percentage": yield_pct,
                "category": ing["category"],
                "cost_net": round(cost, 2)
            })
            
        for ing in calculated_ingredients:
            ing["fc_share_percentage"] = round((ing["cost_net"] / total_dish_cost) * 100, 2) if total_dish_cost > 0 else 0.0

        cur.close()
        conn.close()
        return {
            "ingredients": calculated_ingredients,
            "total_production_cost_net": round(total_dish_cost, 2)
        }
    except Exception:
        return {"ingredients": [], "total_production_cost_net": 0.0}

@app.post("/recipes")
def save_recipe(recipe: RecipeCreate):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM recipes WHERE menu_item_id = %s;", (recipe.menu_item_id,))
        for ing in recipe.ingredients:
            cur.execute("""
                INSERT INTO recipes (menu_item_id, raw_material_id, quantity_required)
                VALUES (%s, %s, %s);
            """, (recipe.menu_item_id, ing.raw_material_id, ing.quantity_required))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Receptura zapisana!"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/food-cost")
def get_food_cost():
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT m.id, m.name AS dish_name, m.price_gross, COALESCE(m.vat_rate, 8.0) AS vat_rate, m.external_pos_id,
                   COALESCE(SUM(
                       r.quantity_required * (rm.avg_purchase_price_net / (CASE WHEN COALESCE(rm.yield_percentage, 100.0) <= 0 THEN 1.0 ELSE COALESCE(rm.yield_percentage, 100.0) / 100.0 END))
                   ), 0) AS production_cost_net
            FROM menu_items m
            LEFT JOIN recipes r ON m.id = r.menu_item_id
            LEFT JOIN raw_materials rm ON r.raw_material_id = rm.id
            GROUP BY m.id, m.name, m.price_gross, m.vat_rate, m.external_pos_id
            ORDER BY m.name;
        """)
        items = cur.fetchall()
        
        for item in items:
            price_gross = float(item["price_gross"]) if item["price_gross"] else 0.0
            vat = float(item["vat_rate"]) if item["vat_rate"] else 8.0
            price_net = price_gross / (1 + vat / 100.0)
            cost = float(item["production_cost_net"])
            
            fc = round((cost / price_net) * 100, 2) if price_net > 0 else 0.0
            item["food_cost_percentage"] = fc

        cur.close()
        conn.close()
        return {"food_cost_analysis": items}
    except Exception:
        return {"food_cost_analysis": []}

@app.post("/integrations/process-sale")
def process_pos_sale(sale: SaleOrder):
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT raw_material_id, quantity_required FROM recipes WHERE menu_item_id = %s;", (sale.menu_item_id,))
        ingredients = cur.fetchall()
        
        if not ingredients:
            cur.close()
            conn.close()
            raise HTTPException(status_code=400, detail="Wybrane danie nie posiada przypisanej receptury (BOM)!")
            
        for ing in ingredients:
            qty_needed = float(ing["quantity_required"]) * sale.quantity_sold
            cur.execute("UPDATE raw_materials SET current_stock = current_stock - %s WHERE id = %s;", (qty_needed, ing["raw_material_id"]))
            
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": f"Przyjęto zamówienie z [{sale.source_platform}]. Rozchodowano surowce w magazynie!"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- ENDPOINTY KSEF ---

@app.get("/ksef/config")
def get_ksef_config():
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT nip, token, environment FROM ksef_config ORDER BY id DESC LIMIT 1;")
        config = cur.fetchone()
        cur.close()
        conn.close()
        return {"config": config or {"nip": "", "token": "", "environment": "TEST"}}
    except Exception:
        return {"config": {"nip": "", "token": "", "environment": "TEST"}}

@app.post("/ksef/config")
def save_ksef_config(conf: KsefConfigModel):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM ksef_config;")
        cur.execute("""
            INSERT INTO ksef_config (nip, token, environment)
            VALUES (%s, %s, %s);
        """, (conf.nip, conf.token, conf.environment or "TEST"))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Konfiguracja zapisana."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/ksef/fetch-auto")
def fetch_ksef_auto():
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT nip, token FROM ksef_config ORDER BY id DESC LIMIT 1;")
        conf = cur.fetchone()
        cur.close()
        conn.close()

        if not conf or not conf.get("nip"):
            raise HTTPException(status_code=400, detail="Brak wprowadzonego NIP-u KSeF!")

        now_str = datetime.datetime.now().strftime("%Y%m%d/%H%M")
        mock_invoice = KsefInvoice(
            invoice_number=f"KSEF/{now_str}",
            supplier_nip="5250005834",
            supplier_name="Hurtownia Gastro Sp. z o.o.",
            items=[
                KsefInvoiceItem(sku="SUROW-001", name="Boczek wędzony / Shoyu", unit="g", quantity=3000, unit_price_net=0.0350, category="jedzenie"),
                KsefInvoiceItem(sku="SUROW-002", name="Płyn do naczyń Gastrex", unit="ml", quantity=5000, unit_price_net=0.0120, category="chemia"),
                KsefInvoiceItem(sku="SUROW-003", name="Pudełko Wynos KRAFT", unit="szt", quantity=200, unit_price_net=0.4500, category="opakowania"),
                KsefInvoiceItem(sku="KOSZT-001", name="Energia Elektryczna (PGE)", unit="szt", quantity=1, unit_price_net=1450.00, category="prad"),
                KsefInvoiceItem(sku="KOSZT-002", name="Czynsz dzierżawy lokalu", unit="szt", quantity=1, unit_price_net=4500.00, category="czynsz")
            ]
        )
        return process_ksef_invoice(mock_invoice)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/ksef/process-invoice")
def process_ksef_invoice(inv: KsefInvoice):
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        total_gross_sum = 0.0

        for item in inv.items:
            total_gross_sum += item.quantity * item.unit_price_net * 1.23
            cur.execute("SELECT id, avg_purchase_price_net, current_stock FROM raw_materials WHERE sku = %s OR name = %s;", (item.sku, item.name))
            material = cur.fetchone()
            
            if material:
                mat_id = material["id"]
                old_price = float(material["avg_purchase_price_net"])
                new_price = item.unit_price_net
                
                if old_price > 0:
                    pct = ((new_price - old_price) / old_price) * 100
                    if pct > 2.0:
                        cur.execute("""
                            INSERT INTO price_alerts (raw_material_id, old_price, new_price, percentage_increase, status)
                            VALUES (%s, %s, %s, %s, 'UNREAD');
                        """, (mat_id, old_price, new_price, round(pct, 2)))
                
                new_stock = float(material["current_stock"]) + item.quantity
                cur.execute("""
                    UPDATE raw_materials 
                    SET avg_purchase_price_net = %s, current_stock = %s, category = %s
                    WHERE id = %s;
                """, (new_price, new_stock, item.category or 'jedzenie', mat_id))
            else:
                cur.execute("""
                    INSERT INTO raw_materials (sku, name, unit, avg_purchase_price_net, current_stock, yield_percentage, category)
                    VALUES (%s, %s, %s, %s, %s, 100.0, %s);
                """, (item.sku, item.name, item.unit, item.unit_price_net, item.quantity, item.category or 'jedzenie'))

        cur.execute("""
            INSERT INTO ksef_invoices (invoice_number, supplier_nip, supplier_name, total_gross, status)
            VALUES (%s, %s, %s, %s, 'POBRANA');
        """, (inv.invoice_number, inv.supplier_nip, inv.supplier_name or 'Dostawca KSeF', round(total_gross_sum, 2)))

        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "invoice_processed": inv.invoice_number}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/ksef/invoices")
def get_ksef_invoices():
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM ksef_invoices ORDER BY created_at DESC LIMIT 20;")
        invoices = cur.fetchall()
        cur.close()
        conn.close()
        return {"invoices": invoices}
    except Exception:
        return {"invoices": []}

@app.get("/alerts")
def get_price_alerts():
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT a.id, rm.name AS material_name, a.old_price, a.new_price, 
                   a.percentage_increase, a.status, a.created_at
            FROM price_alerts a
            JOIN raw_materials rm ON a.raw_material_id = rm.id
            ORDER BY a.created_at DESC;
        """)
        alerts = cur.fetchall()
        cur.close()
        conn.close()
        return {"alerts": alerts}
    except Exception:
        return {"alerts": []}