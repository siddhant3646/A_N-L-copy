"""
Agent Executor Module - Main agent execution orchestration.

This module orchestrates task execution by coordinating platform handlers,
rate limiting, and state management.
"""

import asyncio
from typing import Dict, Any, Optional
from playwright.async_api import Page

from src.agent.state import AgentState
from src.agent.rate_limiter import RateLimiter
from src.platforms.base_platform import BasePlatformHandler
from src.core.constants import (
    RESULT_SUCCESS,
    RESULT_ERROR,
    RESULT_RATE_LIMITED,
    RESULT_LOGIN_REQUIRED,
    RESULT_CONTINUE,
    get_platform_from_task,
    get_rate_limit_hours,
    MAX_STEPS_LINKEDIN,
    MAX_STEPS_DEFAULT,
)


class AgentExecutor:
    """
    Main agent executor that orchestrates task execution.
    
    Coordinates platform handlers, manages state, and handles rate limiting.
    """
    
    def __init__(
        self,
        browser: Any,
        platform_handlers: Dict[str, BasePlatformHandler],
        rate_limiter: RateLimiter,
        state: AgentState
    ):
        """
        Initialize agent executor.
        
        Args:
            browser: Browser instance
            platform_handlers: Dictionary of platform handlers
            rate_limiter: Rate limiter instance
            state: Agent state instance
        """
        self.browser = browser
        self.platform_handlers = platform_handlers
        self.rate_limiter = rate_limiter
        self.state = state
    
    async def run(self, task_description: str) -> bool:
        """
        Execute a task.
        
        Args:
            task_description: Description of the task to execute
            
        Returns:
            True if task completed successfully
        """
        print(f"\n🎯 Executing task: {task_description}")
        
        # Reset state for new task
        self.state.reset()
        
        # Set max steps based on platform
        platform = get_platform_from_task(task_description)
        if platform == "linkedin":
            self.state.max_steps = MAX_STEPS_LINKEDIN
        else:
            self.state.max_steps = MAX_STEPS_DEFAULT
        
        # Check rate limiting
        if self.rate_limiter.is_rate_limited(platform):
            hours = self.rate_limiter.get_remaining_hours(platform)
            print(f"⏳ {platform} is rate limited. {hours:.1f} hours remaining.")
            self.state.mark_rate_limited(platform)
            return False
        
        try:
            # Execute task
            result = await self._execute_task(task_description, platform)
            
            # Mark complete
            self.state.mark_complete(result)
            
            print(f"✅ Task completed with result: {result}")
            return result == RESULT_SUCCESS
            
        except Exception as e:
            error_msg = f"Task execution failed: {str(e)}"
            print(f"❌ {error_msg}")
            self.state.add_error(error_msg)
            self.state.mark_complete(RESULT_ERROR)
            return False
    
    async def _execute_task(
        self,
        task_description: str,
        platform: str
    ) -> str:
        """
        Execute the actual task logic.
        
        Args:
            task_description: Task description
            platform: Platform identifier
            
        Returns:
            Result code
        """
        # Get platform handler
        handler = self.platform_handlers.get(platform)
        if not handler:
            return RESULT_ERROR
        
        # Get current page
        page = await self.browser.get_current_page()
        if not page:
            return RESULT_ERROR
        
        # Pre-task setup
        if not await handler.pre_task_setup(page):
            return RESULT_ERROR
        
        # Main execution loop
        result = RESULT_CONTINUE
        while (
            not self.state.task_complete
            and not self.state.is_max_steps_reached
            and result not in [RESULT_SUCCESS, RESULT_ERROR, RESULT_RATE_LIMITED]
        ):
            self.state.increment_step()
            
            # Check for rate limiting
            if await handler.detect_rate_limit(page):
                self.rate_limiter.set_rate_limit(
                    platform,
                    get_rate_limit_hours(platform)
                )
                self.state.mark_rate_limited(platform)
                result = RESULT_RATE_LIMITED
                break
            
            # Check for login required
            if await handler.detect_login_required(page):
                result = RESULT_LOGIN_REQUIRED
                break
            
            # Handle task
            task_context = {
                'description': task_description,
                'step': self.state.step_count,
                'platform': platform
            }
            
            result = await handler.handle_task(page, task_context)
            self.state.track_result(result)
            
            # Small delay between steps
            await asyncio.sleep(1)
        
        # Post-task cleanup
        await handler.post_task_cleanup(page)
        
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get execution statistics.
        
        Returns:
            Dictionary with execution stats
        """
        return {
            'state': self.state.to_dict(),
            'rate_limits': {
                platform: hours
                for platform, hours in [
                    (p, self.rate_limiter.get_remaining_hours(p))
                    for p in self.platform_handlers.keys()
                ]
                if hours > 0
            }
        }
