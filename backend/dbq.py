import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PID = os.getenv("PID", "")


def main():
    from app.db.database import SessionLocal
    from app.services.ai import AIService
    from app.services.creative_project.service import (
        CreativeProjectService,
        loads_json,
    )

    AIService.initialize(str(Path("config") / "providers.yaml"), session=None)

    # 与线上服务一致：使用同步 session
    session = SessionLocal()
    try:
        svc = CreativeProjectService(session)
        project = svc.get_project(PID)
        if not project:
            print("project not found")
            return
        outline = loads_json(project.outline_json)
        profiles = svc._project_character_production_profiles(PID, outline)
        print("profiles count =", len(profiles))
        for p in profiles:
            print("   -", p.get("name"), "| role=", p.get("usage_role"),
                  "| appearance=", str(p.get("appearance"))[:28])
        cards = svc._character_cards_text(PID, outline)
        print("")
        print("cards length =", len(cards))
        print("---- cards ----")
        print(cards[:900])
    finally:
        session.close()


main()
