"""
JavaScript Loader Module - Load JavaScript from files.

This module provides utilities for loading and executing JavaScript
from separate .js files.
"""

from pathlib import Path
from typing import Dict, Optional


class JSLoader:
    """
    Loads JavaScript files from the js directory.
    """
    
    def __init__(self, js_dir: Optional[Path] = None):
        """
        Initialize JS loader.
        
        Args:
            js_dir: Path to JS directory. Auto-detected if None.
        """
        if js_dir is None:
            # Find js directory relative to this file
            base_dir = Path(__file__).parent.parent
            js_dir = base_dir / "sentinel" / "js"
        
        self.js_dir = js_dir
        self._cache: Dict[str, str] = {}
    
    def load(self, filename: str) -> str:
        """
        Load a JavaScript file.
        
        Args:
            filename: Name of JS file (e.g., 'utils.js' or 'linkedin/form_fill.js')
            
        Returns:
            Contents of JS file
            
        Raises:
            FileNotFoundError: If file doesn't exist
        """
        # Check cache
        if filename in self._cache:
            return self._cache[filename]
        
        # Construct path
        file_path = self.js_dir / filename
        
        if not file_path.exists():
            raise FileNotFoundError(f"JavaScript file not found: {file_path}")
        
        # Read and cache
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        self._cache[filename] = content
        return content
    
    def load_with_vars(self, filename: str, variables: Dict[str, str]) -> str:
        """
        Load JS file and replace template variables.
        
        Args:
            filename: Name of JS file
            variables: Dictionary of variable names to values
            
        Returns:
            JS content with variables replaced
        """
        content = self.load(filename)
        
        for var_name, var_value in variables.items():
            placeholder = f"{{{{ {var_name} }}}}"
            content = content.replace(placeholder, str(var_value))
        
        return content
    
    def clear_cache(self) -> None:
        """Clear the JS cache."""
        self._cache.clear()
    
    def list_files(self, subdir: Optional[str] = None) -> list:
        """
        List available JS files.
        
        Args:
            subdir: Optional subdirectory to list
            
        Returns:
            List of file paths
        """
        target_dir = self.js_dir
        if subdir:
            target_dir = target_dir / subdir
        
        if not target_dir.exists():
            return []
        
        files = []
        for f in target_dir.rglob("*.js"):
            rel_path = f.relative_to(self.js_dir)
            files.append(str(rel_path))
        
        return sorted(files)


# Convenience function
def load_js(filename: str, js_dir: Optional[str] = None) -> str:
    """
    Load a JavaScript file.
    
    Args:
        filename: Name of JS file
        js_dir: Optional path to JS directory
        
    Returns:
        Contents of JS file
    """
    js_path = Path(js_dir) if js_dir else None
    loader = JSLoader(js_path)
    return loader.load(filename)
