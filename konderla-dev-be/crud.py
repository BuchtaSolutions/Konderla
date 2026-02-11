from sqlalchemy.orm import Session
from typing import Optional, List
import models, schemas
import copy
import json
from uuid import UUID

# Project
def create_project(db: Session, project: schemas.ProjectCreate):
    db_project = models.Project(**project.dict())
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project

def get_project(db: Session, project_id: UUID):
    return db.query(models.Project).filter(models.Project.id == project_id).first()

def get_projects(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Project).offset(skip).limit(limit).all()

def update_project(db: Session, project_id: UUID, project_update: schemas.ProjectUpdate):
    db_project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not db_project:
        return None
    
    update_data = project_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_project, key, value)
    
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project

def delete_project(db: Session, project_id: UUID):
    db_project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if db_project:
        db.delete(db_project)
        db.commit()
    return db_project

# Round
def create_round(db: Session, round: schemas.RoundCreate):
    db_round = models.Round(**round.dict())
    db.add(db_round)
    db.commit()
    db.refresh(db_round)
    return db_round

def get_rounds_by_project(db: Session, project_id: UUID):
    return db.query(models.Round).filter(models.Round.project_id == project_id).order_by(models.Round.order).all()

def delete_round(db: Session, round_id: UUID):
    db_round = db.query(models.Round).filter(models.Round.id == round_id).first()
    if db_round:
        db.delete(db_round)
        db.commit()
    return db_round

# Budget
def create_budget(db: Session, budget: schemas.BudgetCreate):
    db_budget = models.Budget(**budget.dict())
    db.add(db_budget)
    db.commit()
    db.refresh(db_budget)
    return db_budget

def get_budgets_by_round(db: Session, round_id: UUID):
    budgets = db.query(models.Budget).filter(models.Budget.round_id == round_id).all()
    # NEPŘEPISOVAT název child budgetu - každý child budget má svůj vlastní název
    # Původní kód přepisoval název child budgetu názvem parent budgetu, což bylo špatně
    return budgets

def delete_budget(db: Session, budget_id: UUID):
    db_budget = db.query(models.Budget).filter(models.Budget.id == budget_id).first()
    if db_budget:
        db.delete(db_budget)
        db.commit()
    return db_budget

def update_budget(db: Session, budget_id: UUID, budget_update: schemas.BudgetUpdate):
    db_budget = db.query(models.Budget).filter(models.Budget.id == budget_id).first()
    if not db_budget:
        return None
    
    update_data = budget_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_budget, key, value)
    
    db.add(db_budget)
    db.commit()
    db.refresh(db_budget)
    return db_budget

def create_budget_note(db: Session, budget_id: UUID, note: schemas.BudgetNoteCreate):
    db_note = models.BudgetNote(budget_id=budget_id, content=note.content)
    db.add(db_note)
    db.commit()
    db.refresh(db_note)
    return db_note

def get_budget_notes(db: Session, budget_id: UUID):
    return db.query(models.BudgetNote).filter(models.BudgetNote.budget_id == budget_id).order_by(models.BudgetNote.created_at.desc()).all()

# Promote Logic
def promote_to_next_round(db: Session, promote_req: schemas.PromoteRequest):
    # 1. Get current round to determine order
    current_round = db.query(models.Round).filter(models.Round.id == promote_req.current_round_id).first()
    if not current_round:
        return None
    
    new_order = current_round.order + 1
    
    # 2. Create new Round
    new_round = models.Round(
        project_id=promote_req.project_id,
        name=promote_req.new_round_name,
        order=new_order,
        status="open"
    )
    db.add(new_round)
    db.commit()
    db.refresh(new_round)
    
    # 3. Deep copy budgets
    promoted_budgets = []
    for budget_id in promote_req.budget_ids:
        original_budget = db.query(models.Budget).filter(models.Budget.id == budget_id).first()
        if original_budget:
            new_budget = models.Budget(
                round_id=new_round.id,
                project_id=new_round.project_id,
                parent_budget_id=original_budget.id,
                name=original_budget.name,
                notes=original_budget.notes,
                score=original_budget.score,
                labels=copy.deepcopy(original_budget.labels),
                items=copy.deepcopy(original_budget.items),
                dynamic_fields=copy.deepcopy(original_budget.dynamic_fields)
            )
            db.add(new_budget)
            promoted_budgets.append(new_budget)
            
    db.commit()
    return new_round

# Chat History
def create_chat_history(db: Session, chat: schemas.ChatHistoryCreate):
    db_chat = models.ChatHistory(**chat.dict())
    db.add(db_chat)
    db.commit()
    db.refresh(db_chat)
    return db_chat

def create_chat_session(db: Session, session: schemas.ChatSessionCreate):
    db_session = models.ChatSession(**session.dict())
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session

def get_project_chat_sessions(db: Session, project_id: UUID):
    return db.query(models.ChatSession).filter(models.ChatSession.project_id == project_id).order_by(models.ChatSession.created_at.desc()).all()

def get_chat_session(db: Session, session_id: UUID):
    return db.query(models.ChatSession).filter(models.ChatSession.id == session_id).first()

def delete_chat_session(db: Session, session_id: UUID):
    db.query(models.ChatSession).filter(models.ChatSession.id == session_id).delete()
    db.commit()
    return {"status": "success"}

def update_chat_session(db: Session, session_id: UUID, name: str):
    db_session = db.query(models.ChatSession).filter(models.ChatSession.id == session_id).first()
    if db_session:
        db_session.name = name
        db.commit()
        db.refresh(db_session)
    return db_session

def get_chat_history(db: Session, project_id: UUID, session_id: Optional[UUID] = None):
    query = db.query(models.ChatHistory).filter(models.ChatHistory.project_id == project_id)
    if session_id:
        query = query.filter(models.ChatHistory.session_id == session_id)
    return query.order_by(models.ChatHistory.timestamp).all()

def delete_chat_history(db: Session, project_id: UUID):
    db.query(models.ChatHistory).filter(models.ChatHistory.project_id == project_id).delete()
    db.commit()
    return {"status": "success"}

# Merge Items Logic
def merge_round_items(db: Session, round_id: UUID, merge_req: schemas.MergeItemsRequest):
    budgets = get_budgets_by_round(db, round_id)
    
    for budget in budgets:
        raw_items = budget.items or []
        
        # 1. Handle if raw_items is a string (double-serialized JSON)
        if isinstance(raw_items, str):
            try:
                raw_items = json.loads(raw_items)
            except Exception as e:
                print(f"Error parsing raw_items for budget {budget.id}: {e}")
                # If parsing fails/not empty, skip to prevent dataloss
                if raw_items:
                     print(f"Aborting merge for budget {budget.id} - raw_items is corrupted string")
                     continue

        # 2. Ensure it is a list
        if not isinstance(raw_items, list):
            # If it's a dict, wrap it
            if isinstance(raw_items, dict):
                raw_items = [raw_items]
            else:
                # If it is something else (like unparseable string) and has content, DO NOT wipe
                if raw_items:
                     print(f"Aborting merge for budget {budget.id} - raw_items is {type(raw_items)}")
                     continue
                raw_items = []
            
        # 3. Robustly parse items into list of dicts
        items = []
        for i in raw_items:
            if isinstance(i, dict):
                items.append(i)
            elif isinstance(i, str):
                try:
                    parsed = json.loads(i)
                    if isinstance(parsed, dict):
                        items.append(parsed)
                except:
                    pass

        # 4. Perform Merge
        source_name = merge_req.source_name
        target_name = merge_req.target_name
        new_name = merge_req.new_name

        # Find all source items to merge (handle duplicates)
        source_items = [i for i in items if i.get('name') == source_name]
        
        if source_items:
            total_source_price = sum((float(i.get('price') or 0) for i in source_items), 0.0)
            
            # Remove source items from the list
            items = [i for i in items if i.get('name') != source_name]
            
            # Find target item in the REMAINING list
            target_item = next((i for i in items if i.get('name') == target_name), None)
            
            if target_item:
                # Merge into existing target
                current_target_price = float(target_item.get('price') or 0)
                target_item['price'] = current_target_price + total_source_price
                
                # Rename if needed
                if new_name and new_name != target_name:
                    target_item['name'] = new_name
            else:
                # Target not found (or was same as source and removed)
                # We reuse the FIRST source item as the base for the new item
                # to preserve other fields (unit, etc)
                base_item = source_items[0].copy()
                base_item['price'] = total_source_price # Sum of all sources
                base_item['name'] = new_name if new_name else target_name
                items.append(base_item)
                
        elif target_name:
             # If source not found, but we want to rename target (if exists)
             target_item = next((i for i in items if i.get('name') == target_name), None)
             if target_item and new_name and new_name != target_name:
                 target_item['name'] = new_name

        # Update budget items
        budget.items = items
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(budget, "items")

    db.commit()
    return {"status": "success"}

# Duplicates
def create_duplicate(db: Session, duplicate: schemas.RoundDuplicateCreate):
    db_duplicate = models.RoundDuplicate(**duplicate.dict())
    db.add(db_duplicate)
    db.commit()
    db.refresh(db_duplicate)
    return db_duplicate

def get_duplicates_by_round(db: Session, round_id: UUID):
    return db.query(models.RoundDuplicate).filter(models.RoundDuplicate.round_id == round_id).all()

def delete_duplicate(db: Session, duplicate_id: int):
    db_duplicate = db.query(models.RoundDuplicate).filter(models.RoundDuplicate.id == duplicate_id).first()
    if db_duplicate:
        db.delete(db_duplicate)
        db.commit()
    return db_duplicate
