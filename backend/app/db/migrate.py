from sqlalchemy import Engine, MetaData, inspect, text


def add_missing_columns(engine: Engine, metadata: MetaData) -> None:
    """Add columns that exist on the models but not yet in the database.

    Stopgap until Alembic migrations are set up: Base.metadata.create_all()
    creates missing *tables* but never alters existing ones. Only additive,
    safe changes are made -- a new NOT NULL column must have a server default.
    """
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table in metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                definition = f'{column.name} {column.type.compile(dialect=engine.dialect)}'
                if column.server_default is not None:
                    default = column.server_default.arg.compile(dialect=engine.dialect)
                    definition += f" DEFAULT {default}"
                if not column.nullable:
                    if column.server_default is None:
                        raise RuntimeError(f"Cannot add NOT NULL column {table.name}.{column.name} without a default")
                    definition += " NOT NULL"
                connection.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {definition}"))
