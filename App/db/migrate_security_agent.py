from App.db.connection import engine
from App.db.models.security_agent_query import SecurityAgentQuery

def main() -> None:
    SecurityAgentQuery.__table__.create(bind=engine, checkfirst=True)
    print("Security Agent query audit table is ready.")

if __name__ == "__main__":
    main()
