"""
Base Platform Module - Abstract base class for platform handlers.

This module defines the interface that all platform handlers must implement.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from playwright.async_api import Page


class BasePlatformHandler(ABC):
    """
    Abstract base class for platform-specific handlers.
    
    All platform handlers (LinkedIn, Naukri, Instahyre) must inherit from
    this class and implement all abstract methods.
    """
    
    def __init__(self, browser: Any):
        """
        Initialize platform handler.
        
        Args:
            browser: Browser instance for page access
        """
        self.browser = browser
        self._page: Optional[Page] = None
    
    @property
    @abstractmethod
    def platform_name(self) -> str:
        """
        Return the platform identifier.
        
        Returns:
            String identifier (e.g., 'linkedin', 'naukri', 'instahyre')
        """
        pass
    
    @abstractmethod
    async def detect_login_required(self, page: Page) -> bool:
        """
        Detect if login is required on current page.
        
        Args:
            page: Playwright page object
            
        Returns:
            True if login is required
        """
        pass
    
    @abstractmethod
    async def detect_rate_limit(self, page: Page) -> bool:
        """
        Detect if rate limiting is in effect.
        
        Args:
            page: Playwright page object
            
        Returns:
            True if rate limited
        """
        pass
    
    @abstractmethod
    async def handle_task(self, page: Page, task_context: Dict[str, Any]) -> str:
        """
        Handle platform-specific task.
        
        Args:
            page: Playwright page object
            task_context: Dictionary with task details
            
        Returns:
            Result code (e.g., 'SUCCESS', 'ERROR', 'RATE_LIMITED')
        """
        pass
    
    @abstractmethod
    async def handle_form(self, page: Page, form_data: Dict[str, Any]) -> str:
        """
        Handle form filling on the platform.
        
        Args:
            page: Playwright page object
            form_data: Dictionary with form field data
            
        Returns:
            Result code
        """
        pass
    
    @abstractmethod
    def get_selectors(self) -> Dict[str, str]:
        """
        Return platform-specific DOM selectors.
        
        Returns:
            Dictionary mapping selector names to CSS selectors
        """
        pass
    
    async def get_page(self) -> Optional[Page]:
        """
        Get current page from browser.
        
        Returns:
            Playwright page or None
        """
        if hasattr(self.browser, 'get_current_page'):
            return await self.browser.get_current_page()
        return None
    
    async def pre_task_setup(self, page: Page) -> bool:
        """
        Perform setup before task execution.
        
        Args:
            page: Playwright page object
            
        Returns:
            True if setup successful
        """
        # Default implementation - can be overridden
        return True
    
    async def post_task_cleanup(self, page: Page) -> bool:
        """
        Perform cleanup after task execution.
        
        Args:
            page: Playwright page object
            
        Returns:
            True if cleanup successful
        """
        # Default implementation - can be overridden
        return True
