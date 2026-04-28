"""MongoDB Atlas connection — single shared client per process."""

import os
from functools import lru_cache

import pymongo
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

load_dotenv()

DB_NAME = "stock_intelligence"


@lru_cache(maxsize=1)
def _client() -> MongoClient:
    uri = os.environ["MONGO_URI"]
    client = MongoClient(
        uri,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
    )
    # Validate connectivity at startup rather than at first query.
    client.admin.command("ping")
    return client


def get_db() -> Database:
    return _client()[DB_NAME]


def get_collection(name: str):
    return get_db()[name]
