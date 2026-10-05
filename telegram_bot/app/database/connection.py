from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def create_database(url: str):
    options = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, pool_pre_ping=True, connect_args=options)


def create_session_factory(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=create_database(database_url), expire_on_commit=False)
