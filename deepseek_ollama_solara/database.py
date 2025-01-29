from sqlalchemy import create_engine, MetaData, Table, Column, UUID, String, DateTime
from databases import Database
from datetime import datetime
import uuid

DATABASE_URL = "sqlite:///./chats.db"

database = Database(DATABASE_URL)
metadata = MetaData()

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

chats = Table(
    "chats",
    metadata,
    Column("title", String),
    Column("id", UUID, primary_key=True, nullable=False, server_default="gen_random_uuid()"),
)

messages = Table(
    "messages",
    metadata,
    Column("id", UUID, primary_key=True, server_default="gen_random_uuid()"),
    Column("chat_id", UUID),
    Column("created", DateTime, server_default="now()"),
    Column("content", String),
    Column("chain_of_reason", String, nullable=True),
    Column("role", String),
)


async def connect_database():
    await database.connect()
    metadata.create_all(engine)


async def disconnect_database():
    await database.disconnect()


async def get_chats():
    query = chats.select()
    return await database.fetch_all(query)


async def create_chat(title: str, uuid: uuid.UUID):
    query = chats.insert().values(title=title, id=uuid).returning(*chats.c)
    return await database.fetch_one(query)


async def update_chat(id: uuid.UUID, title: str):
    query = chats.update().where(chats.c.id == id).values(title=title)
    return await database.execute(query)


async def get_messages(id: str):
    query = messages.select().where(messages.c.chat_id == id)
    chat_messages = await database.fetch_all(query)
    chat_messages.sort(key=lambda x: x["created"])
    return chat_messages


async def create_message(chat_id: uuid.UUID, role: str, created: datetime, content: str, chain_of_reason: str | None):
    query = messages.insert().values(chat_id=chat_id, id=uuid.uuid4(),role=role, created=created, content=content, chain_of_reason=chain_of_reason)
    return await database.execute(query)