from sqlalchemy import create_engine, MetaData, Table, Column, UUID, String, DateTime
from databases import Database
import uuid
from .types import Message

DATABASE_URL = "sqlite:///./chats.db"

database = Database(DATABASE_URL)
metadata = MetaData()

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

chats = Table(
    "chats",
    metadata,
    Column("title", String),
    Column("model", String),
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


async def create_chat(title: str, uuid: uuid.UUID, model: str):
    query = chats.insert().values(title=title, id=uuid, model=model).returning(*chats.c)
    return await database.fetch_one(query)


async def update_chat(id: uuid.UUID, title: str):
    query = chats.update().where(chats.c.id == id).values(title=title)
    return await database.execute(query)


async def get_messages(id: str):
    query = messages.select().where(messages.c.chat_id == id)
    chat_messages = await database.fetch_all(query)
    chat_messages.sort(key=lambda x: x["created"])
    return chat_messages


async def create_messages(chat_id: uuid.UUID, message_list: list[Message]):
    message_values = []
    for message in message_list:
        message_values.append({
            "chat_id": chat_id,
            "id": uuid.uuid4(),
            "role": message.role,
            "created": message.created,
            "content": message.content,
            "chain_of_reason": message.chain_of_reason,
        })
    query = messages.insert().values(message_values)
    return await database.execute(query)
