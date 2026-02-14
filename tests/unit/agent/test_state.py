"""
Tests for Agent State module.
"""

import pytest
from datetime import datetime
from src.agent.state import AgentState


class TestAgentStateInit:
    """Test AgentState initialization."""
    
    def test_default_values(self):
        """Test default values on initialization."""
        state = AgentState()
        
        assert state.step_count == 0
        assert state.max_steps == 50
        assert state.task_complete is False
        assert state.task_result == ""
        assert state.errors == []
        assert state.linkedin_applications == 0
        assert state.naukri_applications == 0
        assert state.instahyre_applications == 0
        assert state.rate_limited is False
    
    def test_custom_max_steps(self):
        """Test initialization with custom max steps."""
        state = AgentState()
        state.max_steps = 100
        assert state.max_steps == 100


class TestAgentStateReset:
    """Test state reset functionality."""
    
    def test_reset_clears_state(self):
        """Test that reset clears all state."""
        state = AgentState()
        
        # Modify state
        state.step_count = 10
        state.errors.append("error")
        state.task_complete = True
        state.rate_limited = True
        
        # Reset
        state.reset()
        
        # Verify cleared
        assert state.step_count == 0
        assert state.errors == []
        assert state.task_complete is False
        assert state.rate_limited is False
        assert state.start_time is not None
    
    def test_reset_preserves_max_steps(self):
        """Test that reset preserves max_steps."""
        state = AgentState()
        state.max_steps = 100
        
        state.reset()
        
        assert state.max_steps == 100


class TestAgentStateStepTracking:
    """Test step tracking functionality."""
    
    def test_increment_step(self):
        """Test step increment."""
        state = AgentState()
        
        state.increment_step()
        assert state.step_count == 1
        
        state.increment_step()
        assert state.step_count == 2
    
    def test_is_max_steps_reached(self):
        """Test max steps detection."""
        state = AgentState()
        state.max_steps = 5
        
        assert state.is_max_steps_reached is False
        
        state.step_count = 5
        assert state.is_max_steps_reached is True
        
        state.step_count = 6
        assert state.is_max_steps_reached is True


class TestAgentStateResultTracking:
    """Test result tracking."""
    
    def test_track_result_increments_on_same(self):
        """Test same result increments counter."""
        state = AgentState()
        
        state.track_result("continue")
        assert state.same_result_count == 0
        assert state.last_result == "continue"
        
        state.track_result("continue")
        assert state.same_result_count == 1
        
        state.track_result("continue")
        assert state.same_result_count == 2
    
    def test_track_result_resets_on_different(self):
        """Test different result resets counter."""
        state = AgentState()
        
        state.track_result("continue")
        state.track_result("continue")
        assert state.same_result_count == 1
        
        state.track_result("success")
        assert state.same_result_count == 0
        assert state.last_result == "success"


class TestAgentStateErrorTracking:
    """Test error tracking."""
    
    def test_add_error(self):
        """Test adding errors."""
        state = AgentState()
        
        state.add_error("Error 1")
        assert len(state.errors) == 1
        assert state.last_error == "Error 1"
        
        state.add_error("Error 2")
        assert len(state.errors) == 2
        assert state.last_error == "Error 2"


class TestAgentStateCompletion:
    """Test task completion."""
    
    def test_mark_complete(self):
        """Test marking task as complete."""
        state = AgentState()
        
        state.mark_complete("SUCCESS")
        
        assert state.task_complete is True
        assert state.task_result == "SUCCESS"
        assert state.end_time is not None
    
    def test_mark_complete_default_result(self):
        """Test marking complete with default result."""
        state = AgentState()
        
        state.mark_complete()
        
        assert state.task_result == "SUCCESS"


class TestAgentStateRateLimiting:
    """Test rate limiting tracking."""
    
    def test_mark_rate_limited(self):
        """Test marking as rate limited."""
        state = AgentState()
        
        state.mark_rate_limited("linkedin")
        
        assert state.rate_limited is True
        assert state.rate_limited_platform == "linkedin"


class TestAgentStateApplications:
    """Test application counting."""
    
    def test_total_applications(self):
        """Test total applications calculation."""
        state = AgentState()
        
        state.linkedin_applications = 3
        state.naukri_applications = 2
        state.instahyre_applications = 1
        
        assert state.total_applications == 6


class TestAgentStateDuration:
    """Test duration tracking."""
    
    def test_duration_seconds_running(self):
        """Test duration while running."""
        state = AgentState()
        state.reset()  # Sets start_time
        
        # Should have some duration
        assert state.duration_seconds >= 0
    
    def test_duration_seconds_completed(self):
        """Test duration when completed."""
        state = AgentState()
        state.reset()
        
        import time
        time.sleep(0.1)
        
        state.mark_complete()
        
        # Duration should be approximately 0.1 seconds
        assert state.duration_seconds >= 0.1
    
    def test_duration_no_start_time(self):
        """Test duration with no start time."""
        state = AgentState()
        state.start_time = None
        
        assert state.duration_seconds == 0.0


class TestAgentStateToDict:
    """Test state serialization."""
    
    def test_to_dict_contains_all_fields(self):
        """Test that to_dict includes all fields."""
        state = AgentState()
        state.reset()
        state.step_count = 10
        state.errors.append("test error")
        state.linkedin_applications = 5
        state.rate_limited = True
        state.rate_limited_platform = "linkedin"
        
        result = state.to_dict()
        
        assert "step_count" in result
        assert "max_steps" in result
        assert "task_complete" in result
        assert "errors" in result
        assert "applications" in result
        assert "rate_limited" in result
        assert "duration_seconds" in result
    
    def test_to_dict_applications_structure(self):
        """Test applications dict structure."""
        state = AgentState()
        state.linkedin_applications = 3
        state.naukri_applications = 2
        state.instahyre_applications = 1
        
        result = state.to_dict()
        
        assert result["applications"]["linkedin"] == 3
        assert result["applications"]["naukri"] == 2
        assert result["applications"]["instahyre"] == 1
        assert result["applications"]["total"] == 6
