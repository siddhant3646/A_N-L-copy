"""
Agent State Module - Manage agent state and progress tracking.

This module provides state management for the agent during task execution.
"""

from dataclasses import dataclass, field
from typing import List, Set, Optional
from datetime import datetime


@dataclass
class AgentState:
    """
    Tracks agent state during task execution.
    """
    # Step tracking
    step_count: int = 0
    max_steps: int = 50
    
    # Task status
    task_complete: bool = False
    task_result: str = ""
    
    # Error tracking
    errors: List[str] = field(default_factory=list)
    last_error: Optional[str] = None
    
    # Action tracking
    last_action: Optional[str] = None
    last_result: str = ""
    same_result_count: int = 0
    
    # Application tracking
    linkedin_applications: int = 0
    naukri_applications: int = 0
    instahyre_applications: int = 0
    
    # Performance tracking
    steps_since_cleanup: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    # Question tracking
    logged_questions: Set[str] = field(default_factory=set)
    all_logged_questions: Set[str] = field(default_factory=set)
    
    # Rate limiting
    rate_limited: bool = False
    rate_limited_platform: Optional[str] = None
    
    def reset(self) -> None:
        """Reset state for new task."""
        self.step_count = 0
        self.task_complete = False
        self.task_result = ""
        self.errors.clear()
        self.last_error = None
        self.last_action = None
        self.last_result = ""
        self.same_result_count = 0
        self.steps_since_cleanup = 0
        self.start_time = datetime.now()
        self.end_time = None
        self.rate_limited = False
        self.rate_limited_platform = None
    
    def increment_step(self) -> None:
        """Increment step counter."""
        self.step_count += 1
    
    def track_result(self, result: str) -> None:
        """
        Track result for loop detection.
        
        Args:
            result: Current result string
        """
        if result == self.last_result:
            self.same_result_count += 1
        else:
            self.same_result_count = 0
        self.last_result = result
    
    def add_error(self, error: str) -> None:
        """
        Add error to tracking.
        
        Args:
            error: Error message
        """
        self.errors.append(error)
        self.last_error = error
    
    def mark_complete(self, result: str = "SUCCESS") -> None:
        """
        Mark task as complete.
        
        Args:
            result: Final result
        """
        self.task_complete = True
        self.task_result = result
        self.end_time = datetime.now()
    
    def mark_rate_limited(self, platform: str) -> None:
        """
        Mark as rate limited.
        
        Args:
            platform: Platform that rate limited
        """
        self.rate_limited = True
        self.rate_limited_platform = platform
    
    @property
    def is_max_steps_reached(self) -> bool:
        """Check if max steps reached."""
        return self.step_count >= self.max_steps
    
    @property
    def duration_seconds(self) -> float:
        """Get task duration in seconds."""
        if self.start_time is None:
            return 0.0
        
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()
    
    @property
    def total_applications(self) -> int:
        """Get total applications submitted."""
        return (
            self.linkedin_applications +
            self.naukri_applications +
            self.instahyre_applications
        )
    
    def to_dict(self) -> dict:
        """Convert state to dictionary."""
        return {
            'step_count': self.step_count,
            'max_steps': self.max_steps,
            'task_complete': self.task_complete,
            'task_result': self.task_result,
            'errors': self.errors.copy(),
            'last_result': self.last_result,
            'same_result_count': self.same_result_count,
            'applications': {
                'linkedin': self.linkedin_applications,
                'naukri': self.naukri_applications,
                'instahyre': self.instahyre_applications,
                'total': self.total_applications
            },
            'rate_limited': self.rate_limited,
            'rate_limited_platform': self.rate_limited_platform,
            'duration_seconds': self.duration_seconds
        }
