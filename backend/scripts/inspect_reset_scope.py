from sqlalchemy import text

from app.config import get_settings
from app.db import SessionLocal
from seed.seed_data import RESET_TABLES


def main() -> None:
    settings = get_settings()
    if settings.database_backend != "postgresql":
        raise SystemExit("DATABASE_URL is not PostgreSQL/Supabase")
    with SessionLocal() as db:
        database, user = db.execute(text("select current_database(), current_user")).one()
        print(f"Database: {database}")
        print(f"Database user: {user}")
        print(f"Reset target tables: {len(RESET_TABLES)}")
        for table_name in RESET_TABLES:
            count = db.scalar(text(f"select count(*) from public.{table_name}"))
            print(f"  {table_name}: {count}")


if __name__ == "__main__":
    main()
