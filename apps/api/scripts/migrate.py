from __future__ import annotations

from app.database import engine

def main() -> None:
    print("Creating tables using SQLAlchemy...")
    from app.models import Base
    Base.metadata.create_all(engine)
    print("Database initialization complete.")

if __name__ == "__main__":
    main()
