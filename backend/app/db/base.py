from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base. Every ORM model in app/models/ inherits this."""
    pass
