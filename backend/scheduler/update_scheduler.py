"""
Update Scheduler for NAAC Compliance Intelligence System
Handles automated scheduling and execution of document updates
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
import asyncio
import json
from pathlib import Path
from dataclasses import dataclass, asdict

from ..updater.auto_ingest import NAACAutoIngest, AutoIngestReport

logger = logging.getLogger(__name__)

@dataclass
class ScheduledJob:
    """Information about a scheduled job"""
    job_id: str
    job_type: str
    schedule: str
    description: str
    enabled: bool
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    last_result: Optional[str] = None

@dataclass
class SchedulerStatus:
    """Status information for the scheduler"""
    is_running: bool
    total_jobs: int
    active_jobs: int
    paused_jobs: int
    last_update_check: Optional[str] = None
    next_scheduled_update: Optional[str] = None
    system_health: str = 'unknown'

class NAACUpdateScheduler:
    """
    Automated scheduler for NAAC document updates
    Manages regular update cycles, error handling, and system maintenance
    """
    
    def __init__(self, 
                 auto_ingest: NAACAutoIngest,
                 config_dir: str = "./scheduler_config",
                 db_url: str = "sqlite:///scheduler.db"):
        """
        Initialize the update scheduler
        
        Args:
            auto_ingest: Auto-ingest coordinator instance
            config_dir: Directory for scheduler configuration
            db_url: Database URL for job persistence
        """
        self.auto_ingest = auto_ingest
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Configure job stores and executors
        jobstores = {
            'default': SQLAlchemyJobStore(url=db_url)
        }
        
        executors = {
            'default': ThreadPoolExecutor(20),
            'update_executor': ThreadPoolExecutor(5)  # Dedicated executor for updates
        }
        
        job_defaults = {
            'coalesce': True,
            'max_instances': 1,
            'misfire_grace_time': 3600  # 1 hour grace time for missed jobs
        }
        
        # Initialize scheduler
        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone='UTC'
        )
        
        # Job tracking
        self.job_history = self._load_job_history()
        
        # Event callbacks
        self.event_callbacks: List[Callable[[str, Dict[str, Any]], None]] = []
        
        # Setup scheduler event listeners
        self._setup_event_listeners()
    
    def start(self):
        """Start the scheduler"""
        try:
            self.scheduler.start()
            logger.info("NAAC Update Scheduler started successfully")
            
            # Setup default jobs if none exist
            self._setup_default_jobs()
            
            # Notify listeners
            self._notify_event('scheduler_started', {
                'timestamp': datetime.now().isoformat(),
                'jobs_count': len(self.scheduler.get_jobs())
            })
            
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            raise
    
    def stop(self):
        """Stop the scheduler"""
        try:
            self.scheduler.shutdown(wait=True)
            logger.info("NAAC Update Scheduler stopped")
            
            self._notify_event('scheduler_stopped', {
                'timestamp': datetime.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}")
    
    def schedule_daily_update(self, 
                            hour: int = 2, 
                            minute: int = 0,
                            job_id: str = 'daily_naac_update') -> bool:
        """
        Schedule daily NAAC document updates
        
        Args:
            hour: Hour to run (0-23)
            minute: Minute to run (0-59) 
            job_id: Unique job identifier
            
        Returns:
            True if scheduled successfully
        """
        try:
            # Remove existing job if it exists
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            
            # Add new daily job
            self.scheduler.add_job(
                func=self._run_daily_update,
                trigger=CronTrigger(hour=hour, minute=minute),
                id=job_id,
                name='Daily NAAC Document Update',
                executor='update_executor',
                replace_existing=True,
                max_instances=1
            )
            
            logger.info(f"Scheduled daily update at {hour:02d}:{minute:02d} UTC")
            return True
            
        except Exception as e:
            logger.error(f"Failed to schedule daily update: {e}")
            return False
    
    def schedule_interval_update(self, 
                               hours: int = 6,
                               job_id: str = 'interval_naac_update') -> bool:
        """
        Schedule updates at regular intervals
        
        Args:
            hours: Interval in hours
            job_id: Unique job identifier
            
        Returns:
            True if scheduled successfully
        """
        try:
            # Remove existing job if it exists
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            
            # Add interval job
            self.scheduler.add_job(
                func=self._run_interval_update,
                trigger=IntervalTrigger(hours=hours),
                id=job_id,
                name=f'Interval NAAC Update ({hours}h)',
                executor='update_executor',
                replace_existing=True,
                max_instances=1
            )
            
            logger.info(f"Scheduled interval update every {hours} hours")
            return True
            
        except Exception as e:
            logger.error(f"Failed to schedule interval update: {e}")
            return False
    
    def schedule_criterion_specific_update(self, 
                                         criteria: List[str],
                                         cron_expression: str,
                                         job_id: Optional[str] = None) -> bool:
        """
        Schedule updates for specific NAAC criteria
        
        Args:
            criteria: List of criterion IDs to update
            cron_expression: Cron expression for scheduling
            job_id: Unique job identifier (auto-generated if None)
            
        Returns:
            True if scheduled successfully
        """
        try:
            if not job_id:
                job_id = f"criterion_update_{'_'.join(criteria)}"
            
            # Remove existing job if it exists
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            
            # Add criterion-specific job
            self.scheduler.add_job(
                func=self._run_criterion_update,
                args=[criteria],
                trigger=CronTrigger.from_crontab(cron_expression),
                id=job_id,
                name=f'Criterion Update: {", ".join(criteria)}',
                executor='update_executor',
                replace_existing=True,
                max_instances=1
            )
            
            logger.info(f"Scheduled criterion update for {criteria} with schedule: {cron_expression}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to schedule criterion update: {e}")
            return False
    
    def schedule_maintenance_tasks(self) -> bool:
        """Schedule routine maintenance tasks"""
        try:
            # Weekly cleanup task
            self.scheduler.add_job(
                func=self._run_maintenance,
                trigger=CronTrigger(day_of_week='sun', hour=1, minute=0),  # Every Sunday at 1 AM
                id='weekly_maintenance',
                name='Weekly System Maintenance',
                replace_existing=True,
                max_instances=1
            )
            
            # Daily health check
            self.scheduler.add_job(
                func=self._run_health_check,
                trigger=CronTrigger(hour=0, minute=30),  # Every day at 00:30
                id='daily_health_check',
                name='Daily System Health Check',
                replace_existing=True,
                max_instances=1
            )
            
            logger.info("Scheduled maintenance tasks")
            return True
            
        except Exception as e:
            logger.error(f"Failed to schedule maintenance tasks: {e}")
            return False
    
    def run_immediate_update(self, 
                           update_type: str = 'incremental',
                           criteria: Optional[List[str]] = None) -> str:
        """
        Run an immediate update outside of scheduled times
        
        Args:
            update_type: Type of update ('incremental', 'full', 'criterion')
            criteria: Specific criteria for criterion updates
            
        Returns:
            Job ID for tracking
        """
        try:
            job_id = f"immediate_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            if update_type == 'full':
                func = self._run_full_update
                args = []
            elif update_type == 'criterion' and criteria:
                func = self._run_criterion_update
                args = [criteria]
            else:
                func = self._run_incremental_update
                args = []
            
            # Schedule job to run immediately
            self.scheduler.add_job(
                func=func,
                args=args,
                trigger='date',  # Run once at specified time
                run_date=datetime.now() + timedelta(seconds=5),  # 5 seconds from now
                id=job_id,
                name=f'Immediate {update_type.title()} Update',
                executor='update_executor',
                max_instances=1
            )
            
            logger.info(f"Scheduled immediate {update_type} update with job ID: {job_id}")
            return job_id
            
        except Exception as e:
            logger.error(f"Failed to schedule immediate update: {e}")
            return ""
    
    def pause_job(self, job_id: str) -> bool:
        """Pause a scheduled job"""
        try:
            self.scheduler.pause_job(job_id)
            logger.info(f"Paused job: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to pause job {job_id}: {e}")
            return False
    
    def resume_job(self, job_id: str) -> bool:
        """Resume a paused job"""
        try:
            self.scheduler.resume_job(job_id)
            logger.info(f"Resumed job: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to resume job {job_id}: {e}")
            return False
    
    def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job"""
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed job: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove job {job_id}: {e}")
            return False
    
    def get_scheduler_status(self) -> SchedulerStatus:
        """Get current scheduler status"""
        
        jobs = self.scheduler.get_jobs()
        active_jobs = len([job for job in jobs if job.next_run_time])
        paused_jobs = len(jobs) - active_jobs
        
        # Find next scheduled update
        next_update = None
        for job in jobs:
            if 'update' in job.id and job.next_run_time:
                if not next_update or job.next_run_time < next_update:
                    next_update = job.next_run_time
        
        # Get last update check from history
        last_update_check = None
        for entry in reversed(self.job_history):
            if entry.get('job_type') == 'update_check':
                last_update_check = entry.get('timestamp')
                break
        
        return SchedulerStatus(
            is_running=self.scheduler.running,
            total_jobs=len(jobs),
            active_jobs=active_jobs,
            paused_jobs=paused_jobs,
            last_update_check=last_update_check,
            next_scheduled_update=next_update.isoformat() if next_update else None,
            system_health=self._check_system_health()
        )
    
    def get_job_list(self) -> List[ScheduledJob]:
        """Get list of all scheduled jobs"""
        
        jobs = []
        
        for job in self.scheduler.get_jobs():
            # Get job history for this job
            job_history = [entry for entry in self.job_history if entry.get('job_id') == job.id]
            last_run = job_history[-1].get('timestamp') if job_history else None
            last_result = job_history[-1].get('status') if job_history else None
            
            scheduled_job = ScheduledJob(
                job_id=job.id,
                job_type=self._classify_job_type(job.id),
                schedule=str(job.trigger),
                description=job.name or job.id,
                enabled=job.next_run_time is not None,
                last_run=last_run,
                next_run=job.next_run_time.isoformat() if job.next_run_time else None,
                last_result=last_result
            )
            
            jobs.append(scheduled_job)
        
        return jobs
    
    def add_event_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        """Add callback for scheduler events"""
        self.event_callbacks.append(callback)
    
    # Internal job functions
    
    def _run_daily_update(self):
        """Execute daily update job"""
        try:
            logger.info("Running scheduled daily update")
            
            report = self.auto_ingest.run_incremental_update()
            
            self._log_job_execution('daily_update', 'daily_update', report.success, {
                'documents_processed': report.documents_detected,
                'successful_downloads': report.successful_downloads,
                'knowledge_base_updates': report.knowledge_base_updates
            })
            
            self._notify_event('daily_update_completed', {
                'success': report.success,
                'report': report
            })
            
        except Exception as e:
            logger.error(f"Daily update job failed: {e}")
            self._log_job_execution('daily_update', 'daily_update', False, {'error': str(e)})
    
    def _run_interval_update(self):
        """Execute interval update job"""
        try:
            logger.info("Running scheduled interval update")
            
            report = self.auto_ingest.run_incremental_update()
            
            self._log_job_execution('interval_update', 'interval_update', report.success, {
                'documents_processed': report.documents_detected,
                'successful_downloads': report.successful_downloads
            })
            
        except Exception as e:
            logger.error(f"Interval update job failed: {e}")
            self._log_job_execution('interval_update', 'interval_update', False, {'error': str(e)})
    
    def _run_criterion_update(self, criteria: List[str]):
        """Execute criterion-specific update job"""
        try:
            logger.info(f"Running scheduled criterion update for: {criteria}")
            
            report = self.auto_ingest.run_criterion_specific_update(criteria)
            
            self._log_job_execution(f"criterion_update_{'_'.join(criteria)}", 'criterion_update', report.success, {
                'criteria': criteria,
                'documents_processed': report.documents_detected
            })
            
        except Exception as e:
            logger.error(f"Criterion update job failed: {e}")
            self._log_job_execution(f"criterion_update_{'_'.join(criteria)}", 'criterion_update', False, {'error': str(e)})
    
    def _run_full_update(self):
        """Execute full update job"""
        try:
            logger.info("Running scheduled full update")
            
            report = self.auto_ingest.force_full_update()
            
            self._log_job_execution('full_update', 'full_update', report.success, {
                'documents_processed': report.documents_detected
            })
            
        except Exception as e:
            logger.error(f"Full update job failed: {e}")
            self._log_job_execution('full_update', 'full_update', False, {'error': str(e)})
    
    def _run_incremental_update(self):
        """Execute incremental update job"""
        try:
            logger.info("Running scheduled incremental update")
            
            report = self.auto_ingest.run_incremental_update()
            
            self._log_job_execution('incremental_update', 'incremental_update', report.success, {
                'documents_processed': report.documents_detected
            })
            
        except Exception as e:
            logger.error(f"Incremental update job failed: {e}")
            self._log_job_execution('incremental_update', 'incremental_update', False, {'error': str(e)})
    
    def _run_maintenance(self):
        """Execute maintenance job"""
        try:
            logger.info("Running scheduled maintenance")
            
            # Cleanup old job history
            cutoff_date = datetime.now() - timedelta(days=30)
            self.job_history = [
                entry for entry in self.job_history 
                if datetime.fromisoformat(entry['timestamp']) > cutoff_date
            ]
            
            # Save cleaned history
            self._save_job_history()
            
            self._log_job_execution('maintenance', 'maintenance', True, {
                'cleaned_history_entries': True
            })
            
        except Exception as e:
            logger.error(f"Maintenance job failed: {e}")
            self._log_job_execution('maintenance', 'maintenance', False, {'error': str(e)})
    
    def _run_health_check(self):
        """Execute health check job"""
        try:
            logger.info("Running scheduled health check")
            
            # Check auto-ingest system health
            status = self.auto_ingest.get_update_status()
            
            health_ok = (
                status.get('system_status') == 'healthy' and
                len(status.get('recent_operations', [])) > 0
            )
            
            self._log_job_execution('health_check', 'health_check', health_ok, {
                'system_status': status.get('system_status', 'unknown')
            })
            
            if not health_ok:
                self._notify_event('health_check_failed', status)
            
        except Exception as e:
            logger.error(f"Health check job failed: {e}")
            self._log_job_execution('health_check', 'health_check', False, {'error': str(e)})
    
    # Helper methods
    
    def _setup_default_jobs(self):
        """Setup default scheduled jobs if none exist"""
        
        existing_jobs = [job.id for job in self.scheduler.get_jobs()]
        
        # Setup daily update if not exists
        if 'daily_naac_update' not in existing_jobs:
            self.schedule_daily_update()
        
        # Setup maintenance tasks
        if 'weekly_maintenance' not in existing_jobs or 'daily_health_check' not in existing_jobs:
            self.schedule_maintenance_tasks()
    
    def _setup_event_listeners(self):
        """Setup APScheduler event listeners"""
        
        def job_listener(event):
            if hasattr(event, 'job_id'):
                event_data = {
                    'job_id': event.job_id,
                    'timestamp': datetime.now().isoformat()
                }
                
                if hasattr(event, 'exception'):
                    event_data['error'] = str(event.exception)
                
                self._notify_event(f'job_{event.code}', event_data)
        
        # Add listeners for job events
        self.scheduler.add_listener(job_listener, mask=0xFFFF)  # All events
    
    def _classify_job_type(self, job_id: str) -> str:
        """Classify job type from job ID"""
        
        if 'daily' in job_id:
            return 'daily_update'
        elif 'interval' in job_id:
            return 'interval_update'
        elif 'criterion' in job_id:
            return 'criterion_update'
        elif 'maintenance' in job_id:
            return 'maintenance'
        elif 'health' in job_id:
            return 'health_check'
        else:
            return 'other'
    
    def _check_system_health(self) -> str:
        """Check overall system health"""
        
        try:
            # Check if scheduler is running
            if not self.scheduler.running:
                return 'critical'
            
            # Check recent job executions
            recent_cutoff = datetime.now() - timedelta(hours=48)
            recent_jobs = [
                entry for entry in self.job_history
                if datetime.fromisoformat(entry['timestamp']) > recent_cutoff
            ]
            
            if not recent_jobs:
                return 'warning'
            
            # Check success rate of recent jobs
            successful_jobs = [job for job in recent_jobs if job.get('success', False)]
            success_rate = len(successful_jobs) / len(recent_jobs)
            
            if success_rate >= 0.9:
                return 'healthy'
            elif success_rate >= 0.7:
                return 'warning'
            else:
                return 'critical'
                
        except Exception as e:
            logger.error(f"Error checking system health: {e}")
            return 'unknown'
    
    def _log_job_execution(self, job_id: str, job_type: str, success: bool, details: Dict[str, Any]):
        """Log job execution to history"""
        
        entry = {
            'timestamp': datetime.now().isoformat(),
            'job_id': job_id,
            'job_type': job_type,
            'success': success,
            'details': details
        }
        
        self.job_history.append(entry)
        
        # Keep only last 1000 entries
        if len(self.job_history) > 1000:
            self.job_history = self.job_history[-1000:]
        
        self._save_job_history()
    
    def _notify_event(self, event_type: str, data: Dict[str, Any]):
        """Notify all event callbacks"""
        
        for callback in self.event_callbacks:
            try:
                callback(event_type, data)
            except Exception as e:
                logger.error(f"Error in event callback: {e}")
    
    def _load_job_history(self) -> List[Dict[str, Any]]:
        """Load job execution history"""
        
        history_file = self.config_dir / "job_history.json"
        
        if history_file.exists():
            try:
                with open(history_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading job history: {e}")
        
        return []
    
    def _save_job_history(self):
        """Save job execution history"""
        
        history_file = self.config_dir / "job_history.json"
        
        try:
            with open(history_file, 'w') as f:
                json.dump(self.job_history, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving job history: {e}")