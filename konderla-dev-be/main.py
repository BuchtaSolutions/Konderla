from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import List, Optional
from database import engine, Base, get_db
import models, schemas, crud
from uuid import UUID
import google.generativeai as genai
import os
import json
import shutil
from dotenv import load_dotenv
import httpx
import difflib
import excel_processor
import pdf_export
from fastapi.responses import FileResponse

# Load environment variables
# Try loading from standard locations
if os.path.exists('/.env'):
    load_dotenv('/.env')
elif os.path.exists(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')):
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

# Create tables on startup
models.Base.metadata.create_all(bind=engine)

# Create uploads directory
os.makedirs("uploads", exist_ok=True)

app = FastAPI()


@app.on_event("startup")
def startup_log():
    print("[Backend] Started. Excel: Var 3 (Soupis PČ/Typ/Kód + D/K) pattern enabled for all matching sheets.")


app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# CORS: s allow_credentials=True nelze použít allow_origins=["*"] – prohlížeč to blokuje.
# Nastav CORS_ORIGINS (oddělené čárkou), výchozí je localhost pro FE.
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").strip()
cors_list = [o.strip() for o in _cors_origins.split(",") if o.strip()] or [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# Gemini Setup
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("NEXT_PUBLIC_GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    # Use gemini-2.0-flash as it is available in the current model list
    model = genai.GenerativeModel('gemini-2.0-flash')
else:
    model = None
    print("Warning: GOOGLE_API_KEY not set")

def generate_project_context(db: Session, project_id: UUID) -> str:
    project = crud.get_project(db, project_id)
    if not project:
        return ""
    
    rounds = crud.get_rounds_by_project(db, project_id)
    
    context = f"Project: {project.name}\nDescription: {project.description}\n\n"
    
    for r in rounds:
        context += f"Round: {r.name} (Order: {r.order}, Status: {r.status})\n"
        budgets = crud.get_budgets_by_round(db, r.id)
        for b in budgets:
            items_str = json.dumps(b.items) if b.items else "[]"
            context += f"  - Budget: {b.name}, Score: {b.score}, Price Items: {items_str}\n"
            if b.parent_budget_id:
                context += f"    (Derived from Budget ID: {b.parent_budget_id})\n"
        context += "\n"
        
    return context

@app.get("/")
def read_root():
    return {"Hello": "World"}

# Projects
@app.post("/projects/", response_model=schemas.Project)
def create_project(project: schemas.ProjectCreate, db: Session = Depends(get_db)):
    return crud.create_project(db=db, project=project)

@app.get("/projects/", response_model=List[schemas.Project])
def read_projects(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_projects(db, skip=skip, limit=limit)

@app.get("/projects/{project_id}", response_model=schemas.Project)
def read_project(project_id: UUID, db: Session = Depends(get_db)):
    db_project = crud.get_project(db, project_id=project_id)
    if db_project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return db_project

@app.put("/projects/{project_id}", response_model=schemas.Project)
def update_project(project_id: UUID, project: schemas.ProjectUpdate, db: Session = Depends(get_db)):
    db_project = crud.update_project(db, project_id=project_id, project_update=project)
    if db_project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return db_project

@app.delete("/projects/{project_id}", response_model=schemas.Project)
def delete_project(project_id: UUID, db: Session = Depends(get_db)):
    db_project = crud.delete_project(db, project_id=project_id)
    if db_project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return db_project

@app.post("/budgets/upload-excel")
async def upload_budget_excel(
    project_id: UUID = Form(...),
    round_id: UUID = Form(...),
    name: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    try:
        # 1. Save File
        file_location = f"uploads/{file.filename}"
        with open(file_location, "wb+") as file_object:
            shutil.copyfileobj(file.file, file_object)
            
        # 2. Process File
        print(f"[Upload] Processing file: {file.filename}")
        data = excel_processor.process_excel_file(file_location, provided_name=name)
        
        if not data:
             raise HTTPException(status_code=400, detail="Could not parse Excel file. Format not recognized.")
        
        print(f"[Upload] Parsed as type: {data.get('type')}")
        print(f"[Upload] Parent budget items: {len(data.get('parent_budget', {}).get('items', []))}")
        print(f"[Upload] Child budgets: {len(data.get('child_budgets', []))}")
             
        # 3. Create Parent Budget
        parent_info = data["parent_budget"]

        # Název rozpočtu: pokud uživatel zadal name při uploadu, vždy ho použij; jinak z Excelu nebo filename
        if name and str(name).strip():
            budget_name = str(name).strip()
        else:
            budget_name = parent_info["name"]
            if "Hlavní rozpočet" in budget_name or "Stavba" in budget_name:
                budget_name = os.path.splitext(file.filename)[0]

        parent_labels = {"type": data["type"], "is_parent": True}
        if data.get("type") == "type3" and parent_info.get("total_price") is not None:
            parent_labels["total_price"] = parent_info["total_price"]
        parent_budget = models.Budget(
            project_id=project_id,
            round_id=round_id,
            name=budget_name,
            items=parent_info["items"],
            file_path=file_location,
            labels=parent_labels,
        )
        print(f"Creating parent budget: name='{budget_name}', items={len(parent_info['items'])}")
        for i, item in enumerate(parent_info["items"][:20]):  # Log first 20 items
            print(f"  Parent item {i+1}: number='{item.get('number', '')}' name='{item.get('name', '')[:50]}' price={item.get('price', 0)}")
        db.add(parent_budget)
        db.commit()
        db.refresh(parent_budget)
        
        # 4. Create Child Budgets – každý má svůj vlastní název z child["name"]
        print(f"Creating {len(data['child_budgets'])} child budgets for parent_id={parent_budget.id}...")
        created_child_ids = []
        for i, child in enumerate(data["child_budgets"]):
            child_name = child.get("name", f"{budget_name} - {i+1}")
            child_items = child.get("items", [])
            print(f"  Creating child budget {i+1}: name='{child_name}', items={len(child_items)}, parent_id={parent_budget.id}")
            child_labels = {"type": data["type"], "is_child": True, "code": child.get("number_code")}
            if child.get("parent_item_code") is not None:
                child_labels["parent_item_code"] = child["parent_item_code"]
            child_budget = models.Budget(
                project_id=project_id,
                round_id=round_id,
                parent_budget_id=parent_budget.id,
                name=child_name,
                items=child_items,
                file_path=file_location,
                labels=child_labels,
            )
            db.add(child_budget)
            db.flush()  # Flush to get the ID
            created_child_ids.append(child_budget.id)
            print(f"    Created child budget with id={child_budget.id}, parent_budget_id={child_budget.parent_budget_id}")
            
        db.commit()
        print(f"Successfully created {len(data['child_budgets'])} child budgets with IDs: {created_child_ids}")
        
        return {
            "message": "Budget processed successfully", 
            "parent_id": parent_budget.id, 
            "child_count": len(data["child_budgets"]),
            "type": data["type"]
        }
        
    except Exception as e:
        print(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def delete_project(project_id: UUID, db: Session = Depends(get_db)):
    db_project = crud.delete_project(db, project_id=project_id)
    if db_project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return db_project

# Rounds
@app.post("/rounds/", response_model=schemas.Round)
def create_round(round: schemas.RoundCreate, db: Session = Depends(get_db)):
    return crud.create_round(db=db, round=round)

@app.get("/projects/{project_id}/rounds/", response_model=List[schemas.Round])
def read_rounds(project_id: UUID, db: Session = Depends(get_db)):
    return crud.get_rounds_by_project(db, project_id=project_id)

@app.delete("/rounds/{round_id}", response_model=schemas.Round)
def delete_round(round_id: UUID, db: Session = Depends(get_db)):
    db_round = crud.delete_round(db=db, round_id=round_id)
    if db_round is None:
        raise HTTPException(status_code=404, detail="Round not found")
    return db_round

# Budgets
@app.post("/budgets/", response_model=schemas.Budget)
async def create_budget(
    round_id: UUID = Form(...),
    project_id: UUID = Form(...),
    name: str = Form(...),
    notes: Optional[str] = Form(None),
    items: Optional[str] = Form(None), # JSON string
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    file_path = None
    parsed_items = json.loads(items) if items else []
    
    if file:
        file_path = f"uploads/{file.filename}"
        # Reset file cursor to beginning before saving
        await file.seek(0)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    
    budget_data = schemas.BudgetCreate(
        round_id=round_id,
        project_id=project_id,
        name=name,
        notes=notes,
        items=parsed_items,
        file_path=file_path
    )
    return crud.create_budget(db=db, budget=budget_data)

@app.get("/rounds/{round_id}/budgets/", response_model=List[schemas.Budget])
def read_budgets(round_id: UUID, db: Session = Depends(get_db)):
    budgets = crud.get_budgets_by_round(db, round_id=round_id)
    print(f"[API] Returning {len(budgets)} budgets for round_id={round_id}")
    root_count = sum(1 for b in budgets if not b.parent_budget_id)
    child_count = sum(1 for b in budgets if b.parent_budget_id)
    print(f"[API]   - Root budgets: {root_count}")
    print(f"[API]   - Child budgets: {child_count}")
    for b in budgets:
        if b.parent_budget_id:
            print(f"[API]   - Child budget: id={b.id}, name='{b.name}', parent_budget_id={b.parent_budget_id}, items={len(b.items) if b.items else 0}")

    # Doplň ceny u root rozpočtů ze součtů child budgetů, pokud má položky s cenou 0 (Type3 / Moravostav)
    for b in budgets:
        if b.parent_budget_id or not b.items:
            continue
        children = [c for c in budgets if c.parent_budget_id == b.id]
        if not children:
            continue
        # Obohatit jen když má smysl: aspoň jedna parent položka má cenu 0
        has_zero = any(not (item.get("price") and float(item.get("price", 0)) > 0) for item in b.items)
        if not has_zero:
            continue
        enriched_count = 0
        for item in b.items:
            old_price = item.get("price", 0)
            if old_price and float(old_price) > 0:
                continue
            code = str(item.get("number") or "").strip()
            name = (item.get("name") or "").strip()
            child = None
            if code:
                child = next((c for c in children if str((c.labels or {}).get("code") or "").strip() == code), None)
            if not child and name:
                child = next((c for c in children if (c.name or "").strip() == name), None)
            if child and child.items:
                total = round(sum(float(i.get("price") or 0) for i in child.items), 2)
                if total > 0:
                    item["price"] = total
                    enriched_count += 1
                    if enriched_count <= 3:  # Log first 3
                        print(f"[API]   Enriched item '{code}' ({name[:30]}): {old_price} -> {total}")
        if enriched_count > 0:
            print(f"[API] Root budget id={b.id} name='{b.name}': enriched {enriched_count}/{len(b.items)} parent items from {len(children)} children")
    return budgets

@app.delete("/budgets/{budget_id}")
def delete_budget(budget_id: UUID, db: Session = Depends(get_db)):
    db_budget = crud.delete_budget(db, budget_id=budget_id)
    if db_budget is None:
        raise HTTPException(status_code=404, detail="Budget not found")
    return {"message": "Budget deleted successfully"}

@app.put("/budgets/{budget_id}", response_model=schemas.Budget)
def update_budget(budget_id: UUID, budget_update: schemas.BudgetUpdate, db: Session = Depends(get_db)):
    db_budget = crud.update_budget(db, budget_id, budget_update)
    if not db_budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    return db_budget

@app.post("/budgets/{budget_id}/notes/", response_model=schemas.BudgetNote)
def create_budget_note(budget_id: UUID, note: schemas.BudgetNoteCreate, db: Session = Depends(get_db)):
    return crud.create_budget_note(db, budget_id, note)

@app.get("/budgets/{budget_id}/notes/", response_model=List[schemas.BudgetNote])
def read_budget_notes(budget_id: UUID, db: Session = Depends(get_db)):
    return crud.get_budget_notes(db, budget_id)

# Promote
@app.post("/promote/", response_model=schemas.Round)
def promote_round(promote_req: schemas.PromoteRequest, db: Session = Depends(get_db)):
    new_round = crud.promote_to_next_round(db, promote_req)
    if new_round is None:
        raise HTTPException(status_code=400, detail="Could not promote round")
    return new_round

# Chat
@app.post("/chat/", response_model=schemas.ChatHistory)
async def chat_with_project(chat_req: schemas.ChatRequest, db: Session = Depends(get_db)):
    if not model:
        raise HTTPException(status_code=503, detail="Gemini API not configured")

    # 1. Save User Message
    user_msg = schemas.ChatHistoryCreate(
        project_id=chat_req.project_id,
        session_id=chat_req.session_id,
        role="user",
        content=chat_req.message
    )
    crud.create_chat_history(db, user_msg)

    # 2. Build Context
    context_data = generate_project_context(db, chat_req.project_id)
    system_prompt = f"""Jsi zkušený analytik nákupu a rozpočtů.
    Zde jsou data pro aktuální projekt:
    {context_data}
    
    Odpověz na otázku uživatele na základě těchto dat.
    Odpovídej vždy v českém jazyce. Používej Markdown pro formátování (tučné písmo, odrážky, tabulky), aby byla odpověď přehledná.
    
    Otázka uživatele: {chat_req.message}
    """

    # 3. Call Gemini
    try:
        response = model.generate_content(system_prompt)
        # Check if response has text (it might be blocked)
        if hasattr(response, 'text'):
            ai_text = response.text
        else:
            ai_text = "I'm sorry, I couldn't generate a response (Safety/Filter)."
    except Exception as e:
        # Instead of failing the request, respond with the error so the user sees it
        ai_text = f"I encountered an error: {str(e)}"

    # 4. Save AI Message
    ai_msg = schemas.ChatHistoryCreate(
        project_id=chat_req.project_id,
        session_id=chat_req.session_id,
        role="model",
        content=ai_text
    )
    saved_ai_msg = crud.create_chat_history(db, ai_msg)
    
    # Auto-name session if it is new and unnamed (first user message)
    if chat_req.session_id:
        session = crud.get_chat_session(db, chat_req.session_id)
        if session and session.name == "New Chat":
            # Generate a short title based on the first user message
            try:
                # Ask Gemini to summarize into a title
                 # Using the same model instance
                title_prompt = f"Summarize this query into a very short 3-5 words title: {chat_req.message}"
                title_response = model.generate_content(title_prompt)
                if hasattr(title_response, 'text'):
                     crud.update_chat_session(db, chat_req.session_id, title_response.text.strip())
            except:
                pass # Fail silently, keep "New Chat"

    return saved_ai_msg

@app.get("/projects/{project_id}/chat/", response_model=List[schemas.ChatHistory])
def get_project_chat_history(project_id: UUID, session_id: Optional[UUID] = None, db: Session = Depends(get_db)):
    return crud.get_chat_history(db, project_id, session_id)

@app.post("/projects/{project_id}/sessions/", response_model=schemas.ChatSession)
def create_project_chat_session(project_id: UUID, db: Session = Depends(get_db)):
    return crud.create_chat_session(db, schemas.ChatSessionCreate(project_id=project_id, name="New Chat"))

@app.get("/projects/{project_id}/sessions/", response_model=List[schemas.ChatSession])
def get_project_chat_sessions(project_id: UUID, db: Session = Depends(get_db)):
    return crud.get_project_chat_sessions(db, project_id)

@app.delete("/sessions/{session_id}")
def delete_chat_session(session_id: UUID, db: Session = Depends(get_db)):
    return crud.delete_chat_session(db, session_id)

@app.delete("/projects/{project_id}/chat/")
def delete_project_chat_history(project_id: UUID, db: Session = Depends(get_db)):
    return crud.delete_chat_history(db, project_id)

# Duplicates
@app.post("/rounds/duplicates/", response_model=schemas.RoundDuplicate)
def create_duplicate(duplicate: schemas.RoundDuplicateCreate, db: Session = Depends(get_db)):
    return crud.create_duplicate(db=db, duplicate=duplicate)

@app.get("/rounds/{round_id}/duplicates/", response_model=List[schemas.RoundDuplicate])
def get_round_duplicates(round_id: UUID, db: Session = Depends(get_db)):
    return crud.get_duplicates_by_round(db, round_id=round_id)

@app.delete("/rounds/duplicates/{duplicate_id}")
def delete_duplicate(duplicate_id: UUID, db: Session = Depends(get_db)):
    return crud.delete_duplicate(db, duplicate_id=duplicate_id)

@app.post("/rounds/{round_id}/merge-items")
def merge_round_items(round_id: UUID, merge_req: schemas.MergeItemsRequest, db: Session = Depends(get_db)):
    return crud.merge_round_items(db, round_id, merge_req)

@app.post("/rounds/{round_id}/detect-duplicates", response_model=List[schemas.RoundDuplicate])
def detect_duplicates(round_id: UUID, db: Session = Depends(get_db)):
    # 1. Clear existing duplicates for this round
    existing_duplicates = crud.get_duplicates_by_round(db, round_id)
    for dup in existing_duplicates:
        crud.delete_duplicate(db, dup.id)

    # 2. Get budgets to compare
    budgets = crud.get_budgets_by_round(db, round_id)
    duplicates_found = []

    # Collect all unique item names
    all_items = set()
    print(f"Detecting duplicates for round {round_id}")
    for budget in budgets:
        items = budget.items or []
        print(f"Budget {budget.name} raw items type: {type(items)}")
        
        # Ensure items is list
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except:
                print(f"Failed to parse items string for budget {budget.name}")
                items = []
        
        # Handle dict wrapper (common if parsed from some sources)
        if isinstance(items, dict):
            if "list" in items and isinstance(items["list"], list):
                items = items["list"]
            else:
                items = [items]
        
        if not isinstance(items, list):
            items = []
            
        for item in items:
            if isinstance(item, dict):
                name = item.get("name")
                if name:
                     all_items.add(name.strip())

    unique_names = list(all_items)
    print(f"Found {len(unique_names)} unique items: {unique_names}")
    n = len(unique_names)

    # 3. Compare iteratively
    for i in range(n):
        for j in range(i + 1, n):
            name1 = unique_names[i]
            name2 = unique_names[j]

            match_type = None
            score = 0.0

            # Logic
            if name1 == name2:
                continue 
            
            if name1.lower() == name2.lower():
                match_type = "case_insensitive"
                score = 1.0
            else:
                # Fuzzy match
                ratio = difflib.SequenceMatcher(None, name1.lower(), name2.lower()).ratio()
                if ratio > 0.85:
                    match_type = "fuzzy"
                    score = ratio

            if match_type:
                print(f"Match found: {name1} vs {name2} ({match_type}, {score})")
                data = {
                    "item_a_name": name1,
                    "item_b_name": name2,
                    "match_type": match_type,
                    "similarity": round(score, 2)
                }
                
                dup_create = schemas.RoundDuplicateCreate(
                    round_id=round_id,
                    data=data
                )
                
                created_dup = crud.create_duplicate(db, dup_create)
                duplicates_found.append(created_dup)

    return duplicates_found

# PDF Export
@app.get("/rounds/{round_id}/export-pdf")
async def export_round_pdf(round_id: UUID, db: Session = Depends(get_db)):
    """Exportuje srovnání budgets do PDF s koláčovými grafy"""
    try:
        # Vytvořit dočasný soubor pro PDF
        output_dir = "uploads/exports"
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"export_{round_id}.pdf")
        
        # Vygenerovat PDF
        pdf_export.generate_pdf_export(round_id, db, output_path)
        
        # Vrátit soubor jako response
        return FileResponse(
            output_path,
            media_type="application/pdf",
            filename=f"rozpocty_export_{round_id}.pdf"
        )
    except Exception as e:
        print(f"PDF export error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {str(e)}")

