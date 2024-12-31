import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Determine the environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Configure the database URL
if ENVIRONMENT == "production":
    DATABASE_URL = os.getenv("DATABASE_URL")
else:
    DATABASE_URL = f"sqlite:///{os.getcwd()}/test_pickler.db"  # Local SQLite database

# Initialize SQLAlchemy engine and session
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

print(f"Using {DATABASE_URL} for {ENVIRONMENT} environment.")
