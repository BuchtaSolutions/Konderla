from database import SessionLocal
import models
import json

db = SessionLocal()

print("--- PROJECTS ---")
projects = db.query(models.Project).all()
for p in projects:
    print(f"Project ID: {p.id}, Name: {p.name}")
    for r in p.rounds:
        print(f"  Round ID: {r.id}, Name: {r.name}, Status: {r.status}")
        for b in r.budgets:
            print(f"    Budget ID: {b.id}, Name: {b.name}")
            print(f"    Raw Items Type: {type(b.items)}")
            print(f"    Raw Items Content: {b.items}")
