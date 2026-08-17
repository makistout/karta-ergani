"""Apply the additive assistant channel unification migration."""
from pathlib import Path
from app.db import cursor

SQL_PATH = Path(__file__).resolve().parents[1] / "sql" / "alter_unify_assistant_channels.sql"

def main() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
    with cursor() as cur:
        for statement in (part.strip() for part in sql.split("\nGO\n")):
            if statement:
                cur.execute(statement)
    print("OK: unified assistant channels migration")

if __name__ == "__main__":
    main()
