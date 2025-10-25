"""
Database connection management for Stockshot Browser.
"""

import logging
import os
import shutil
import time
import random
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator, Optional
from queue import Queue, Empty

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import OperationalError, DatabaseError, IntegrityError, InterfaceError

from .models import Base, create_additional_indexes
from .migrations import apply_migrations


logger = logging.getLogger(__name__)


def database_retry(max_retries: int = 5, base_delay: float = 0.1, max_delay: float = 2.0):
    """Decorator for database operations with exponential backoff retry logic."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None
            func_name = f"{func.__module__}.{func.__qualname__}"
            
            # Log function entry with argument details for better debugging
            args_info = f"args=({len(args)} items)" if args else "no args"
            kwargs_info = f"kwargs={list(kwargs.keys())}" if kwargs else "no kwargs"
            
            for attempt in range(max_retries):
                try:
                    result = func(*args, **kwargs)
                    if attempt > 0:
                        logger.info(f"✅ DB_RETRY: {func_name} succeeded after {attempt + 1} attempts")
                    else:
                        logger.debug(f"✅ DB_RETRY: {func_name} succeeded on first attempt")
                    return result
                    
                except (OperationalError, DatabaseError, IntegrityError, InterfaceError) as e:
                    last_exception = e
                    error_msg = str(e).lower()
                    full_error = str(e)
                    error_type = type(e).__name__
                    
                    # Enhanced error logging with SQL details
                    if hasattr(e, 'statement') and e.statement:
                        if hasattr(e, 'params') and e.params:
                            logger.error(f"❌ DB_RETRY: Params: {e.params}")
                    else:
                        logger.error(f"❌ DB_RETRY: {func_name} failed with {error_type}: {full_error}")
                    
                    # Check if this is a retryable error
                    retryable_errors = [
                        'cannot commit transaction - sql statements in progress',
                        'cursor needed to be reset',
                        'cursor needed to be reset because of commit/rollback',
                        'cannot start a transaction within a transaction',
                        'database is locked',
                        'database table is locked',
                        'not an error',  # SQLite internal concurrency errors
                        'cannot rollback - no transaction is active',
                        'single-row insert statement',  # Primary key generation issues
                        'did not produce a new primary key result',
                        'error binding parameter',  # Parameter binding type issues
                        'probably unsupported type',
                        'sqlite3.operationalerror',
                        'sqlite3.integrityerror',
                        'sqlite3.interfaceerror',
                        'interfaceerror',
                        'foreign key constraint failed'  # Add FK constraint errors
                    ]
                    
                    # Find which specific pattern matched
                    matched_pattern = None
                    for pattern in retryable_errors:
                        if pattern in error_msg:
                            matched_pattern = pattern
                            break
                    
                    is_retryable = matched_pattern is not None
                    
                    if not is_retryable:
                        raise
                    
                    if attempt == max_retries - 1:
                        raise
                    
                    # Calculate delay with exponential backoff and jitter
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    jitter = random.uniform(0, delay * 0.1)  # Add 10% jitter
                    total_delay = delay + jitter
                    
                    time.sleep(total_delay)
                
                except Exception as e:
                    # Non-database errors should not be retried
                    raise
            
            # This should never be reached due to the final attempt re-raise above
            raise last_exception
        
        return wrapper
    return decorator


class DatabaseManager:
    """Manages database connections and operations with session pooling."""
    
    def __init__(self, database_path: str, max_concurrent_sessions: int = 1):
        self.database_path = Path(database_path)
        self.engine: Optional[Engine] = None
        self.SessionLocal: Optional[sessionmaker] = None
        self._backup_enabled = False
        self._backup_interval_hours = 24
        self._max_backups = 7
        
        # Session pool management - conservative serialized access by default
        self.max_concurrent_sessions = max_concurrent_sessions
        self._session_semaphore = threading.Semaphore(max_concurrent_sessions)
        self._session_wait_timeout = 5.0  # seconds - reduced timeout for faster failure
        
        # Separate semaphore for tag operations that need concurrent access
        self._tag_session_semaphore = threading.Semaphore(8)  # Allow concurrent tag reads
        
    
    def initialize_database(self) -> None:
        """Initialize database connection and create tables."""
        
        # Ensure database directory exists
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create SQLite engine with optimizations
        database_url = f"sqlite:///{self.database_path}"
        
        self.engine = create_engine(
            database_url,
            poolclass=StaticPool,
            connect_args={
                "check_same_thread": False,  # Allow multi-threading
                "timeout": 30,  # Connection timeout
            },
            echo=False,  # Set to True for SQL debugging
        )
        
        # Configure SQLite for better performance
        self._configure_sqlite()
        
        # Create session factory
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
        
        # Create all tables
        Base.metadata.create_all(bind=self.engine)
        
        # Test database connection
        if not self.test_connection():
            raise Exception("Database connection test failed")
        
        # Apply database migrations
        try:
            apply_migrations(self.engine)
        except Exception as e:
            raise
        
        # Create additional indexes
        try:
            create_additional_indexes(self.engine)
        except Exception as e:
            logger.warning(f"Could not create additional indexes: {e}")
        
    
    def _configure_sqlite(self) -> None:
        """Configure SQLite for optimal performance."""
        @event.listens_for(Engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            """Set SQLite pragmas for better performance."""
            cursor = dbapi_connection.cursor()
            
            # Performance optimizations
            cursor.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
            cursor.execute("PRAGMA synchronous=NORMAL")  # Faster writes
            cursor.execute("PRAGMA cache_size=10000")  # Larger cache
            cursor.execute("PRAGMA temp_store=MEMORY")  # Use memory for temp tables
            cursor.execute("PRAGMA mmap_size=268435456")  # 256MB memory mapping
            
            # Foreign key constraints
            cursor.execute("PRAGMA foreign_keys=ON")
            
            # Auto vacuum
            cursor.execute("PRAGMA auto_vacuum=INCREMENTAL")
            
            cursor.close()
    
    @contextmanager
    def get_session(self, for_tags: bool = False) -> Generator[Session, None, None]:
        """Get database session with connection pooling to limit concurrent access.
        
        Args:
            for_tags: If True, uses the tag session pool which allows higher concurrency
        """
        if not self.SessionLocal:
            raise RuntimeError("Database not initialized. Call initialize_database() first.")
        
        # Use appropriate semaphore based on operation type
        if for_tags:
            semaphore = self._tag_session_semaphore
            max_sessions = 8
            session_type = "tag"
        else:
            semaphore = self._session_semaphore
            max_sessions = self.max_concurrent_sessions
            session_type = "regular"
        
        # Acquire session slot from appropriate pool
        acquired = semaphore.acquire(timeout=self._session_wait_timeout)
        if not acquired:
            raise RuntimeError(f"Failed to acquire {session_type} database session within {self._session_wait_timeout}s timeout. "
                             f"Maximum {max_sessions} concurrent {session_type} sessions exceeded.")
        
        session = None
        session_id = None
        
        try:
            session = self.SessionLocal()
            session_id = id(session)
            if for_tags:
                active_count = 8 - self._tag_session_semaphore._value
            else:
                active_count = self.max_concurrent_sessions - self._session_semaphore._value
            
            # Session-level retry for creation/operational issues
            max_session_retries = 2  # Reduced since we have connection pooling
            last_exception = None
            
            for attempt in range(max_session_retries):
                try:
                    yield session
                    
                    # Apply retry logic to session commit
                    self._commit_with_retry(session, session_id)
                    return  # Success, exit retry loop
                    
                except Exception as e:
                    last_exception = e
                    error_type = type(e).__name__
                    error_msg = str(e).lower()
                    
                    # Check if this is a retryable session-level error
                    session_retryable_patterns = [
                        'cursor needed to be reset because of commit/rollback',
                        'cannot start a transaction within a transaction',
                        'error binding parameter',
                        'probably unsupported type',
                        'cursor needed to be reset',
                        'interfaceerror'
                    ]
                    
                    is_session_retryable = any(pattern in error_msg for pattern in session_retryable_patterns)
                    
                    if is_session_retryable and attempt < max_session_retries - 1:
                        delay = 0.05 * (2 ** attempt)  # Shorter delay with connection pooling
                        time.sleep(delay)
                        
                        # Rollback and continue with same session for retry
                        try:
                            session.rollback()
                        except:
                            pass
                    else:
                        break
            
            # If we got here, re-raise the last exception
            if last_exception:
                raise last_exception
                
        except Exception as e:
            
            # Rollback on any error
            if session:
                try:
                    session.rollback()
                except Exception as rollback_error:
                    logger.error(f"❌ SESSION: Failed to rollback session {session_id}: {rollback_error}")
            raise
            
        finally:
            # Always clean up session and release pool slot
            if session:
                try:
                    session.close()
                except Exception as close_error:
                    logger.error(f"❌ SESSION: Failed to close session {session_id}: {close_error}")
            
            # Release session slot back to appropriate pool
            if for_tags:
                self._tag_session_semaphore.release()
                remaining_slots = 8 - self._tag_session_semaphore._value
            else:
                self._session_semaphore.release()
                remaining_slots = self.max_concurrent_sessions - self._session_semaphore._value
    
    def _commit_with_retry(self, session: Session, session_id: int, max_retries: int = 5, base_delay: float = 0.1):
        """Commit session with retry logic for concurrency conflicts."""
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                session.commit()
                if attempt > 0:
                    logger.info(f"✅ SESSION: Session {session_id} commit succeeded after {attempt + 1} attempts")
                return
                
            except Exception as e:
                last_exception = e
                error_msg = str(e).lower()
                error_type = type(e).__name__
                
                
                # Check if this is a retryable error
                retryable_patterns = [
                    'cannot commit transaction - sql statements in progress',
                    'cursor needed to be reset because of commit/rollback',
                    'cannot start a transaction within a transaction',
                    'database is locked',
                    'database table is locked',
                    'not an error',
                    'cannot rollback - no transaction is active',
                    'single-row insert statement',
                    'did not produce a new primary key result',
                    'error binding parameter',
                    'probably unsupported type',
                    'sqlite3.operationalerror',
                    'sqlite3.integrityerror',
                    'sqlite3.interfaceerror',
                    'interfaceerror',
                    'can\'t reconnect until invalid transaction is rolled back',  # PendingRollbackError
                    'pendingerror',
                    'pendingrollbackerror'
                ]
                
                # Find which specific pattern matched
                matched_pattern = None
                for pattern in retryable_patterns:
                    if pattern in error_msg:
                        matched_pattern = pattern
                        break
                
                is_retryable = matched_pattern is not None
                
                if not is_retryable:
                    raise
                
                if attempt == max_retries - 1:
                    raise
                
                # Rollback session before retry to clear corrupted state
                try:
                    session.rollback()
                except Exception as rollback_error:
                    # Continue with retry even if rollback fails
                    raise
                
                # Calculate delay with exponential backoff and jitter
                delay = min(base_delay * (2 ** attempt), 2.0)
                jitter = random.uniform(0, delay * 0.1)
                total_delay = delay + jitter
                
                time.sleep(total_delay)
        
        # This should never be reached due to the final attempt re-raise above
        raise last_exception
    
    def setup_auto_backup(self, interval_hours: int = 24, max_backups: int = 7) -> None:
        """Setup automatic database backups."""
        self._backup_enabled = True
        self._backup_interval_hours = interval_hours
        self._max_backups = max_backups
                
        # Perform initial backup if needed
        self._check_and_backup()
    
    def _check_and_backup(self) -> None:
        """Check if backup is needed and perform it."""
        if not self._backup_enabled or not self.database_path.exists():
            return
        
        backup_dir = self.database_path.parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        
        # Check if backup is needed
        latest_backup = self._get_latest_backup(backup_dir)
        
        if latest_backup:
            backup_age = datetime.now() - datetime.fromtimestamp(latest_backup.stat().st_mtime)
            if backup_age < timedelta(hours=self._backup_interval_hours):
                return  # Backup is recent enough
        
        # Perform backup
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"stockshot_browser_{timestamp}.db"
            
            shutil.copy2(self.database_path, backup_path)
            
            # Clean up old backups
            self._cleanup_old_backups(backup_dir)
            
        except Exception as e:
            logger.error(f"Failed to create database backup: {e}")
    
    def _get_latest_backup(self, backup_dir: Path) -> Optional[Path]:
        """Get the most recent backup file."""
        if not backup_dir.exists():
            return None
        
        backup_files = list(backup_dir.glob("stockshot_browser_*.db"))
        if not backup_files:
            return None
        
        return max(backup_files, key=lambda p: p.stat().st_mtime)
    
    def _cleanup_old_backups(self, backup_dir: Path) -> None:
        """Remove old backup files beyond the maximum count."""
        backup_files = sorted(
            backup_dir.glob("stockshot_browser_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        # Remove excess backups
        for backup_file in backup_files[self._max_backups:]:
            try:
                backup_file.unlink()
            except Exception as e:
                logger.warning(f"Failed to remove old backup {backup_file}: {e}")
    
    def create_backup(self, backup_path: Optional[str] = None) -> Path:
        """Create a manual database backup."""
        if not self.database_path.exists():
            raise FileNotFoundError("Database file does not exist")
        
        if backup_path:
            backup_file = Path(backup_path)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = self.database_path.parent / f"stockshot_browser_backup_{timestamp}.db"
        
        backup_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.database_path, backup_file)
        
        return backup_file
    
    def restore_backup(self, backup_path: str) -> None:
        """Restore database from backup."""
        backup_file = Path(backup_path)
        
        if not backup_file.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")
        
        # Close current connections
        if self.engine:
            self.engine.dispose()
        
        # Create backup of current database
        if self.database_path.exists():
            current_backup = self.database_path.with_suffix('.db.pre_restore')
            shutil.copy2(self.database_path, current_backup)
        
        # Restore from backup
        shutil.copy2(backup_file, self.database_path)
        
        # Reinitialize database connection
        self.initialize_database()
    
    def vacuum_database(self) -> None:
        """Vacuum database to reclaim space and optimize."""
        if not self.engine:
            raise RuntimeError("Database not initialized")
        
        
        with self.engine.connect() as conn:
            # Close all sessions first
            if self.SessionLocal:
                self.SessionLocal.close_all()
            
            # Perform vacuum
            conn.execute(text("VACUUM"))
            conn.execute(text("PRAGMA optimize"))
            
    
    def get_database_info(self) -> dict:
        """Get database information and statistics."""
        if not self.engine:
            return {"status": "not_initialized"}
        
        info = {
            "status": "initialized",
            "path": str(self.database_path),
            "exists": self.database_path.exists(),
        }
        
        if self.database_path.exists():
            stat = self.database_path.stat()
            info.update({
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
            
            # Get table counts
            try:
                with self.get_session() as session:
                    from .models import Project, Entity, Metadata, Tag, Favorite, Thumbnail
                    
                    info["table_counts"] = {
                        "projects": session.query(Project).count(),
                        "entities": session.query(Entity).count(),
                        "metadata": session.query(Metadata).count(),
                        "tags": session.query(Tag).count(),
                        "favorites": session.query(Favorite).count(),
                        "thumbnails": session.query(Thumbnail).count(),
                    }
            except Exception as e:
                logger.warning(f"Could not get table counts: {e}")
                info["table_counts"] = "error"
        
        return info
    
    def close(self) -> None:
        """Close database connections."""
        if self.SessionLocal:
            self.SessionLocal.close_all()
        
        if self.engine:
            self.engine.dispose()
            
    
    def test_connection(self) -> bool:
        """Test database connection."""
        try:
            with self.get_session() as session:
                session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            return False


# Global session factory for convenience
_session_factory: Optional[sessionmaker] = None


def set_session_factory(session_factory: sessionmaker) -> None:
    """Set global session factory."""
    global _session_factory
    _session_factory = session_factory


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Get database session using global session factory."""
    if not _session_factory:
        raise RuntimeError("Session factory not set. Initialize DatabaseManager first.")
    
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


def init_database(database_path: str, max_concurrent_sessions: int = 1) -> DatabaseManager:
    """Initialize database and set global session factory with conservative serialized access."""
    db_manager = DatabaseManager(database_path, max_concurrent_sessions)
    db_manager.initialize_database()
    
    # Set global session factory
    set_session_factory(db_manager.SessionLocal)
    
    return db_manager