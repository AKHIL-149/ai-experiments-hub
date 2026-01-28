"""Database models and persistence - Phase 5"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Text, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import logging

logger = logging.getLogger(__name__)

Base = declarative_base()


class Job(Base):
    """Job model for persisting analysis jobs"""
    __tablename__ = 'jobs'

    id = Column(String, primary_key=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    status = Column(String, nullable=False, default='queued')  # queued, processing, completed, failed, cancelled

    # Options
    summary_level = Column(String, default='standard')
    extract_actions = Column(Boolean, default=True)
    extract_topics = Column(Boolean, default=True)
    output_format = Column(String, default='markdown')
    language = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Progress
    progress_percent = Column(Integer, default=0)
    current_stage = Column(String, nullable=True)

    # Results
    output_file_path = Column(String, nullable=True)
    summary_text = Column(Text, nullable=True)
    topics = Column(JSON, nullable=True)
    action_items_count = Column(Integer, default=0)

    # Statistics
    processing_time_seconds = Column(Float, nullable=True)
    estimated_cost_usd = Column(Float, nullable=True)
    cache_hits = Column(Integer, default=0)

    # Error
    error_message = Column(Text, nullable=True)

    # Metadata
    metadata_json = Column(JSON, nullable=True)

    def to_dict(self) -> Dict:
        """Convert job to dictionary"""
        return {
            'job_id': self.id,
            'filename': self.filename,
            'status': self.status,
            'summary_level': self.summary_level,
            'extract_actions': self.extract_actions,
            'extract_topics': self.extract_topics,
            'output_format': self.output_format,
            'language': self.language,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'progress_percent': self.progress_percent,
            'current_stage': self.current_stage,
            'output_file_path': self.output_file_path,
            'summary_text': self.summary_text,
            'topics': self.topics,
            'action_items_count': self.action_items_count,
            'processing_time_seconds': self.processing_time_seconds,
            'estimated_cost_usd': self.estimated_cost_usd,
            'cache_hits': self.cache_hits,
            'error_message': self.error_message,
            'metadata': self.metadata_json
        }


class DatabaseManager:
    """Manage database connections and operations"""

    def __init__(self, db_url: Optional[str] = None):
        """
        Initialize database manager

        Args:
            db_url: SQLAlchemy database URL (default: SQLite in data/database.db)
        """
        if db_url is None:
            db_dir = Path('./data')
            db_dir.mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{db_dir}/database.db"

        self.engine = create_engine(db_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Create tables
        Base.metadata.create_all(self.engine)
        logger.info(f"Database initialized: {db_url}")

    def get_session(self) -> Session:
        """Get a new database session"""
        return self.SessionLocal()

    def create_job(
        self,
        job_id: str,
        filename: str,
        file_path: str,
        summary_level: str = 'standard',
        extract_actions: bool = True,
        extract_topics: bool = True,
        output_format: str = 'markdown',
        language: Optional[str] = None
    ) -> Job:
        """Create a new job"""
        session = self.get_session()
        try:
            job = Job(
                id=job_id,
                filename=filename,
                file_path=file_path,
                summary_level=summary_level,
                extract_actions=extract_actions,
                extract_topics=extract_topics,
                output_format=output_format,
                language=language,
                status='queued',
                created_at=datetime.utcnow()
            )
            session.add(job)
            session.commit()
            session.refresh(job)
            logger.info(f"Created job {job_id}")
            return job
        finally:
            session.close()

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID"""
        session = self.get_session()
        try:
            return session.query(Job).filter(Job.id == job_id).first()
        finally:
            session.close()

    def update_job(self, job_id: str, **kwargs) -> Optional[Job]:
        """Update job fields"""
        session = self.get_session()
        try:
            job = session.query(Job).filter(Job.id == job_id).first()
            if job:
                for key, value in kwargs.items():
                    if hasattr(job, key):
                        setattr(job, key, value)
                session.commit()
                session.refresh(job)
                return job
            return None
        finally:
            session.close()

    def update_job_progress(
        self,
        job_id: str,
        progress_percent: int,
        current_stage: Optional[str] = None
    ) -> Optional[Job]:
        """Update job progress"""
        updates = {'progress_percent': progress_percent}
        if current_stage:
            updates['current_stage'] = current_stage
        return self.update_job(job_id, **updates)

    def mark_job_processing(self, job_id: str) -> Optional[Job]:
        """Mark job as processing"""
        return self.update_job(
            job_id,
            status='processing',
            started_at=datetime.utcnow()
        )

    def mark_job_completed(
        self,
        job_id: str,
        output_file_path: str,
        summary_text: Optional[str] = None,
        topics: Optional[List[str]] = None,
        action_items_count: int = 0,
        processing_time_seconds: Optional[float] = None,
        estimated_cost_usd: Optional[float] = None,
        cache_hits: int = 0
    ) -> Optional[Job]:
        """Mark job as completed with results"""
        return self.update_job(
            job_id,
            status='completed',
            completed_at=datetime.utcnow(),
            progress_percent=100,
            current_stage='completed',
            output_file_path=output_file_path,
            summary_text=summary_text,
            topics=topics,
            action_items_count=action_items_count,
            processing_time_seconds=processing_time_seconds,
            estimated_cost_usd=estimated_cost_usd,
            cache_hits=cache_hits
        )

    def mark_job_failed(self, job_id: str, error_message: str) -> Optional[Job]:
        """Mark job as failed"""
        return self.update_job(
            job_id,
            status='failed',
            completed_at=datetime.utcnow(),
            error_message=error_message,
            current_stage='failed'
        )

    def list_jobs(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None
    ) -> List[Job]:
        """List jobs with pagination"""
        session = self.get_session()
        try:
            query = session.query(Job).order_by(Job.created_at.desc())

            if status:
                query = query.filter(Job.status == status)

            return query.offset(offset).limit(limit).all()
        finally:
            session.close()

    def delete_job(self, job_id: str) -> bool:
        """Delete job from database"""
        session = self.get_session()
        try:
            job = session.query(Job).filter(Job.id == job_id).first()
            if job:
                # Delete associated files
                if job.file_path and Path(job.file_path).exists():
                    try:
                        Path(job.file_path).unlink()
                    except Exception as e:
                        logger.error(f"Failed to delete file {job.file_path}: {e}")

                if job.output_file_path and Path(job.output_file_path).exists():
                    try:
                        Path(job.output_file_path).unlink()
                    except Exception as e:
                        logger.error(f"Failed to delete output {job.output_file_path}: {e}")

                session.delete(job)
                session.commit()
                logger.info(f"Deleted job {job_id}")
                return True
            return False
        finally:
            session.close()

    def get_statistics(self) -> Dict:
        """Get database statistics"""
        session = self.get_session()
        try:
            total_jobs = session.query(Job).count()
            completed_jobs = session.query(Job).filter(Job.status == 'completed').count()
            failed_jobs = session.query(Job).filter(Job.status == 'failed').count()
            processing_jobs = session.query(Job).filter(Job.status == 'processing').count()

            # Calculate total cost
            total_cost = session.query(Job).with_entities(
                Job.estimated_cost_usd
            ).filter(Job.estimated_cost_usd.isnot(None)).all()
            total_cost_sum = sum(cost[0] for cost in total_cost if cost[0])

            return {
                'total_jobs': total_jobs,
                'completed': completed_jobs,
                'failed': failed_jobs,
                'processing': processing_jobs,
                'total_cost_usd': round(total_cost_sum, 4)
            }
        finally:
            session.close()

    def cleanup_old_jobs(self, days: int = 30) -> int:
        """Delete jobs older than specified days"""
        session = self.get_session()
        try:
            from datetime import timedelta
            cutoff = datetime.utcnow() - timedelta(days=days)

            old_jobs = session.query(Job).filter(Job.created_at < cutoff).all()

            count = 0
            for job in old_jobs:
                # Delete files
                if job.file_path and Path(job.file_path).exists():
                    try:
                        Path(job.file_path).unlink()
                    except Exception:
                        pass

                if job.output_file_path and Path(job.output_file_path).exists():
                    try:
                        Path(job.output_file_path).unlink()
                    except Exception:
                        pass

                session.delete(job)
                count += 1

            session.commit()
            logger.info(f"Cleaned up {count} old jobs")
            return count
        finally:
            session.close()
